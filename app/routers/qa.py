from datetime import datetime

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.chat_log import ChatLog
from app.models.qa_knowledge import QaKnowledge
from app.routers.auth import get_current_user
from app.schemas.qa import QaCreate, QaListResponse, QaResponse, QaUpdate

router = APIRouter(prefix="/api/qa", tags=["qa"])


def require_admin(session_token: str | None = Cookie(None)):
    user = get_current_user(session_token)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    return user


@router.get("", response_model=QaListResponse)
def list_qa(
    page: int = 1,
    size: int = 10,
    search: str = "",
    category: str = "",
    status: str = "",
    db: Session = Depends(get_db),
    _user: dict = Depends(require_admin),
):
    query = db.query(QaKnowledge)

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
    _user: dict = Depends(require_admin),
):
    """Return similar questions for duplicate warning."""
    q = question.strip().lower()
    if len(q) < 5:
        return {"duplicates": []}

    all_qa = db.query(QaKnowledge).all()
    results = []
    for qa in all_qa:
        if exclude_id and qa.qa_id == exclude_id:
            continue
        existing = qa.question.strip().lower()
        # Simple character overlap similarity
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
    _user: dict = Depends(require_admin),
):
    qa = db.query(QaKnowledge).filter(QaKnowledge.qa_id == qa_id).first()
    if not qa:
        raise HTTPException(status_code=404, detail="Q&A를 찾을 수 없습니다.")
    return qa


@router.post("", response_model=QaResponse, status_code=201)
def create_qa(
    data: QaCreate,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_admin),
):
    qa = QaKnowledge(**data.model_dump())
    db.add(qa)
    db.commit()
    db.refresh(qa)
    return qa


@router.put("/{qa_id}", response_model=QaResponse)
def update_qa(
    qa_id: int,
    data: QaUpdate,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_admin),
):
    qa = db.query(QaKnowledge).filter(QaKnowledge.qa_id == qa_id).first()
    if not qa:
        raise HTTPException(status_code=404, detail="Q&A를 찾을 수 없습니다.")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(qa, key, value)
    qa.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(qa)
    return qa


@router.delete("/{qa_id}")
def delete_qa(
    qa_id: int,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_admin),
):
    qa = db.query(QaKnowledge).filter(QaKnowledge.qa_id == qa_id).first()
    if not qa:
        raise HTTPException(status_code=404, detail="Q&A를 찾을 수 없습니다.")

    # Nullify references in chat_logs
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
    _user: dict = Depends(require_admin),
):
    qa = db.query(QaKnowledge).filter(QaKnowledge.qa_id == qa_id).first()
    if not qa:
        raise HTTPException(status_code=404, detail="Q&A를 찾을 수 없습니다.")
    qa.is_active = not qa.is_active
    qa.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(qa)
    return qa
