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
from app.dependencies import require_admin, require_fee_token
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


# 단지 비교 분석용 비용 항목 그룹 (검침 '요금' 필드는 단가라 총비용 비교에 부적합)
_ELEC_FEE_ITEMS = ['세대전기료', '냉난방동력전기', '공동전기료', '공동전력기금', '세대전력기금', '승강기전기']
_WATER_FEE_ITEMS = ['세대수도료', '공동수도료', '하수도료', '물이용부담금']
_HOTWATER_FEE_ITEMS = ['세대급탕비']


def _normalize(v: str) -> str:
    v = v.strip()
    return v.lstrip("0") or v


# 테스트 용도로 임의 생성한 동호수 — 실제 세대가 아니므로 조회이력/통계/평균 집계에서 항상 제외
_TEST_UNITS = {(1, "1", "9999")}


def _is_test_unit(company_id: int, dong: str, ho: str) -> bool:
    return (company_id, dong, ho) in _TEST_UNITS


def _to_int(v) -> int:
    try:
        return int(str(v).replace(",", ""))
    except (ValueError, TypeError):
        return 0


def _to_float(v):
    try:
        return float(str(v).replace(",", ""))
    except (ValueError, TypeError):
        return None


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
        "exclusive_area": all_items.get("전용면적", ""),
        "billing_items":  billing_items,
        "billing_구분":   billing_구분,
        "summary":        summary,
        "meter":          meter,
        "discounts":      discounts,
    }


def _log_access(db: Session, company_id: int, dong: str, ho: str, request: Request, action: str, success: bool):
    if _is_test_unit(company_id, dong, ho):
        return
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


@router.get("/admin-stats")
def admin_fee_stats(
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """관리자 전용 관리비 조회 통계 (일별/월별/년도별)"""
    from collections import defaultdict
    cid = admin["company_id"]
    if cid == 0:
        raise HTTPException(status_code=400, detail="수퍼관리자는 특정 회사 계정으로 접근하세요.")

    logs = db.query(AccessLog).filter(AccessLog.company_id == cid).all()

    def empty():
        return {"total": 0, "success": 0, "fail": 0}

    daily: dict = defaultdict(empty)
    monthly: dict = defaultdict(empty)
    yearly: dict = defaultdict(empty)

    for log in logs:
        kst = log.created_at
        for key, bucket in [
            (kst.strftime("%Y-%m-%d"), daily),
            (kst.strftime("%Y-%m"),    monthly),
            (kst.strftime("%Y"),       yearly),
        ]:
            bucket[key]["total"] += 1
            if log.success:
                bucket[key]["success"] += 1
            else:
                bucket[key]["fail"] += 1

    def to_list(d, limit=None):
        items = [{"period": k, **v} for k, v in sorted(d.items(), reverse=True)]
        return items[:limit] if limit else items

    return {
        "daily":   to_list(daily,   30),
        "monthly": to_list(monthly, 12),
        "yearly":  to_list(yearly),
    }


@router.get("/admin-log")
def admin_fee_log(
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin),
    limit: int = 100,
    offset: int = 0,
):
    """관리자 전용 관리비 조회 이력 (access_log)"""
    cid = admin["company_id"]
    if cid == 0:
        raise HTTPException(status_code=400, detail="수퍼관리자는 특정 회사 계정으로 접근하세요.")
    q = db.query(AccessLog).filter(AccessLog.company_id == cid)
    total = q.count()
    logs = q.order_by(AccessLog.created_at.desc()).offset(offset).limit(min(limit, 200)).all()
    return {
        "total": total,
        "logs": [
            {
                "id": l.id,
                "dong": l.dong,
                "ho": l.ho,
                "action": l.action,
                "success": l.success,
                "ip": l.ip,
                "created_at": l.created_at.isoformat(),
            }
            for l in logs
        ],
    }


