from datetime import datetime
from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class FeeEntry(Base):
    __tablename__ = "fee_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(Integer, nullable=False, default=1, index=True)
    year_month: Mapped[str] = mapped_column(String(6), nullable=False, index=True)
    dong: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    ho: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    phone: Mapped[str] = mapped_column(String(30), nullable=False, default="")
    fee_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
