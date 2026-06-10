from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class FeeOtp(Base):
    """관리비 조회 SMS 인증번호 (동/호당 1개의 활성 레코드를 upsert)."""

    __tablename__ = "fee_otp"
    __table_args__ = (UniqueConstraint("dong", "ho", name="uq_fee_otp_dong_ho"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dong: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    ho: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(6), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    fail_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
