from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ChatLog(Base):
    __tablename__ = "chat_logs"

    log_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(Integer, nullable=False, default=1, index=True)
    user_question: Mapped[str] = mapped_column(Text, nullable=False)
    bot_answer: Mapped[str] = mapped_column(Text, nullable=False)
    qa_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    session_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_feedback: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
