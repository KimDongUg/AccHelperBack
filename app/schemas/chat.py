from datetime import datetime

from pydantic import BaseModel


class ChatRequest(BaseModel):
    question: str
    session_id: str
    category: str | None = None
    company_id: int | None = None


class EvidenceItem(BaseModel):
    qa_id: int
    question: str
    answer: str
    category: str | None = None
    similarity: float


class ChatResponse(BaseModel):
    answer: str
    category: str | None = None
    qa_id: int | None = None
    used_rag: bool = False
    evidence_ids: list[int] = []
    similarity_score: float | None = None
    evidences: list[EvidenceItem] = []


class ChatHistoryItem(BaseModel):
    log_id: int | None = None
    user_question: str
    bot_answer: str
    category: str | None = None
    used_rag: bool = False
    timestamp: datetime

    model_config = {"from_attributes": True}
