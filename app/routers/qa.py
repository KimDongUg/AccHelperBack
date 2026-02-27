from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin, require_auth
from app.models.chat_log import ChatLog
from app.models.company import Company
from app.models.qa_knowledge import QaKnowledge
from app.quota import increment_usage
from app.schemas.qa import QaCreate, QaListResponse, QaResponse, QaUpdate
from app.services.embedding_service import delete_qa_embedding, upsert_qa_embedding

router = APIRouter(prefix="/api/qa", tags=["qa"])


@router.get("", response_model=QaListResponse)
def list_qa(
    page: int = 1,
    size: int = 10,
    search: str = "",
    category: str = "",
    status: str = "",
    company_id: int | None = Query(None, alias="company_id"),
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    user_company_id = user["company_id"]
    query = db.query(QaKnowledge)
    if user_company_id != 0:
        # Non-super_admin: always filter by own company
        query = query.filter(QaKnowledge.company_id == user_company_id)
    elif company_id is not None:
        # super_admin with company filter
        query = query.filter(QaKnowledge.company_id == company_id)

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

    # Build company_id → company_name map
    company_map = {}
    if user_company_id == 0:
        companies = db.query(Company.company_id, Company.company_name).all()
        company_map = {c.company_id: c.company_name for c in companies}

    result_items = []
    for item in items:
        resp = QaResponse.model_validate(item)
        resp.company_name = company_map.get(item.company_id)
        result_items.append(resp)

    return QaListResponse(items=result_items, total=total, page=page, pages=pages)


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

    qa_query = db.query(QaKnowledge)
    if company_id != 0:
        qa_query = qa_query.filter(QaKnowledge.company_id == company_id)
    all_qa = qa_query.all()
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
    user_company_id = user["company_id"]
    query = db.query(QaKnowledge).filter(QaKnowledge.qa_id == qa_id)
    if user_company_id != 0:
        query = query.filter(QaKnowledge.company_id == user_company_id)
    qa = query.first()
    if not qa:
        raise HTTPException(status_code=404, detail="Q&A를 찾을 수 없습니다.")

    resp = QaResponse.model_validate(qa)
    if user_company_id == 0:
        company = db.query(Company).filter(Company.company_id == qa.company_id).first()
        resp.company_name = company.company_name if company else None
    return resp


@router.post("", response_model=QaResponse, status_code=201)
def create_qa(
    data: QaCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
):
    user_company_id = user["company_id"]

    # super_admin can specify target company_id
    target_company_id = user_company_id
    if user_company_id == 0 and data.company_id is not None:
        target_company_id = data.company_id

    # Check max_qa_count quota (skip for super_admin)
    if target_company_id != 0:
        company = db.query(Company).filter(Company.company_id == target_company_id).first()
        if company:
            current_count = db.query(QaKnowledge).filter(QaKnowledge.company_id == target_company_id).count()
            if current_count >= company.max_qa_count:
                raise HTTPException(
                    status_code=403,
                    detail=f"Q&A 수 한도({company.max_qa_count}개)를 초과했습니다.",
                )

    qa_data = data.model_dump(exclude={"company_id"})
    qa = QaKnowledge(
        **qa_data,
        company_id=target_company_id,
    )
    db.add(qa)

    # QA 커스터마이즈 플래그
    if target_company_id != 0:
        comp = db.query(Company).filter(Company.company_id == target_company_id).first()
        if comp and not comp.qa_customized:
            comp.qa_customized = True

    db.flush()

    # Auto-generate embedding
    if upsert_qa_embedding(db, qa):
        increment_usage(db, target_company_id, embed_cnt=1)

    db.commit()
    db.refresh(qa)

    resp = QaResponse.model_validate(qa)
    if user_company_id == 0:
        company = db.query(Company).filter(Company.company_id == qa.company_id).first()
        resp.company_name = company.company_name if company else None
    return resp


@router.put("/{qa_id}", response_model=QaResponse)
def update_qa(
    qa_id: int,
    data: QaUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
):
    user_company_id = user["company_id"]
    query = db.query(QaKnowledge).filter(QaKnowledge.qa_id == qa_id)
    if user_company_id != 0:
        query = query.filter(QaKnowledge.company_id == user_company_id)
    qa = query.first()
    if not qa:
        raise HTTPException(status_code=404, detail="Q&A를 찾을 수 없습니다.")

    update_data = data.model_dump(exclude_unset=True)
    # Only super_admin can change company_id
    if "company_id" in update_data and user_company_id != 0:
        del update_data["company_id"]
    for key, value in update_data.items():
        setattr(qa, key, value)
    qa.updated_at = datetime.utcnow()
    qa.updated_by = user["user_id"]

    # QA 커스터마이즈 플래그
    cid = qa.company_id
    if cid != 0:
        comp = db.query(Company).filter(Company.company_id == cid).first()
        if comp and not comp.qa_customized:
            comp.qa_customized = True

    db.flush()

    # Re-generate embedding
    if upsert_qa_embedding(db, qa):
        increment_usage(db, cid, embed_cnt=1)

    db.commit()
    db.refresh(qa)

    resp = QaResponse.model_validate(qa)
    if user_company_id == 0:
        company = db.query(Company).filter(Company.company_id == qa.company_id).first()
        resp.company_name = company.company_name if company else None
    return resp


@router.delete("/{qa_id}")
def delete_qa(
    qa_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
):
    company_id = user["company_id"]
    query = db.query(QaKnowledge).filter(QaKnowledge.qa_id == qa_id)
    if company_id != 0:
        query = query.filter(QaKnowledge.company_id == company_id)
    qa = query.first()
    if not qa:
        raise HTTPException(status_code=404, detail="Q&A를 찾을 수 없습니다.")

    cid = qa.company_id

    # Delete embedding
    delete_qa_embedding(db, qa_id)

    db.query(ChatLog).filter(ChatLog.qa_id == qa_id).update(
        {ChatLog.qa_id: None}, synchronize_session="fetch"
    )
    db.delete(qa)

    # QA 커스터마이즈 플래그
    if cid != 0:
        comp = db.query(Company).filter(Company.company_id == cid).first()
        if comp and not comp.qa_customized:
            comp.qa_customized = True

    db.commit()
    return {"success": True, "message": "삭제되었습니다."}


@router.patch("/{qa_id}/toggle", response_model=QaResponse)
def toggle_qa(
    qa_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
):
    user_company_id = user["company_id"]
    query = db.query(QaKnowledge).filter(QaKnowledge.qa_id == qa_id)
    if user_company_id != 0:
        query = query.filter(QaKnowledge.company_id == user_company_id)
    qa = query.first()
    if not qa:
        raise HTTPException(status_code=404, detail="Q&A를 찾을 수 없습니다.")
    qa.is_active = not qa.is_active
    qa.updated_at = datetime.utcnow()
    qa.updated_by = user["user_id"]
    db.commit()
    db.refresh(qa)

    resp = QaResponse.model_validate(qa)
    if user_company_id == 0:
        company = db.query(Company).filter(Company.company_id == qa.company_id).first()
        resp.company_name = company.company_name if company else None
    return resp
