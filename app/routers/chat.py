from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.config import RATE_LIMIT_CHAT
from app.database import get_db
from app.models.chat_log import ChatLog
from app.rate_limit import limiter
from app.schemas.chat import ChatHistoryItem, ChatRequest, ChatResponse
from app.services.chat_service import search_qa

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
@limiter.limit(RATE_LIMIT_CHAT)
def chat(req: ChatRequest, request: Request, db: Session = Depends(get_db)):
    answer, category, qa_id = search_qa(db, req.question, req.category)

    log = ChatLog(
        user_question=req.question,
        bot_answer=answer,
        qa_id=qa_id,
        session_id=req.session_id,
        category=category,
    )
    db.add(log)
    db.commit()

    return ChatResponse(answer=answer, category=category, qa_id=qa_id)


@router.get("/history/{session_id}", response_model=list[ChatHistoryItem])
def get_history(session_id: str, db: Session = Depends(get_db)):
    logs = (
        db.query(ChatLog)
        .filter(ChatLog.session_id == session_id)
        .order_by(ChatLog.timestamp.asc())
        .all()
    )
    return logs
