from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BillingKey(Base):
    """토스페이먼츠 빌링키 저장 테이블"""

    __tablename__ = "billing_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    customer_key: Mapped[str] = mapped_column(String(100), nullable=False)
    billing_key: Mapped[str] = mapped_column(String(200), nullable=False)
    card_company: Mapped[str | None] = mapped_column(String(50), nullable=True)
    card_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PaymentHistory(Base):
    """결제 내역 테이블"""

    __tablename__ = "payment_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    billing_key_id: Mapped[int] = mapped_column(Integer, nullable=False)
    order_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    order_name: Mapped[str] = mapped_column(String(200), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # success, failed
    payment_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    paid_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
