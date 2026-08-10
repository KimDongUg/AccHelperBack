from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class ChatThread(Base):
    """1:1 톡 스레드 — (company_id, dong, ho)당 열린(open) 스레드는 1개."""
    __tablename__ = "chat_threads"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("companies.company_id", ondelete="CASCADE"), nullable=False, index=True)
    dong = Column(String(20), nullable=False)
    ho = Column(String(20), nullable=False)
    resident_name = Column(String(100), nullable=False)
    resident_phone = Column(String(30), nullable=True)
    status = Column(String(20), nullable=False, default="open")  # open / closed
    claimed_admin_id = Column(Integer, ForeignKey("admin_users.user_id"), nullable=True)
    claimed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    last_message_at = Column(DateTime, server_default=func.now())


class ChatMessage(Base):
    """1:1 톡 메시지."""
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    thread_id = Column(Integer, ForeignKey("chat_threads.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_type = Column(String(10), nullable=False)  # resident / admin
    sender_admin_id = Column(Integer, ForeignKey("admin_users.user_id"), nullable=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    read_at = Column(DateTime, nullable=True)  # resident 메시지에만 의미 있음 (admin 안읽음 배지용)
