from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TenantQuota(Base):
    __tablename__ = "tenant_quotas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    monthly_chat_cnt: Mapped[int] = mapped_column(Integer, default=50)
    monthly_tokens: Mapped[int] = mapped_column(Integer, default=20000)
    monthly_embed_cnt: Mapped[int] = mapped_column(Integer, default=100)
