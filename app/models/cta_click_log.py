import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CtaClickLog(Base):
    __tablename__ = "cta_click_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    page_path: Mapped[str] = mapped_column(String(200), nullable=False)
    cta_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    visitor_type: Mapped[str] = mapped_column(String(20), nullable=False, default="unknown")
    referrer: Mapped[str | None] = mapped_column(Text, nullable=True)
    utm_source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    utm_medium: Mapped[str | None] = mapped_column(String(100), nullable=True)
    utm_campaign: Mapped[str | None] = mapped_column(String(100), nullable=True)
    device_type: Mapped[str] = mapped_column(String(20), nullable=False, default="desktop")
    session_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    funnel_step: Mapped[str] = mapped_column(String(30), nullable=False)
