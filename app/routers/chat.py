import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.config import RATE_LIMIT_CHAT
from app.database import get_db
from app.models.chat_log import ChatLog
from app.models.company import Company
from app.models.qa_knowledge import QaKnowledge
from app.rate_limit import limiter
from app.schemas.chat import ChatHistoryItem, ChatRequest, ChatResponse
from app.services.chat_service import search_qa

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _resolve_company_id(db: Session, company_code: str | None) -> int:
    """Resolve company_code to company_id. Default to 1 if not provided."""
    if not company_code:
        return 1
    company = (
        db.query(Company)
        .filter(Company.company_code == company_code, Company.is_active == True, Company.deleted_at == None)
        .first()
    )
    if not company:
        raise HTTPException(status_code=404, detail="회사를 찾을 수 없습니다.")
    return company.company_id


@router.post("", response_model=ChatResponse)
@limiter.limit(RATE_LIMIT_CHAT)
def chat(req: ChatRequest, request: Request, db: Session = Depends(get_db)):
    company_id = _resolve_company_id(db, req.company_code)

    start_time = time.perf_counter()
    answer, category, qa_id, confidence = search_qa(db, req.question, req.category, company_id)
    elapsed_ms = int((time.perf_counter() - start_time) * 1000)

    # Increment used_count on matched QA
    if qa_id:
        qa = db.query(QaKnowledge).filter(QaKnowledge.qa_id == qa_id).first()
        if qa:
            qa.used_count = (qa.used_count or 0) + 1

    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent", "")[:500]

    log = ChatLog(
        company_id=company_id,
        user_question=req.question,
        bot_answer=answer,
        qa_id=qa_id,
        session_id=req.session_id,
        category=category,
        confidence_score=confidence,
        response_time_ms=elapsed_ms,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(log)
    db.commit()

    return ChatResponse(answer=answer, category=category, qa_id=qa_id)


@router.get("/history/{session_id}", response_model=list[ChatHistoryItem])
def get_history(
    session_id: str,
    company_code: str | None = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(ChatLog).filter(ChatLog.session_id == session_id)

    if company_code:
        company_id = _resolve_company_id(db, company_code)
        query = query.filter(ChatLog.company_id == company_id)

    logs = query.order_by(ChatLog.timestamp.asc()).all()
    return logs
