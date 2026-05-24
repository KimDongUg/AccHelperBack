from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class ComplaintPerson(Base):
    """민원인 테이블 — 민원 등록 시 자동 등록, 동일인 중복 등록 방지."""
    __tablename__ = "complaint_persons"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("companies.company_id", ondelete="CASCADE"), nullable=False, index=True)
    dong = Column(String(20), nullable=False)
    ho = Column(String(20), nullable=False)
    name = Column(String(100), nullable=False)
    phone = Column(String(30), nullable=True)
    first_complained_at = Column(DateTime, server_default=func.now())  # 최초 민원 접수일
    last_complained_at = Column(DateTime, server_default=func.now())   # 최근 민원 접수일
    complaint_count = Column(Integer, default=1)                        # 총 민원 건수
