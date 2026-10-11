from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.utils import now_kst


class PageVisitLog(Base):
    """랜딩페이지/샘플 체험 페이지 접속 기록 (슈퍼관리자 접속자 현황용)."""

    __tablename__ = "page_visit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    page: Mapped[str] = mapped_column(String(30), nullable=False, index=True)  # landing / sample_apt / sample_office
    visitor_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    device_type: Mapped[str] = mapped_column(String(20), nullable=False, default="desktop")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_kst, index=True)
