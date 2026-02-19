import logging
import time
from base64 import b64encode
from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import SITE_URL, TOSS_CLIENT_KEY, TOSS_SECRET_KEY
from app.database import get_db
from app.dependencies import require_admin, require_auth
from app.models.billing import BillingKey, PaymentHistory
from app.models.company import Company
from app.schemas.billing import (
    BillingCancelResponse,
    BillingKeyDeactivateResponse,
    BillingPayRequest,
    BillingPayResponse,
    BillingStatusResponse,
    BillingTrialResponse,
    PaymentHistoryItem,
    PaymentHistoryResponse,
)

logger = logging.getLogger("acchelper")

router = APIRouter(prefix="/api/billing", tags=["billing"])

TOSS_API_BASE = "https://api.tosspayments.com/v1"


@router.get("/client-key")
def get_toss_client_key():
    """프론트엔드에 토스 Client Key 전달"""
    return {"clientKey": TOSS_CLIENT_KEY}

PRICE_DISCOUNTED = 100     # TODO: 테스트 후 24500으로 복원
PRICE_FULL = 49000         # 10개 초과: 정가
MAX_DISCOUNT_COMPANIES = 10


def _calculate_amount(db: Session) -> int:
    """활성 구독(enterprise) 회사 수 기반 결제 금액 계산"""
    enterprise_count = (
        db.query(Company)
        .filter(Company.subscription_plan == "enterprise", Company.deleted_at == None)
        .count()
    )
    if enterprise_count < MAX_DISCOUNT_COMPANIES:
        return PRICE_DISCOUNTED
    return PRICE_FULL


def _toss_auth_header() -> dict:
    """토스페이먼츠 Basic 인증 헤더 생성"""
    encoded = b64encode(f"{TOSS_SECRET_KEY}:".encode()).decode()
    return {
        "Authorization": f"Basic {encoded}",
        "Content-Type": "application/json",
    }


# ──────────────────────────────────────────────
# 1단계: 카드 등록 콜백 (프론트에서 리다이렉트됨)
# ──────────────────────────────────────────────


@router.get("/success")
async def billing_success(
    customerKey: str = Query(...),
    authKey: str = Query(...),
    db: Session = Depends(get_db),
):
    """토스 카드 등록 성공 콜백 → billingKey 발급/저장 → 첫 결제 실행 → 리다이렉트"""
    try:
        # 1) billingKey 발급
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{TOSS_API_BASE}/billing/authorizations/issue",
                json={"customerKey": customerKey, "authKey": authKey},
                headers=_toss_auth_header(),
                timeout=30.0,
            )

        if resp.status_code != 200:
            logger.error("Toss billingKey issue failed: %s", resp.text)
            return RedirectResponse(
                url=f"/billing.html?status=fail&message=billingKey+발급+실패",
                status_code=302,
            )

        data = resp.json()
        billing_key = data["billingKey"]
        card_info = data.get("card", {})

        # customerKey 형식: company_{company_id}
        company_id = int(customerKey.split("_")[1])

        # 2) 기존 빌링키 비활성화
        existing = (
            db.query(BillingKey)
            .filter(BillingKey.company_id == company_id, BillingKey.is_active == True)
            .all()
        )
        for bk in existing:
            bk.is_active = False
            bk.deactivated_at = datetime.utcnow()

        # 3) 새 빌링키 저장
        new_bk = BillingKey(
            company_id=company_id,
            customer_key=customerKey,
            billing_key=billing_key,
            card_company=card_info.get("company"),
            card_number=card_info.get("number"),
            is_active=True,
        )
        db.add(new_bk)
        db.flush()  # new_bk.id 확보

        # 4) 첫 결제 즉시 실행
        order_id = f"order_{company_id}_{int(time.time())}"
        pay_amount = _calculate_amount(db)
        pay_order_name = "보듬누리 구독"

        # 회사명 조회 (토스 구매자명에 표시)
        company = db.query(Company).filter(Company.company_id == company_id).first()
        customer_name = company.company_name if company else f"company_{company_id}"

        async with httpx.AsyncClient() as client:
            pay_resp = await client.post(
                f"{TOSS_API_BASE}/billing/{billing_key}",
                json={
                    "customerKey": customerKey,
                    "amount": pay_amount,
                    "orderId": order_id,
                    "orderName": pay_order_name,
                    "customerName": customer_name,
                },
                headers=_toss_auth_header(),
                timeout=30.0,
            )

        pay_result = pay_resp.json()

        if pay_resp.status_code == 200:
            # 결제 성공 → DB 기록 + 구독 업그레이드
            history = PaymentHistory(
                company_id=company_id,
                billing_key_id=new_bk.id,
                order_id=order_id,
                order_name=pay_order_name,
                amount=pay_amount,
                status="success",
                payment_key=pay_result.get("paymentKey"),
            )
            db.add(history)

            company = db.query(Company).filter(Company.company_id == company_id).first()
            if company:
                company.subscription_plan = "enterprise"
                company.max_qa_count = 1000
                company.max_admins = 50

            db.commit()
            logger.info("BillingKey saved + first payment success: company_id=%d, order_id=%s", company_id, order_id)
            return RedirectResponse(url="/billing.html?status=success", status_code=302)
        else:
            # 결제 실패 → 빌링키는 저장하되 결제 실패 기록
            failure_msg = pay_result.get("message", "결제 실패")
            history = PaymentHistory(
                company_id=company_id,
                billing_key_id=new_bk.id,
                order_id=order_id,
                order_name=pay_order_name,
                amount=pay_amount,
                status="failed",
                failure_reason=failure_msg,
            )
            db.add(history)
            db.commit()

            logger.warning("BillingKey saved but payment failed: company_id=%d, reason=%s", company_id, failure_msg)
            return RedirectResponse(
                url=f"/billing.html?status=fail&message=결제+실패:+{failure_msg}",
                status_code=302,
            )

    except Exception as exc:
        logger.error("billing_success error: %s", exc)
        return RedirectResponse(
            url=f"/billing.html?status=fail&message={exc}",
            status_code=302,
        )


