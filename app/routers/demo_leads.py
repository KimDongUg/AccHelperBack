"""메인화면 '체험하기' 신청 (channel.io 데모 방식) — 공개 등록 API."""

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.demo_lead import DemoLead
from app.rate_limit import limiter
from app.utils import now_kst

logger = logging.getLogger("acchelper")

router = APIRouter(tags=["demo-leads"])

DEMO_TYPES = {"apt": "샘플아파트", "office": "샘플오피스텔"}
ALLOWED_DEVICE_TYPES = {"mobile", "tablet", "desktop"}
PHONE_RE = re.compile(r"^01[016789]\d{7,8}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class DemoLeadCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    phone: str = Field(..., min_length=10, max_length=20)
    email: str | None = Field(None, max_length=120)
    building_name: str = Field(..., min_length=1, max_length=100)
    demo_type: str = Field(..., max_length=20)
    privacy_agreed: bool
    marketing_agreed: bool = False
    device_type: str = Field("desktop", max_length=20)
    source: str | None = Field(None, max_length=30)


def _client_ip(request: Request) -> str | None:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()[:45]
    return request.client.host if request.client else None


@router.post("/api/demo-leads", status_code=201)
@limiter.limit("5/minute;30/day")
def create_demo_lead(data: DemoLeadCreate, request: Request, db: Session = Depends(get_db)):
    """체험하기 신청 정보 저장. 인증 불필요."""
    name = data.name.strip()
    building = data.building_name.strip()
    phone = re.sub(r"\D", "", data.phone)
    email = (data.email or "").strip() or None

    if not data.privacy_agreed:
        raise HTTPException(status_code=400, detail="개인정보 수집·이용에 동의해 주세요.")
    if not name or not building:
        raise HTTPException(status_code=400, detail="이름과 아파트(오피스텔)명을 입력해 주세요.")
    if not PHONE_RE.match(phone):
        raise HTTPException(status_code=400, detail="휴대폰 번호를 정확히 입력해 주세요.")
    if email and not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="이메일 형식이 올바르지 않습니다.")
    if data.demo_type not in DEMO_TYPES:
        raise HTTPException(status_code=400, detail="체험 유형을 선택해 주세요.")

    lead = DemoLead(
        name=name,
        phone=phone,
        email=email,
        building_name=building,
        demo_type=data.demo_type,
        privacy_agreed=True,
        marketing_agreed=data.marketing_agreed,
        device_type=data.device_type if data.device_type in ALLOWED_DEVICE_TYPES else "desktop",
        source=(data.source or None),
        ip_address=_client_ip(request),
        created_at=now_kst(),
    )
    db.add(lead)
    db.commit()
    logger.info("체험 신청 | id=%s | type=%s | source=%s", lead.id, lead.demo_type, lead.source)
    return {"success": True, "id": lead.id}
