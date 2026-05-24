from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class Complaint(Base):
    __tablename__ = "complaints"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("companies.company_id", ondelete="CASCADE"), nullable=False, index=True)
    dong = Column(String(20), nullable=False)
    ho = Column(String(20), nullable=False)
    writer_name = Column(String(100), nullable=False)   # 비공개 — API 응답에서 제외
    writer_phone = Column(String(30), nullable=True)    # 비공개 — 관리자만 확인 가능
    privacy_agreed_at = Column(DateTime, nullable=True) # 개인정보 동의 시각 (법적 근거 보관)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    # 첨부 이미지 (선택, 최대 2장)
    image1_url = Column(String(500), nullable=True)
    image2_url = Column(String(500), nullable=True)

    # 관리자 답변
    reply_content = Column(Text, nullable=True)
    replied_at = Column(DateTime, nullable=True)

    # 관리자 삭제
    is_deleted = Column(Boolean, default=False)
    delete_reason = Column(Text, nullable=True)
    deleted_at = Column(DateTime, nullable=True)