@router.get("/fail")
async def billing_fail(
    code: str = Query(""),
    message: str = Query(""),
):
    """토스 카드 등록 실패 콜백 → /billing.html로 리다이렉트"""
    logger.warning("Toss billing auth failed: code=%s, message=%s", code, message)
    return RedirectResponse(
        url=f"/billing.html?status=fail&code={code}&message={message}",
        status_code=302,
    )


# ──────────────────────────────────────────────
# 2단계: 자동결제 실행
# ──────────────────────────────────────────────


@router.post("/pay", response_model=BillingPayResponse)
async def billing_pay(
    req: BillingPayRequest,
    request: Request,
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """저장된 billingKey로 결제 실행"""

    bk = (
        db.query(BillingKey)
        .filter(BillingKey.company_id == req.company_id, BillingKey.is_active == True)
        .first()
    )
    if not bk:
        return BillingPayResponse(success=False, message="등록된 카드가 없습니다. 먼저 카드를 등록해주세요.")

    order_id = f"order_{req.company_id}_{int(time.time())}"

    # 금액: 프론트에서 전달하지 않으면 서버에서 자동 계산
    pay_amount = req.amount if req.amount is not None else _calculate_amount(db)

    # 회사명 조회 (토스 구매자명에 표시)
    company = db.query(Company).filter(Company.company_id == req.company_id).first()
    customer_name = company.company_name if company else f"company_{req.company_id}"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{TOSS_API_BASE}/billing/{bk.billing_key}",
                json={
                    "customerKey": bk.customer_key,
                    "amount": pay_amount,
                    "orderId": order_id,
                    "orderName": req.order_name,
                    "customerName": customer_name,
                },
                headers=_toss_auth_header(),
                timeout=30.0,
            )

        result = resp.json()

        if resp.status_code == 200:
            # 결제 성공
            history = PaymentHistory(
                company_id=req.company_id,
                billing_key_id=bk.id,
                order_id=order_id,
                order_name=req.order_name,
                amount=pay_amount,
                status="success",
                payment_key=result.get("paymentKey"),
            )
            db.add(history)
            db.commit()

            logger.info("Payment success: company_id=%d, order_id=%s", req.company_id, order_id)
            return BillingPayResponse(
                success=True,
                message="결제가 완료되었습니다.",
                payment_key=result.get("paymentKey"),
                order_id=order_id,
                amount=pay_amount,
            )
        else:
            # 결제 실패
            failure_msg = result.get("message", "결제 실패")
            history = PaymentHistory(
                company_id=req.company_id,
                billing_key_id=bk.id,
                order_id=order_id,
                order_name=req.order_name,
                amount=pay_amount,
                status="failed",
                failure_reason=failure_msg,
            )
            db.add(history)
            db.commit()

            logger.warning("Payment failed: company_id=%d, reason=%s", req.company_id, failure_msg)
            return BillingPayResponse(success=False, message=failure_msg)

    except Exception as exc:
        logger.error("billing_pay error: %s", exc)
        return BillingPayResponse(success=False, message=f"결제 처리 중 오류: {exc}")


# ──────────────────────────────────────────────
# 조회 엔드포인트
# ──────────────────────────────────────────────


