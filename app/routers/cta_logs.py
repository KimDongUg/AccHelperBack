import logging
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.cta_click_log import CtaClickLog

logger = logging.getLogger("acchelper")

router = APIRouter(tags=["cta-logs"])

ALLOWED_CTA_TYPES = {
    "kakao_intro",
    "kakao_demo",
    "kakao_pricing",
    "kakao_case",
    "kakao_manager_consult",
    "kakao_manager_intro",
    "kakao_manager_pricing",
    "kakao_manager_process",
    "kakao_quick",
}

ALLOWED_FUNNEL_STEPS = {
    "impression",
    "click",
    "modal_open",
    "kakao_redirect",
}

ALLOWED_VISITOR_TYPES = {"manager", "general", "unknown"}
ALLOWED_DEVICE_TYPES = {"mobile", "tablet", "desktop"}


class CtaClickLogCreate(BaseModel):
    page_path: str = Field(..., max_length=200)
    cta_type: str = Field(..., max_length=50)
    visitor_type: str = Field("unknown", max_length=20)
    referrer: Optional[str] = None
    utm_source: Optional[str] = Field(None, max_length=100)
    utm_medium: Optional[str] = Field(None, max_length=100)
    utm_campaign: Optional[str] = Field(None, max_length=100)
    device_type: str = Field("desktop", max_length=20)
    session_id: str = Field(..., max_length=100)
    funnel_step: str = Field(..., max_length=30)


@router.post("/api/cta-logs", status_code=201)
def create_cta_click_log(
    data: CtaClickLogCreate,
    db: Session = Depends(get_db),
):
    """Log a CTA click event. No auth required (public pages).

    Failures are swallowed so the user is never blocked from navigating to Kakao.
    """
    try:
        # Validate cta_type
        if data.cta_type not in ALLOWED_CTA_TYPES:
            return {"detail": "logged", "warning": "unknown cta_type"}

        # Validate funnel_step
        if data.funnel_step not in ALLOWED_FUNNEL_STEPS:
            return {"detail": "logged", "warning": "unknown funnel_step"}

        # Normalize visitor_type / device_type with fallback
        visitor_type = data.visitor_type if data.visitor_type in ALLOWED_VISITOR_TYPES else "unknown"
        device_type = data.device_type if data.device_type in ALLOWED_DEVICE_TYPES else "desktop"

        log = CtaClickLog(
            page_path=data.page_path,
            cta_type=data.cta_type,
            visitor_type=visitor_type,
            referrer=data.referrer,
            utm_source=data.utm_source,
            utm_medium=data.utm_medium,
            utm_campaign=data.utm_campaign,
            device_type=device_type,
            session_id=data.session_id,
            funnel_step=data.funnel_step,
        )
        db.add(log)
        db.commit()

        return {"detail": "logged", "id": log.id}
    except Exception as exc:
        logger.warning("CTA click log failed: %s", exc)
        # Never block the user — return 200 on failure
        return {"detail": "logged"}
