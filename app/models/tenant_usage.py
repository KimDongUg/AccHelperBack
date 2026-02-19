from sqlalchemy import Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TenantUsageMonthly(Base):
    __tablename__ = "tenant_usage_monthly"
    __table_args__ = (
        Index("ix_tenant_usage_company_month", "company_id", "yyyymm", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    yyyymm: Mapped[str] = mapped_column(String(7), nullable=False)
    chat_cnt: Mapped[int] = mapped_column(Integer, default=0)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    embed_cnt: Mapped[int] = mapped_column(Integer, default=0)
