import json
import logging
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.config import (
    FEE_OTP_LOCKOUT_MINUTES,
    FEE_OTP_MAX_ATTEMPTS,
    FEE_OTP_TTL_MINUTES,
    FEE_TOKEN_TTL_MINUTES,
    RATE_LIMIT_FEE_QUERY,
    RATE_LIMIT_FEE_SMS,
    RATE_LIMIT_FEE_VERIFY,
)
from app.database import get_db
from app.dependencies import require_fee_token
from app.models.access_log import AccessLog
from app.models.fee_data import FeeEntry
from app.models.fee_otp import FeeOtp
from app.rate_limit import limiter
from app.services.auth_service import mask_phone
from app.services.jwt_service import create_access_token
from app.services.solapi_service import send_fee_otp_alimtalk

logger = logging.getLogger("acchelper")
router = APIRouter(prefix="/api/fee", tags=["fee"])

# 고지내역 요약 키 목록 (항목별 부과내역과 구분)
_SUMMARY_KEYS = {
    '관리비소계', '징수대행소계', '연체적용합계', '당월부과합계', '할인총계',
    '미납액', '미납연체료', '공급가액', '부가가치세', '비과세합계', '면세합계',
    '합계(납기내)', '연체료(납기후)', '합계(납기후)',
    '부과항목계', '당월부과액', '절상차액',
}


def _normalize(v: str) -> str:
    v = v.strip()
    return v.lstrip("0") or v


def _build_fee_response(entry: FeeEntry) -> dict:
    """FeeEntry를 관리비 조회 화면용 응답 형태로 가공."""
    all_items = json.loads(entry.fee_json or "{}")

    # ─── 항목별 부과내역 (prefix '항목_') ─────────────────────
    import re as _re
    _ibsheet_id = _re.compile(r'^[A-Z]\d+$')  # A5, B6, C0 등 IBSheet 내부 코드 제외
    billing_items = {}   # { 항목명: 금액 }
    billing_구분  = {}   # { 항목명: "과" | "비" }
    for k, v in all_items.items():
        if k.startswith("항목구분_"):
            label = k[6:]
            if not _ibsheet_id.match(label):
                billing_구분[label] = v
        elif k.startswith("항목_"):
            label = k[3:]  # '항목_' 제거
            if _ibsheet_id.match(label):  # IBSheet 코드 필터링
                continue
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
        "dong":           entry.dong,
        "ho":             entry.ho,
        "name":           entry.name,
        "year_month":     entry.year_month,
        "total":          total_납기내 or total_부과,
        "total_after":    total_납기후,
        "billing_items":  billing_items,
        "billing_구분":   billing_구분,
        "summary":        summary,
        "meter":          meter,
        "discounts":      discounts,
    }


def _log_access(db: Session, company_id: int, dong: str, ho: str, request: Request, action: str, success: bool):
    db.add(AccessLog(
        company_id=company_id,
        dong=dong,
        ho=ho,
        ip=get_remote_address(request),
        user_agent=request.headers.get("user-agent", ""),
        action=action,
        success=success,
    ))
    db.commit()


class SendSmsRequest(BaseModel):
    dong: str
    ho: str
    company_id: int = 1


class VerifyOtpRequest(BaseModel):
    dong: str
    ho: str
    code: str = Field(pattern=r"^\d{6}$")
    company_id: int = 1


