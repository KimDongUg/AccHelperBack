from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.utils import now_kst


class DemoLead(Base):
    """메인화면 '체험하기' 신청자 정보 (슈퍼관리자 체험 신청자 목록용)."""

    __tablename__ = "demo_leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(120), nullable=True)
    building_name: Mapped[str] = mapped_column(String(100), nullable=False)  # 아파트(오피스텔)명
    demo_type: Mapped[str] = mapped_column(String(20), nullable=False)  # apt / office
    privacy_agreed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    marketing_agreed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    device_type: Mapped[str] = mapped_column(String(20), nullable=False, default="desktop")
    source: Mapped[str | None] = mapped_column(String(30), nullable=True)  # 어느 버튼에서 신청했는지
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_kst, index=True)
