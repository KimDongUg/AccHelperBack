import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, field_validator


class FeedbackCreate(BaseModel):
    chat_log_id: int | None = None
    question: str
    answer: str
    qa_ids: str = ""  # stored as JSON string
    rating: str  # "like" or "dislike"
    comment: str | None = None
    company_id: int | None = None
    session_id: str | None = None

    @field_validator("qa_ids", mode="before")
    @classmethod
    def coerce_qa_ids(cls, v: Any) -> str:
        if isinstance(v, list):
            return json.dumps(v)
        return v or ""


class FeedbackResponse(BaseModel):
    id: int
    company_id: int
    chat_log_id: int | None = None
    question: str
    answer: str
    qa_ids: str = ""
    rating: str
    comment: str | None = None
    session_id: str | None = None
    status: str = "pending"
    created_at: datetime

    model_config = {"from_attributes": True}


class FeedbackListResponse(BaseModel):
    items: list[FeedbackResponse]
    total: int
    page: int
    pages: int


class FeedbackCountResponse(BaseModel):
    count: int


class FeedbackStatusUpdate(BaseModel):
    status: str  # "resolved"


class FeedbackStatusResponse(BaseModel):
    id: int
    status: str


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