@router.get("/admin-search")
def admin_fee_search(
    request: Request,
    dong: str,
    ho: str,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """관리자 전용 관리비 조회 (OTP 인증 불필요, company_id는 JWT에서 자동 추출)"""
    cid = admin["company_id"]
    if cid == 0:
        raise HTTPException(status_code=400, detail="수퍼관리자는 특정 회사 계정으로 접근하세요.")
    dong_n = _normalize(dong)
    ho_n = _normalize(ho)
    if not dong_n or not ho_n:
        raise HTTPException(status_code=400, detail="동, 호를 입력하세요.")
    entry = (
        db.query(FeeEntry)
        .filter(FeeEntry.company_id == cid, FeeEntry.dong == dong_n, FeeEntry.ho == ho_n)
        .order_by(FeeEntry.uploaded_at.desc())
        .first()
    )
    if not entry:
        _log_access(db, cid, dong_n, ho_n, request, "admin_query", False)
        raise HTTPException(status_code=404, detail="해당 세대의 관리비 데이터를 찾을 수 없습니다.")
    _log_access(db, cid, dong_n, ho_n, request, "admin_query", True)
    return _build_fee_response(entry)


@router.get("/history")
@limiter.limit(RATE_LIMIT_FEE_QUERY)
def get_fee_history(
    request: Request,
    dong: str,
    ho: str,
    company_id: int = 1,
    months: int = 12,
    db: Session = Depends(get_db),
    _auth: dict = Depends(require_fee_token),
):
    """해당 세대 최근 N개월 납부금액 히스토리"""
    dong_n = _normalize(dong)
    ho_n = _normalize(ho)
    entries = (
        db.query(FeeEntry)
        .filter(FeeEntry.company_id == company_id, FeeEntry.dong == dong_n, FeeEntry.ho == ho_n)
        .order_by(FeeEntry.year_month.desc())
        .limit(min(months, 24))
        .all()
    )
    history = []
    for e in reversed(entries):
        resp = _build_fee_response(e)
        amt_str = resp.get("total", "") or ""
        try:
            amt = int(str(amt_str).replace(",", ""))
        except (ValueError, TypeError):
            amt = 0
        history.append({"year_month": e.year_month, "amount": amt})
    return {"history": history}


@router.get("/average")
@limiter.limit(RATE_LIMIT_FEE_QUERY)
def get_fee_average(
    request: Request,
    company_id: int = 1,
    year_month: str = "",
    dong: str = "",
    ho: str = "",
    db: Session = Depends(get_db),
    _auth: dict = Depends(require_fee_token),
):
    """해당 단지의 해당 월 평균 관리비/사용량 (히어로 카드, 사용량 카드 비교용)

    dong/ho가 주어지면 해당 세대와 전용면적이 같은 세대들만 모아 평균을 낸다
    (단지 전체에는 면적이 다른 세대가 섞여 있어 비교가 불공정해지는 문제 보완).
    동일면적 표본이 3건 미만이면 면적 차이가 가장 가까운 세대부터 채워 3건을 확보한다.
    전용면적 데이터가 없는 세대(수집 전 업로드분)는 기존처럼 단지 전체 평균으로 폴백한다.
    """
    if not year_month:
        raise HTTPException(status_code=400, detail="year_month이 필요합니다.")

    all_entries = (
        db.query(FeeEntry)
        .filter(FeeEntry.company_id == company_id, FeeEntry.year_month == year_month)
        .all()
    )
    entries = [e for e in all_entries if not _is_test_unit(company_id, e.dong, e.ho)]
    if not entries:
        return {"amount": None, "electricity_kwh": None, "water_ton": None,
                 "hotwater_ton": None, "electricity_fee": None, "water_fee": None,
                 "hotwater_fee": None, "sample_size": 0, "area": None, "area_match": None}

    dong_n = _normalize(dong)
    ho_n = _normalize(ho)
    my_area = None
    if dong_n and ho_n:
        # 테스트 동호수(1동 9999호, 회사 자체 미리보기용)로 조회할 수도 있으므로
        # 본인 면적은 테스트 동호수 제외 전(all_entries)에서 찾는다 — 평균 대상(entries)은 계속 제외 유지.
        my_entry = next((e for e in all_entries if e.dong == dong_n and e.ho == ho_n), None)
        if my_entry:
            my_items = json.loads(my_entry.fee_json or "{}")
            my_area = _to_float(my_items.get("전용면적"))

    area_match = None
    if my_area is not None:
        with_area = []
        for e in entries:
            items = json.loads(e.fee_json or "{}")
            a = _to_float(items.get("전용면적"))
            if a is not None:
                with_area.append((e, abs(a - my_area)))

        if with_area:
            with_area.sort(key=lambda pair: pair[1])
            exact = [e for e, diff in with_area if diff < 0.01]
            if len(exact) >= 3:
                entries = exact
                area_match = "exact"
            else:
                entries = [e for e, _ in with_area[:3]]
                area_match = "nearby"

    def _category_sum(billing_items: dict, keys: list) -> int:
        return sum(_to_int(billing_items.get(k)) for k in keys)

    amounts, elec, water, hotwater, heating, cooling = [], [], [], [], [], []
    elec_fee, water_fee, hotwater_fee = [], [], []
    for e in entries:
        resp = _build_fee_response(e)
        amt = _to_int(resp.get("total"))
        if amt > 0:
            amounts.append(amt)

        meter = resp.get("meter", {})
        for item, usage_bucket in (("전기", elec), ("수도", water), ("온수", hotwater), ("난방", heating), ("냉방", cooling)):
            m = meter.get(item)
            if not m:
                continue
            # 난방/냉방(Mcal)은 소수점 지침이 있어 _to_int(정수 전용)로는 항상 0이 됨 — _to_float 사용
            cur = _to_float(m.get("당월") or m.get("당월지침")) or 0
            prev = _to_float(m.get("전월") or m.get("전월지침")) or 0
            usage = cur - prev
            if usage > 0:
                usage_bucket.append(usage)

        billing_items = resp.get("billing_items", {})
        ce = _category_sum(billing_items, _ELEC_FEE_ITEMS)
        if ce > 0:
            elec_fee.append(ce)
        cw = _category_sum(billing_items, _WATER_FEE_ITEMS)
        if cw > 0:
            water_fee.append(cw)
        ch = _category_sum(billing_items, _HOTWATER_FEE_ITEMS)
        if ch > 0:
            hotwater_fee.append(ch)

    def _stats(values):
        if not values:
            return None
        return {
            "avg": round(sum(values) / len(values), 1),
            "min": min(values),
            "max": max(values),
        }

    return {
        "amount":          _stats(amounts),
        "electricity_kwh": _stats(elec),
        "water_ton":       _stats(water),
        "hotwater_ton":    _stats(hotwater),
        "heating_mcal":    _stats(heating),
        "cooling_mcal":    _stats(cooling),
        "electricity_fee": _stats(elec_fee),
        "water_fee":       _stats(water_fee),
        "hotwater_fee":    _stats(hotwater_fee),
        "sample_size":     len(entries),
        "area":            my_area,
        "area_match":      area_match,
    }


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
