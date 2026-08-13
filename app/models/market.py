from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from app.database import Base
from app.utils import now_kst


class ApartmentResident(Base):
    __tablename__ = "apartment_residents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    building = Column(String(20), nullable=False)
    unit_number = Column(String(20), nullable=False)
    resident_name = Column(String(100))
    resident_phone = Column(String(30))
    owner_name = Column(String(100))
    owner_phone = Column(String(30))
    company_id = Column(Integer, nullable=True)
    is_self_registered = Column(Boolean, default=False)
    is_verified = Column(Boolean, default=True)
    registered_at = Column(DateTime, default=now_kst)


class MarketPost(Base):
    __tablename__ = "market_posts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, nullable=True)
    category = Column(String(50), nullable=False)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    price = Column(Integer, default=0)
    status = Column(String(30), default="판매중")
    writer_building = Column(String(20), nullable=False)
    writer_unit = Column(String(20), nullable=False)
    is_hidden = Column(Boolean, default=False)
    hidden_reason = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=now_kst)


class MarketImage(Base):
    __tablename__ = "market_images"

    id = Column(Integer, primary_key=True, autoincrement=True)
    post_id = Column(Integer, ForeignKey("market_posts.id", ondelete="CASCADE"), nullable=False)
    image_url = Column(Text, nullable=False)


class MarketComment(Base):
    __tablename__ = "market_comments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    post_id = Column(Integer, ForeignKey("market_posts.id", ondelete="CASCADE"), nullable=False)
    writer_unit = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=now_kst)


class MarketReport(Base):
    __tablename__ = "market_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    post_id = Column(Integer, ForeignKey("market_posts.id", ondelete="CASCADE"), nullable=False)
    reporter_unit = Column(String(20), nullable=False)
    reason = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=now_kst)
