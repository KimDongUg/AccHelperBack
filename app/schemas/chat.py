from datetime import datetime

from pydantic import BaseModel


class ChatRequest(BaseModel):
    question: str
    session_id: str
    category: str | None = None
    company_code: str | None = None


class ChatResponse(BaseModel):
    answer: str
    category: str | None = None
    qa_id: int | None = None


class ChatHistoryItem(BaseModel):
    user_question: str
    bot_answer: str
    category: str | None = None
    timestamp: datetime

    model_config = {"from_attributes": True}
