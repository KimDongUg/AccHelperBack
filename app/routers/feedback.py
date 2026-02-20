from fastapi import APIRouter, Cookie, Depends, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin, require_auth
from app.models.chat_log import ChatLog
from app.models.feedback import Feedback
from app.schemas.feedback import (
    ChatLogItem,
    ChatLogListResponse,
    FeedbackCreate,
    FeedbackListResponse,
    FeedbackResponse,
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