@router.get("/status", response_model=BillingStatusResponse)
def billing_status(
    company_id: int = Query(...),
    request: Request = None,
    user: dict = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """회사의 빌링 상태 조회"""

    bk = (
        db.query(BillingKey)
        .filter(BillingKey.company_id == company_id, BillingKey.is_active == True)
        .first()
    )
    company = db.query(Company).filter(Company.company_id == company_id).first()

    trial_ends = None
    if company and company.trial_ends_at:
        trial_ends = company.trial_ends_at.isoformat() + "Z"

    # active = 유료 구독 중이거나 체험 기간 내
    is_active = False
    if company:
        if company.subscription_plan == "enterprise":
            is_active = True
        elif company.subscription_plan == "trial" and company.trial_ends_at:
            is_active = company.trial_ends_at > datetime.utcnow()

    return BillingStatusResponse(
        success=True,
        active=is_active,
        has_billing_key=bk is not None,
        card_company=bk.card_company if bk else None,
        card_number=bk.card_number if bk else None,
        subscription_plan=company.subscription_plan if company else None,
        trial_ends_at=trial_ends,
    )


@router.get("/history", response_model=PaymentHistoryResponse)
def billing_history(
    company_id: int = Query(...),
    request: Request = None,
    user: dict = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """결제 내역 조회"""

    payments = (
        db.query(PaymentHistory)
        .filter(PaymentHistory.company_id == company_id)
        .order_by(PaymentHistory.paid_at.desc())
        .limit(50)
        .all()
    )

    return PaymentHistoryResponse(
        success=True,
        payments=[
            PaymentHistoryItem(
                order_id=p.order_id,
                order_name=p.order_name,
                amount=p.amount,
                status=p.status,
                payment_key=p.payment_key,
                failure_reason=p.failure_reason,
                paid_at=p.paid_at.isoformat() + "Z",
            )
            for p in payments
        ],
    )


@router.post("/deactivate", response_model=BillingKeyDeactivateResponse)
def billing_deactivate(
    company_id: int = Query(...),
    request: Request = None,
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """카드 등록 해제 (구독 취소)"""

    bk_list = (
        db.query(BillingKey)
        .filter(BillingKey.company_id == company_id, BillingKey.is_active == True)
        .all()
    )
    if not bk_list:
        return BillingKeyDeactivateResponse(success=False, message="등록된 카드가 없습니다.")

    for bk in bk_list:
        bk.is_active = False
        bk.deactivated_at = datetime.utcnow()

    # 구독 다운그레이드
    company = db.query(Company).filter(Company.company_id == company_id).first()
    if company:
        company.subscription_plan = "free"
        company.max_qa_count = 100
        company.max_admins = 5

    db.commit()

    logger.info("BillingKey deactivated for company_id=%d", company_id)
    return BillingKeyDeactivateResponse(success=True, message="구독이 해지되었습니다.")


@router.post("/trial", response_model=BillingTrialResponse)
def billing_trial(
    company_id: int = Query(...),
    request: Request = None,
    user: dict = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """14일 무료체험 시작"""

    company = db.query(Company).filter(Company.company_id == company_id).first()
    if not company:
        return BillingTrialResponse(success=False, message="회사를 찾을 수 없습니다.")

    # 이미 유료 구독 중이면 거부
    if company.subscription_plan == "enterprise":
        return BillingTrialResponse(success=False, message="이미 구독 중입니다.")

    # 이미 체험 사용했으면 거부
    if company.trial_ends_at is not None:
        return BillingTrialResponse(success=False, message="무료체험은 1회만 가능합니다.")

    # 14일 무료체험 시작
    trial_end = datetime.utcnow() + timedelta(days=14)
    company.subscription_plan = "trial"
    company.trial_ends_at = trial_end
    company.max_qa_count = 1000
    company.max_admins = 50
    db.commit()

    logger.info("Trial started for company_id=%d, ends_at=%s", company_id, trial_end)
    return BillingTrialResponse(
        success=True,
        message="14일 무료체험이 시작되었습니다.",
        trial_ends_at=trial_end.isoformat() + "Z",
    )


@router.post("/cancel", response_model=BillingCancelResponse)
def billing_cancel(
    company_id: int = Query(...),
    request: Request = None,
    user: dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """구독 해지 (카드 비활성화 + free 다운그레이드)"""

    company = db.query(Company).filter(Company.company_id == company_id).first()
    if not company:
        return BillingCancelResponse(success=False, message="회사를 찾을 수 없습니다.")

    if company.subscription_plan == "free":
        return BillingCancelResponse(success=False, message="현재 구독 중이 아닙니다.")

    # 빌링키 비활성화
    bk_list = (
        db.query(BillingKey)
        .filter(BillingKey.company_id == company_id, BillingKey.is_active == True)
        .all()
    )
    for bk in bk_list:
        bk.is_active = False
        bk.deactivated_at = datetime.utcnow()

    # free로 다운그레이드
    company.subscription_plan = "free"
    company.max_qa_count = 100
    company.max_admins = 5
    db.commit()

    logger.info("Subscription cancelled for company_id=%d", company_id)
    return BillingCancelResponse(success=True, message="구독이 해지되었습니다.")


