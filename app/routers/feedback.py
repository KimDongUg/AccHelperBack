from datetime import datetime

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin, require_auth
from app.models.chat_log import ChatLog
from app.models.feedback import Feedback
from app.schemas.feedback import (
    ChatLogItem,
    ChatLogListResponse,
    FeedbackCountResponse,
    FeedbackCreate,
    FeedbackListResponse,
    FeedbackResponse,
    FeedbackStatusResponse,
    FeedbackStatusUpdate,
    UnmatchedItem,
    UnmatchedListResponse,
)
from app.services.jwt_service import decode_token

router = APIRouter(tags=["feedback"])


def _optional_user(request: Request, session_token: str | None = Cookie(None)) -> dict | None:
    """Extract user from JWT if present, return None otherwise."""
    auth_header = request.headers.get("authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else session_token
    if not token:
        return None
    return decode_token(token)


@router.post("/api/feedback", response_model=FeedbackResponse, status_code=201)
def create_feedback(
    data: FeedbackCreate,
    db: Session = Depends(get_db),
    user: dict | None = Depends(_optional_user),
):
    """Create a feedback entry (like/dislike). Auth optional for public chatbot."""
    company_id = data.company_id or (user.get("company_id", 0) if user else 0)

    fb = Feedback(
        company_id=company_id,
        chat_log_id=data.chat_log_id,
        question=data.question,
        answer=data.answer,
        qa_ids=data.qa_ids,
        rating=data.rating,
        comment=data.comment,
        session_id=data.session_id,
    )
    db.add(fb)

    # Also update chat_log user_feedback if chat_log_id provided
    if data.chat_log_id:
        log = db.query(ChatLog).filter(ChatLog.log_id == data.chat_log_id).first()
        if log:
            log.user_feedback = data.rating

    db.commit()
    db.refresh(fb)
    return fb


@router.get("/admin/feedback", response_model=FeedbackListResponse)
def list_feedback(
    rating: str | None = Query(None),
    page: int = 1,
    size: int = 20,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
):
    """List feedbacks (admin). Filter by rating (like/dislike)."""
    company_id = user["company_id"]
    query = db.query(Feedback)
    if company_id != 0:
        query = query.filter(Feedback.company_id == company_id)
    if rating:
        query = query.filter(Feedback.rating == rating)

    total = query.count()
    pages = max(1, (total + size - 1) // size)
    items = (
        query.order_by(Feedback.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    return FeedbackListResponse(items=items, total=total, page=page, pages=pages)


# --- New /api/feedback endpoints for frontend dashboard ---

@router.get("/api/feedback/count", response_model=FeedbackCountResponse)
def feedback_dislike_count(
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
):
    """미처리 불만족(dislike) 건수"""
    company_id = user["company_id"]
    query = db.query(Feedback).filter(
        Feedback.rating == "dislike",
        Feedback.status == "pending",
    )
    if company_id != 0:
        query = query.filter(Feedback.company_id == company_id)
    return FeedbackCountResponse(count=query.count())


@router.get("/api/feedback", response_model=FeedbackListResponse)
def list_feedback_api(
    rating: str | None = Query(None),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
):
    """피드백 목록 조회 (관리자). rating/status 필터 가능."""
    company_id = user["company_id"]
    query = db.query(Feedback)
    if company_id != 0:
        query = query.filter(Feedback.company_id == company_id)
    if rating:
        query = query.filter(Feedback.rating == rating)
    if status:
        query = query.filter(Feedback.status == status)

    total = query.count()
    pages = max(1, (total + size - 1) // size)
    items = (
        query.order_by(Feedback.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    return FeedbackListResponse(items=items, total=total, page=page, pages=pages)


@router.patch("/api/feedback/{feedback_id}", response_model=FeedbackStatusResponse)
def update_feedback_status(
    feedback_id: int,
    data: FeedbackStatusUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
):
    """피드백 처리 상태 변경 (관리자)"""
    if data.status not in ("resolved", "dismissed"):
        raise HTTPException(status_code=400, detail="status는 'resolved' 또는 'dismissed'만 가능합니다.")

    company_id = user["company_id"]
    query = db.query(Feedback).filter(Feedback.id == feedback_id)
    if company_id != 0:
        query = query.filter(Feedback.company_id == company_id)

    fb = query.first()
    if not fb:
        raise HTTPException(status_code=404, detail="피드백을 찾을 수 없습니다.")

    fb.status = data.status
    db.commit()
    return FeedbackStatusResponse(id=fb.id, status=fb.status)


@router.get("/admin/unmatched", response_model=UnmatchedListResponse)
def list_unmatched(
    page: int = 1,
    size: int = 20,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
):
    """List unmatched questions (used_rag=false and no qa_id)."""
    company_id = user["company_id"]
    query = db.query(ChatLog).filter(
        ChatLog.used_rag == False,
        ChatLog.qa_id == None,
    )
    if company_id != 0:
        query = query.filter(ChatLog.company_id == company_id)

    total = query.count()
    pages = max(1, (total + size - 1) // size)
    items = (
        query.order_by(ChatLog.timestamp.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    result = [
        UnmatchedItem(
            log_id=item.log_id,
            company_id=item.company_id,
            user_question=item.user_question,
            bot_answer=item.bot_answer,
            timestamp=item.timestamp,
        )
        for item in items
    ]

    return UnmatchedListResponse(items=result, total=total, page=page, pages=pages)


@router.get("/admin/chat-logs", response_model=ChatLogListResponse)
def list_chat_logs(
    page: int = 1,
    size: int = 20,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
):
    """List all chat logs (admin)."""
    company_id = user["company_id"]
    query = db.query(ChatLog)
    if company_id != 0:
        query = query.filter(ChatLog.company_id == company_id)

    total = query.count()
    pages = max(1, (total + size - 1) // size)
    items = (
        query.order_by(ChatLog.timestamp.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    return ChatLogListResponse(items=items, total=total, page=page, pages=pages)
