from sqlalchemy import Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    Vector = None


class QaEmbedding(Base):
    __tablename__ = "qa_embeddings"
    __table_args__ = (
        Index("ix_qa_embeddings_company_id", "company_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    qa_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True, index=True)
    company_id: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding = mapped_column(Vector(1536), nullable=True) if Vector else mapped_column(Text, nullable=True)
