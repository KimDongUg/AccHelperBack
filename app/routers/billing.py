import logging
import time
from base64 import b64encode
from datetime import datetime

import httpx
from fastapi import APIRouter, Cookie, Depends, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import SITE_URL, TOSS_SECRET_KEY
from app.database import get_db
from app.models.billing import BillingKey, PaymentHistory
from app.models.company import Company
from app.routers.auth import get_current_user
from app.schemas.billing import (
    BillingKeyDeactivateResponse,
    BillingPayRequest,
    BillingPayResponse,
    BillingStatusResponse,
    PaymentHistoryItem,
    PaymentHistoryResponse,
)

logger = logging.getLogger("acchelper")

router = APIRouter(prefix="/api/billing", tags=["billing"])

TOSS_API_BASE = "https://api.tosspayments.com/v1"


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
    """토스 카드 등록 성공 콜백 → billingKey 발급 및 저장 → /billing.html로 리다이렉트"""
    try:
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
                url=f"/billing.html?status=fail&message=토스+응답+오류:+{resp.status_code}",
                status_code=302,
            )

        data = resp.json()
        billing_key = data["billingKey"]
        card_info = data.get("card", {})

        # customerKey 형식: company_{company_id}
        company_id = int(customerKey.split("_")[1])

        # 기존 빌링키 비활성화
        existing = (
            db.query(BillingKey)
            .filter(BillingKey.company_id == company_id, BillingKey.is_active == True)
            .all()
        )
        for bk in existing:
            bk.is_active = False
            bk.deactivated_at = datetime.utcnow()

        # 새 빌링키 저장
        new_bk = BillingKey(
            company_id=company_id,
            customer_key=customerKey,
            billing_key=billing_key,
            card_company=card_info.get("company"),
            card_number=card_info.get("number"),
            is_active=True,
        )
        db.add(new_bk)

        # 구독 플랜 업그레이드
        company = db.query(Company).filter(Company.company_id == company_id).first()
        if company and company.subscription_plan == "free":
            company.subscription_plan = "enterprise"
            company.max_qa_count = 1000
            company.max_admins = 50

        db.commit()

        logger.info("BillingKey saved for company_id=%d", company_id)
        return RedirectResponse(url="/billing.html?status=success", status_code=302)

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
    session_token: str | None = Cookie(None),
    db: Session = Depends(get_db),
):
    """저장된 billingKey로 결제 실행"""
    user = get_current_user(session_token)
    if not user:
        return BillingPayResponse(success=False, message="로그인이 필요합니다.")

    # admin 이상만 결제 가능
    if user["role"] not in ("admin", "super_admin"):
        return BillingPayResponse(success=False, message="결제 권한이 없습니다.")

    bk = (
        db.query(BillingKey)
        .filter(BillingKey.company_id == req.company_id, BillingKey.is_active == True)
        .first()
    )
    if not bk:
        return BillingPayResponse(success=False, message="등록된 카드가 없습니다. 먼저 카드를 등록해주세요.")

    order_id = f"order_{req.company_id}_{int(time.time())}"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{TOSS_API_BASE}/billing/{bk.billing_key}",
                json={
                    "customerKey": bk.customer_key,
                    "amount": req.amount,
                    "orderId": order_id,
                    "orderName": req.order_name,
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
                amount=req.amount,
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
                amount=req.amount,
            )
        else:
            # 결제 실패
            failure_msg = result.get("message", "결제 실패")
            history = PaymentHistory(
                company_id=req.company_id,
                billing_key_id=bk.id,
                order_id=order_id,
                order_name=req.order_name,
                amount=req.amount,
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
    session_token: str | None = Cookie(None),
    db: Session = Depends(get_db),
):
    """회사의 빌링 상태 조회"""
    user = get_current_user(session_token)
    if not user:
        return BillingStatusResponse(success=False)

    bk = (
        db.query(BillingKey)
        .filter(BillingKey.company_id == company_id, BillingKey.is_active == True)
        .first()
    )
    company = db.query(Company).filter(Company.company_id == company_id).first()

    return BillingStatusResponse(
        success=True,
        has_billing_key=bk is not None,
        card_company=bk.card_company if bk else None,
        card_number=bk.card_number if bk else None,
        subscription_plan=company.subscription_plan if company else None,
    )


@router.get("/history", response_model=PaymentHistoryResponse)
def billing_history(
    company_id: int = Query(...),
    session_token: str | None = Cookie(None),
    db: Session = Depends(get_db),
):
    """결제 내역 조회"""
    user = get_current_user(session_token)
    if not user:
        return PaymentHistoryResponse(success=False)

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
    session_token: str | None = Cookie(None),
    db: Session = Depends(get_db),
):
    """카드 등록 해제 (구독 취소)"""
    user = get_current_user(session_token)
    if not user:
        return BillingKeyDeactivateResponse(success=False, message="로그인이 필요합니다.")

    if user["role"] not in ("admin", "super_admin"):
        return BillingKeyDeactivateResponse(success=False, message="권한이 없습니다.")

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


