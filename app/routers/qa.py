from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin, require_auth
from app.models.chat_log import ChatLog
from app.models.company import Company
from app.models.qa_knowledge import QaKnowledge
from app.schemas.qa import QaCreate, QaListResponse, QaResponse, QaUpdate

router = APIRouter(prefix="/api/qa", tags=["qa"])


@router.get("", response_model=QaListResponse)
def list_qa(
    page: int = 1,
    size: int = 10,
    search: str = "",
    category: str = "",
    status: str = "",
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    company_id = user["company_id"]
    query = db.query(QaKnowledge).filter(QaKnowledge.company_id == company_id)

    if search:
        query = query.filter(
            QaKnowledge.question.contains(search)
            | QaKnowledge.answer.contains(search)
            | QaKnowledge.keywords.contains(search)
        )
    if category:
        query = query.filter(QaKnowledge.category == category)
    if status == "active":
        query = query.filter(QaKnowledge.is_active == True)
    elif status == "inactive":
        query = query.filter(QaKnowledge.is_active == False)

    total = query.count()
    pages = max(1, (total + size - 1) // size)
    items = (
        query.order_by(QaKnowledge.qa_id.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    return QaListResponse(items=items, total=total, page=page, pages=pages)


@router.get("/check-duplicate")
def check_duplicate(
    question: str = Query(..., min_length=1),
    exclude_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Return similar questions for duplicate warning."""
    company_id = user["company_id"]
    q = question.strip().lower()
    if len(q) < 5:
        return {"duplicates": []}

    all_qa = db.query(QaKnowledge).filter(QaKnowledge.company_id == company_id).all()
    results = []
    for qa in all_qa:
        if exclude_id and qa.qa_id == exclude_id:
            continue
        existing = qa.question.strip().lower()
        if len(q) == 0 or len(existing) == 0:
            continue
        common = sum(1 for c in q if c in existing)
        similarity = (2.0 * common) / (len(q) + len(existing))
        if similarity >= 0.8:
            results.append({
                "qa_id": qa.qa_id,
                "question": qa.question,
                "similarity": round(similarity * 100),
            })

    results.sort(key=lambda x: x["similarity"], reverse=True)
    return {"duplicates": results[:5]}


@router.get("/{qa_id}", response_model=QaResponse)
def get_qa(
    qa_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    company_id = user["company_id"]
    qa = (
        db.query(QaKnowledge)
        .filter(QaKnowledge.qa_id == qa_id, QaKnowledge.company_id == company_id)
        .first()
    )
    if not qa:
        raise HTTPException(status_code=404, detail="Q&A를 찾을 수 없습니다.")
    return qa


@router.post("", response_model=QaResponse, status_code=201)
def create_qa(
    data: QaCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
):
    company_id = user["company_id"]

    # Check max_qa_count quota
    company = db.query(Company).filter(Company.company_id == company_id).first()
    if company:
        current_count = db.query(QaKnowledge).filter(QaKnowledge.company_id == company_id).count()
        if current_count >= company.max_qa_count:
            raise HTTPException(
                status_code=403,
                detail=f"Q&A 수 한도({company.max_qa_count}개)를 초과했습니다.",
            )

    qa = QaKnowledge(
        **data.model_dump(),
        company_id=company_id,
        created_by=user["user_id"],
    )
    db.add(qa)
    db.commit()
    db.refresh(qa)
    return qa


@router.put("/{qa_id}", response_model=QaResponse)
def update_qa(
    qa_id: int,
    data: QaUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
):
    company_id = user["company_id"]
    qa = (
        db.query(QaKnowledge)
        .filter(QaKnowledge.qa_id == qa_id, QaKnowledge.company_id == company_id)
        .first()
    )
    if not qa:
        raise HTTPException(status_code=404, detail="Q&A를 찾을 수 없습니다.")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(qa, key, value)
    qa.updated_at = datetime.utcnow()
    qa.updated_by = user["user_id"]
    db.commit()
    db.refresh(qa)
    return qa


@router.delete("/{qa_id}")
def delete_qa(
    qa_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
):
    company_id = user["company_id"]
    qa = (
        db.query(QaKnowledge)
        .filter(QaKnowledge.qa_id == qa_id, QaKnowledge.company_id == company_id)
        .first()
    )
    if not qa:
        raise HTTPException(status_code=404, detail="Q&A를 찾을 수 없습니다.")

    db.query(ChatLog).filter(ChatLog.qa_id == qa_id).update(
        {ChatLog.qa_id: None}, synchronize_session="fetch"
    )
    db.delete(qa)
    db.commit()
    return {"success": True, "message": "삭제되었습니다."}


@router.patch("/{qa_id}/toggle", response_model=QaResponse)
def toggle_qa(
    qa_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
):
    company_id = user["company_id"]
    qa = (
        db.query(QaKnowledge)
        .filter(QaKnowledge.qa_id == qa_id, QaKnowledge.company_id == company_id)
        .first()
    )
    if not qa:
        raise HTTPException(status_code=404, detail="Q&A를 찾을 수 없습니다.")
    qa.is_active = not qa.is_active
    qa.updated_at = datetime.utcnow()
    qa.updated_by = user["user_id"]
    db.commit()
    db.refresh(qa)
    return qa
