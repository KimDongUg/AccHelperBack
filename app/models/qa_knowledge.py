from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class QaKnowledge(Base):
    __tablename__ = "qa_knowledge"
    __table_args__ = (
        Index("ix_qa_knowledge_category_is_active", "category", "is_active"),
        Index("ix_qa_knowledge_company_category", "company_id", "category"),
    )

    qa_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(Integer, nullable=False, default=1, index=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    keywords: Mapped[str] = mapped_column(Text, nullable=False, default="")
    aliases: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tags: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
