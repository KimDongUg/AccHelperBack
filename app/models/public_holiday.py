from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from app.database import Base


class PublicHoliday(Base):
    """공공데이터포털 특일 정보 API로 조회한 법정공휴일 캐시. 연 단위 lazy fetch."""
    __tablename__ = "public_holidays"

    id = Column(Integer, primary_key=True, autoincrement=True)
    year = Column(Integer, nullable=False, index=True)
    holiday_date = Column(String(8), nullable=False)  # YYYYMMDD
    name = Column(String(100), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
