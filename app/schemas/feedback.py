from datetime import datetime

from pydantic import BaseModel


class FeedbackCreate(BaseModel):
    chat_log_id: int | None = None
    question: str
    answer: str
    qa_ids: str = ""  # JSON array of qa_ids
    rating: str  # "like" or "dislike"
    comment: str | None = None
    company_id: int | None = None


class FeedbackResponse(BaseModel):
    id: int
    company_id: int
    chat_log_id: int | None = None
    question: str
    answer: str
    qa_ids: str = ""
    rating: str
    comment: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class FeedbackListResponse(BaseModel):
    items: list[FeedbackResponse]
    total: int
    page: int
    pages: int


class UnmatchedItem(BaseModel):
    log_id: int
    company_id: int
    user_question: str
    bot_answer: str
    timestamp: datetime

    model_config = {"from_attributes": True}


class UnmatchedListResponse(BaseModel):
    items: list[UnmatchedItem]
    total: int
    page: int
    pages: int


class ChatLogItem(BaseModel):
    log_id: int
    company_id: int
    user_question: str
    bot_answer: str
    qa_id: int | None = None
    session_id: str
    category: str | None = None
    confidence_score: float | None = None
    used_rag: bool = False
    evidence_ids: str = ""
    timestamp: datetime

    model_config = {"from_attributes": True}


class ChatLogListResponse(BaseModel):
    items: list[ChatLogItem]
    total: int
    page: int
    pages: int
