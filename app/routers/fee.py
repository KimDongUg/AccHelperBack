import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.fee_data import FeeEntry

logger = logging.getLogger("acchelper")
router = APIRouter(prefix="/api/fee", tags=["fee"])


class FeeVerifyRequest(BaseModel):
    dong: str
    ho: str
    name: str
    phone: str


@router.post("/verify")
def verify_fee(req: FeeVerifyRequest, db: Session = Depends(get_db)):
    """동호수 + 이름(LIKE) + 전화번호로 관리비 조회"""
    dong  = req.dong.strip().lstrip("0") or req.dong.strip()
    ho    = req.ho.strip().lstrip("0")   or req.ho.strip()
    name  = req.name.strip()
    phone = req.phone.strip().replace("-", "").replace(" ", "")

    if not all([dong, ho, name, phone]):
        raise HTTPException(status_code=400, detail="동, 호, 이름, 전화번호를 모두 입력하세요.")

    entries = (
        db.query(FeeEntry)
        .filter(
            FeeEntry.dong == dong,
            FeeEntry.ho   == ho,
            FeeEntry.name.ilike(f"%{name}%"),
        )
        .order_by(FeeEntry.uploaded_at.desc())
        .all()
    )

    if not entries:
        raise HTTPException(status_code=404, detail="입력하신 정보와 일치하는 데이터가 없습니다.")

    # 전화번호 뒷자리 8자리로 매칭 (앞 지역번호 생략 허용)
    matched = None
    phone_tail = phone[-8:] if len(phone) >= 8 else phone
    for entry in entries:
        stored = entry.phone.replace("-", "").replace(" ", "")
        if stored == phone or stored.endswith(phone_tail):
            matched = entry
            break

    if not matched:
        raise HTTPException(status_code=403, detail="전화번호가 일치하지 않습니다.")

    fee_items = json.loads(matched.fee_json or "{}")

    # 고지항목 / 검침내역 / 요약 분리
    billing = {k: v for k, v in fee_items.items()
               if not k.startswith("검침_") and k not in ("부과항목계", "당월부과액", "절상차액")}
    meter   = {}
    for k, v in fee_items.items():
        if k.startswith("검침_"):
            # "검침_전기_전월" → item="전기", field="전월"
            parts = k.split("_", 2)
            if len(parts) == 3:
                item, field = parts[1], parts[2]
                if item not in meter:
                    meter[item] = {}
                meter[item][field] = v

    return {
        "dong": matched.dong,
        "ho": matched.ho,
        "name": matched.name,
        "year_month": matched.year_month,
        "total": fee_items.get("당월부과액", ""),
        "billing": billing,
        "meter": meter,
    }
