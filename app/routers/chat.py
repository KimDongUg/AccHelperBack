import json
import time

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.config import RATE_LIMIT_CHAT
from app.database import get_db
from app.models.chat_log import ChatLog
from app.models.qa_knowledge import QaKnowledge
from app.quota import increment_usage
from app.rate_limit import limiter
from app.schemas.chat import ChatHistoryItem, ChatRequest, ChatResponse
from app.services.chat_service import search_qa, search_qa_rag

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
@limiter.limit(RATE_LIMIT_CHAT)
def chat(req: ChatRequest, request: Request, db: Session = Depends(get_db)):
    company_id = req.company_id or 1

    start_time = time.perf_counter()

    # Try RAG search first
    rag_result = search_qa_rag(db, req.question, company_id)

    elapsed_ms = int((time.perf_counter() - start_time) * 1000)

    # Determine qa_id and category from evidence
    qa_id = rag_result.evidence_ids[0] if rag_result.evidence_ids else None
    category = None
    if qa_id:
        qa = db.query(QaKnowledge).filter(QaKnowledge.qa_id == qa_id).first()
        if qa:
            qa.used_count = (qa.used_count or 0) + 1
            category = qa.category

    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent", "")[:500]

    evidence_ids_str = json.dumps(rag_result.evidence_ids) if rag_result.evidence_ids else ""

    log = ChatLog(
        company_id=company_id,
        user_question=req.question,
        bot_answer=rag_result.answer,
        qa_id=qa_id,
        session_id=req.session_id,
        category=category,
        confidence_score=rag_result.avg_similarity if rag_result.used_rag else None,
        response_time_ms=elapsed_ms,
        ip_address=ip_address,
        user_agent=user_agent,
        used_rag=rag_result.used_rag,
        evidence_ids=evidence_ids_str,
    )
    db.add(log)

    # Track usage
    increment_usage(
        db, company_id,
        chat_cnt=1,
        tokens_used=rag_result.tokens_used,
    )

    db.commit()

    return ChatResponse(
        answer=rag_result.answer,
        category=category,
        qa_id=qa_id,
        used_rag=rag_result.used_rag,
        evidence_ids=rag_result.evidence_ids,
        similarity_score=rag_result.avg_similarity if rag_result.used_rag else None,
    )


@router.get("/history/{session_id}", response_model=list[ChatHistoryItem])
def get_history(
    session_id: str,
    company_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(ChatLog).filter(ChatLog.session_id == session_id)

    if company_id:
        query = query.filter(ChatLog.company_id == company_id)

    logs = query.order_by(ChatLog.timestamp.asc()).all()
    return logs