@router.post("/send-sms")
@limiter.limit(RATE_LIMIT_FEE_SMS)
def send_sms(req: SendSmsRequest, request: Request, db: Session = Depends(get_db)):
    """동/호 등록된 휴대폰으로 인증번호(알림톡) 발송"""
    company_id = req.company_id
    dong = _normalize(req.dong)
    ho = _normalize(req.ho)

    if not dong or not ho:
        raise HTTPException(status_code=400, detail="동, 호를 입력하세요.")

    entry = (
        db.query(FeeEntry)
        .filter(FeeEntry.company_id == company_id, FeeEntry.dong == dong, FeeEntry.ho == ho)
        .order_by(FeeEntry.uploaded_at.desc())
        .first()
    )
    if not entry or not entry.phone:
        _log_access(db, company_id, dong, ho, request, "send_sms", False)
        return {"success": False, "message": "등록된 세대 정보를 찾을 수 없습니다."}

    now = datetime.utcnow()
    otp = db.query(FeeOtp).filter(
        FeeOtp.company_id == company_id, FeeOtp.dong == dong, FeeOtp.ho == ho
    ).first()

    if otp and otp.locked_until and otp.locked_until > now:
        _log_access(db, company_id, dong, ho, request, "send_sms", False)
        return {"success": False, "message": "인증 시도 횟수를 초과했습니다. 잠시 후 다시 시도해 주세요."}

    code = f"{secrets.randbelow(1_000_000):06d}"
    expires_at = now + timedelta(minutes=FEE_OTP_TTL_MINUTES)

    if otp:
        otp.code = code
        otp.expires_at = expires_at
        otp.fail_count = 0
        otp.locked_until = None
    else:
        db.add(FeeOtp(company_id=company_id, dong=dong, ho=ho, code=code, expires_at=expires_at))

    try:
        sent = send_fee_otp_alimtalk(entry.phone, code, FEE_OTP_TTL_MINUTES)
    except Exception:
        logger.exception("관리비 인증번호 알림톡 발송 실패")
        sent = False

    db.commit()
    _log_access(db, company_id, dong, ho, request, "send_sms", sent)

    return {
        "success": True,
        "message": "인증번호가 발송되었습니다.",
        "masked_phone": mask_phone(entry.phone),
        "expires_in": FEE_OTP_TTL_MINUTES * 60,
    }


@router.post("/verify-otp")
@limiter.limit(RATE_LIMIT_FEE_VERIFY)
def verify_otp(req: VerifyOtpRequest, request: Request, db: Session = Depends(get_db)):
    """인증번호 확인 → 성공 시 관리비 조회용 JWT 발급"""
    company_id = req.company_id
    dong = _normalize(req.dong)
    ho = _normalize(req.ho)
    now = datetime.utcnow()

    otp = db.query(FeeOtp).filter(
        FeeOtp.company_id == company_id, FeeOtp.dong == dong, FeeOtp.ho == ho
    ).first()

    if not otp:
        _log_access(db, company_id, dong, ho, request, "verify", False)
        return {"success": False, "message": "인증번호를 먼저 요청해 주세요."}

    if otp.locked_until and otp.locked_until > now:
        _log_access(db, company_id, dong, ho, request, "verify", False)
        return {"success": False, "message": "인증 시도 횟수를 초과했습니다. 잠시 후 다시 시도해 주세요."}

    if otp.expires_at < now:
        _log_access(db, company_id, dong, ho, request, "verify", False)
        return {"success": False, "message": "인증번호가 만료되었습니다. 다시 요청해 주세요."}

    if not secrets.compare_digest(otp.code, req.code):
        otp.fail_count += 1
        if otp.fail_count >= FEE_OTP_MAX_ATTEMPTS:
            otp.locked_until = now + timedelta(minutes=FEE_OTP_LOCKOUT_MINUTES)
        db.commit()
        _log_access(db, company_id, dong, ho, request, "verify", False)
        return {"success": False, "message": "인증번호가 일치하지 않습니다."}

    db.delete(otp)
    db.commit()
    _log_access(db, company_id, dong, ho, request, "verify", True)

    token = create_access_token(
        {"dong": dong, "ho": ho, "company_id": company_id, "scope": "fee"},
        expire_minutes=FEE_TOKEN_TTL_MINUTES,
    )
    return {"success": True, "token": token, "expires_in": FEE_TOKEN_TTL_MINUTES * 60}


@router.get("")
@limiter.limit(RATE_LIMIT_FEE_QUERY)
def get_fee(
    request: Request,
    dong: str,
    ho: str,
    company_id: int = 1,
    db: Session = Depends(get_db),
    _auth: dict = Depends(require_fee_token),
):
    """인증된 JWT로 관리비 데이터 조회"""
    dong_n = _normalize(dong)
    ho_n = _normalize(ho)

    entry = (
        db.query(FeeEntry)
        .filter(FeeEntry.company_id == company_id, FeeEntry.dong == dong_n, FeeEntry.ho == ho_n)
        .order_by(FeeEntry.uploaded_at.desc())
        .first()
    )

    if not entry:
        _log_access(db, company_id, dong_n, ho_n, request, "fee_query", False)
        raise HTTPException(status_code=404, detail="관리비 데이터를 찾을 수 없습니다.")

    _log_access(db, company_id, dong_n, ho_n, request, "fee_query", True)
    return _build_fee_response(entry)
