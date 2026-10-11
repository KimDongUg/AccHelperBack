import logging
from datetime import timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.page_visit_log import PageVisitLog
from app.utils import now_kst

logger = logging.getLogger("acchelper")

router = APIRouter(tags=["visits"])

# 접속자 현황 집계 대상 페이지
VISIT_PAGES = {
    "landing": "랜딩페이지",
    "sample_apt": "샘플아파트 체험하기",
    "sample_office": "샘플오피스텔 체험하기",
}
ALLOWED_DEVICE_TYPES = {"mobile", "tablet", "desktop"}

# 같은 방문자의 같은 페이지 기록이 이 시간 안에 반복되면 무시 (연타/중복 호출 방지)
DUPLICATE_WINDOW = timedelta(seconds=10)


class PageVisitCreate(BaseModel):
    page: str = Field(..., max_length=30)
    visitor_id: str = Field(..., min_length=8, max_length=64)
    device_type: str = Field("desktop", max_length=20)


@router.post("/api/visits", status_code=201)
def create_page_visit(data: PageVisitCreate, db: Session = Depends(get_db)):
    """공개 페이지 접속 기록. 인증 불필요, 실패해도 화면에는 영향 없도록 에러를 삼킨다."""
    if data.page not in VISIT_PAGES:
        return {"detail": "ignored"}
    try:
        now = now_kst()
        recent = (
            db.query(PageVisitLog.id)
            .filter(
                PageVisitLog.page == data.page,
                PageVisitLog.visitor_id == data.visitor_id,
                PageVisitLog.created_at >= now - DUPLICATE_WINDOW,
            )
            .first()
        )
        if recent:
            return {"detail": "duplicate"}
        db.add(PageVisitLog(
            page=data.page,
            visitor_id=data.visitor_id,
            device_type=data.device_type if data.device_type in ALLOWED_DEVICE_TYPES else "desktop",
            created_at=now,
        ))
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning("페이지 접속 기록 실패 | page=%s | %s", data.page, e)
    return {"detail": "logged"}
