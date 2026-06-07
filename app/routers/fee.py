import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.fee_data import FeeEntry

logger = logging.getLogger("acchelper")
router = APIRouter(prefix="/api/fee", tags=["fee"])

# 고지내역 요약 키 목록 (항목별 부과내역과 구분)
_SUMMARY_KEYS = {
    '관리비소계', '징수대행소계', '연체적용합계', '당월부과합계', '할인총계',
    '미납액', '미납연체료', '공급가액', '부가가치세', '비과세합계', '면세합계',
    '합계(납기내)', '연체료(납기후)', '합계(납기후)',
    '부과항목계', '당월부과액', '절상차액',
}


class FeeVerifyRequest(BaseModel):
    dong: str
    ho: str
    name: str
    phone: str


@router.post("/verify")
def verify_fee(req: FeeVerifyRequest, db: Session = Depends(get_db)):
    """동호수 + 이름(LIKE) + 휴대폰으로 관리비 조회"""
    dong  = req.dong.strip().lstrip("0") or req.dong.strip()
    ho    = req.ho.strip().lstrip("0")   or req.ho.strip()
    name  = req.name.strip()
    phone = req.phone.strip().replace("-", "").replace(" ", "")

    if not all([dong, ho, name, phone]):
        raise HTTPException(status_code=400, detail="동, 호, 이름, 휴대폰을 모두 입력하세요.")

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

    phone_tail = phone[-8:] if len(phone) >= 8 else phone
    matched = None
    for entry in entries:
        stored = entry.phone.replace("-", "").replace(" ", "")
        if stored == phone or stored.endswith(phone_tail):
            matched = entry
            break

    if not matched:
        raise HTTPException(status_code=403, detail="휴대폰 번호가 일치하지 않습니다.")

    all_items = json.loads(matched.fee_json or "{}")

    # ─── 항목별 부과내역 (prefix '항목_') ─────────────────────
    billing_items = {}
    for k, v in all_items.items():
        if k.startswith("항목_"):
            label = k[3:]  # '항목_' 제거
            billing_items[label] = v

    # ─── 검침내역 (prefix '검침_') ────────────────────────────
    meter = {}
    for k, v in all_items.items():
        if k.startswith("검침_"):
            parts = k.split("_", 2)
            if len(parts) == 3:
                item, field = parts[1], parts[2]
                if item not in meter:
                    meter[item] = {}
                meter[item][field] = v

    # ─── 고지내역 요약 (나머지) ───────────────────────────────
    summary = {k: v for k, v in all_items.items()
               if k in _SUMMARY_KEYS and not k.startswith("항목_") and not k.startswith("검침_")}

    # ─── 할인내역 ────────────────────────────────────────────
    discounts = {}
    for k, v in all_items.items():
        if k.startswith("할인_"):
            discounts[k[3:]] = v

    total_납기내  = summary.get("합계(납기내)", "")
    total_부과    = summary.get("당월부과합계", summary.get("당월부과액", ""))
    total_납기후  = summary.get("합계(납기후)", "")

    return {
        "dong":           matched.dong,
        "ho":             matched.ho,
        "name":           matched.name,
        "year_month":     matched.year_month,
        "total":          total_납기내 or total_부과,
        "total_after":    total_납기후,
        "billing_items":  billing_items,
        "summary":        summary,
        "meter":          meter,
        "discounts":      discounts,
    }
