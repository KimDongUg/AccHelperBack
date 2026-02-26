from datetime import datetime

from pydantic import BaseModel


class UnansweredQuestionCreate(BaseModel):
    question: str
    company_id: int
    session_id: str | None = None


class UnansweredQuestionResponse(BaseModel):
    id: int
    question: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class UnansweredQuestionListResponse(BaseModel):
    items: list[UnansweredQuestionResponse]
    page: int
    pages: int
    total: int


class UnansweredQuestionCountResponse(BaseModel):
    count: int


class UnansweredQuestionStatusUpdate(BaseModel):
    status: str  # "resolved" | "dismissed"


class UnansweredQuestionStatusResponse(BaseModel):
    id: int
    status: str
