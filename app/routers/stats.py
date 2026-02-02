from datetime import datetime, timedelta

from fastapi import APIRouter, Cookie, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.chat_log import ChatLog
from app.models.qa_knowledge import QaKnowledge
from app.routers.auth import get_current_user

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("")
def get_stats(
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(None),
):
    user = get_current_user(session_token)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    total_qa = db.query(QaKnowledge).count()
    active_qa = db.query(QaKnowledge).filter(QaKnowledge.is_active == True).count()

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_chats = (
        db.query(ChatLog).filter(ChatLog.timestamp >= today_start).count()
    )

    total_chats = db.query(ChatLog).count()

    # Category distribution
    categories = {}
    for qa in db.query(QaKnowledge).all():
        categories[qa.category] = categories.get(qa.category, 0) + 1

    return {
        "total_qa": total_qa,
        "active_qa": active_qa,
        "today_chats": today_chats,
        "total_chats": total_chats,
        "categories": categories,
    }
