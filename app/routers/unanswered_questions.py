from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin
from app.models.unanswered_question import UnansweredQuestion
from app.schemas.unanswered_question import (
    UnansweredQuestionCountResponse,
    UnansweredQuestionCreate,
    UnansweredQuestionListResponse,
    UnansweredQuestionResponse,
    UnansweredQuestionStatusResponse,
    UnansweredQuestionStatusUpdate,
)

router = APIRouter(prefix="/api/unanswered-questions", tags=["unanswered-questions"])


@router.post("", response_model=UnansweredQuestionResponse, status_code=201)
def create_unanswered_question(
    data: UnansweredQuestionCreate,
    db: Session = Depends(get_db),
):
    """미답변 질문 저장 (챗봇에서 호출, 인증 불필요)"""
    uq = UnansweredQuestion(
        question=data.question,
        company_id=data.company_id,
        session_id=data.session_id,
    )
    db.add(uq)
    db.commit()
    db.refresh(uq)
    return uq


@router.get("", response_model=UnansweredQuestionListResponse)
def list_unanswered_questions(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
):
    """미답변 목록 조회 (pending만, 관리자 인증 필요)"""
    company_id = user["company_id"]
    query = db.query(UnansweredQuestion).filter(UnansweredQuestion.status == "pending")
    if company_id != 0:
        query = query.filter(UnansweredQuestion.company_id == company_id)

    total = query.count()
    pages = max(1, (total + size - 1) // size)
    items = (
        query.order_by(UnansweredQuestion.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    return UnansweredQuestionListResponse(items=items, page=page, pages=pages, total=total)


@router.get("/count", response_model=UnansweredQuestionCountResponse)
def count_unanswered_questions(
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
):
    """미답변(pending) 건수 (관리자 인증 필요)"""
    company_id = user["company_id"]
    query = db.query(UnansweredQuestion).filter(UnansweredQuestion.status == "pending")
    if company_id != 0:
        query = query.filter(UnansweredQuestion.company_id == company_id)

    return UnansweredQuestionCountResponse(count=query.count())


@router.patch("/{question_id}", response_model=UnansweredQuestionStatusResponse)
def update_unanswered_question_status(
    question_id: int,
    data: UnansweredQuestionStatusUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
):
    """미답변 질문 상태 변경 (관리자 인증 필요)"""
    if data.status not in ("resolved", "dismissed"):
        raise HTTPException(status_code=400, detail="status는 'resolved' 또는 'dismissed'만 가능합니다.")

    company_id = user["company_id"]
    query = db.query(UnansweredQuestion).filter(UnansweredQuestion.id == question_id)
    if company_id != 0:
        query = query.filter(UnansweredQuestion.company_id == company_id)

    uq = query.first()
    if not uq:
        raise HTTPException(status_code=404, detail="미답변 질문을 찾을 수 없습니다.")

    uq.status = data.status
    uq.updated_at = datetime.utcnow()
    db.commit()

    return UnansweredQuestionStatusResponse(id=uq.id, status=uq.status)
