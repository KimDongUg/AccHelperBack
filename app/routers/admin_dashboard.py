from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_super_admin
from app.models.admin_user import AdminUser
from app.models.billing import BillingKey, PaymentHistory
from app.models.company import Company
from app.schemas.admin import AdminListResponse
from app.schemas.admin_dashboard import (
    DashboardOverview,
    PaymentItem,
    PaymentListResponse,
    SubscriberItem,
    SubscriberListResponse,
)

router = APIRouter(prefix="/api/admin-dashboard", tags=["admin-dashboard"])


@router.get("/overview", response_model=DashboardOverview)
def dashboard_overview(
    db: Session = Depends(get_db),
    user: dict = Depends(require_super_admin),
):
    """전체 현황 요약 (super_admin 전용)"""
    companies = db.query(Company).filter(Company.deleted_at == None).all()
    now = datetime.utcnow()

    total = len(companies)
    active = 0
    trial = 0
    free = 0

    for c in companies:
        if c.subscription_plan == "enterprise":
            active += 1
        elif c.subscription_plan == "trial" and c.trial_ends_at and c.trial_ends_at > now:
            trial += 1
        else:
            free += 1

    total_revenue = (
        db.query(func.coalesce(func.sum(PaymentHistory.amount), 0))
        .filter(PaymentHistory.status == "success")
        .scalar()
    )
    total_payments = (
        db.query(func.count(PaymentHistory.id))
        .filter(PaymentHistory.status == "success")
        .scalar()
    )

    return DashboardOverview(
        success=True,
        total_companies=total,
        active_subscribers=active,
        trial_subscribers=trial,
        free_companies=free,
        total_revenue=total_revenue,
        total_payments=total_payments,
    )


@router.get("/subscribers", response_model=SubscriberListResponse)
def list_subscribers(
    db: Session = Depends(get_db),
    user: dict = Depends(require_super_admin),
):
    """전체 회사 구독 현황 (super_admin 전용)"""
    companies = (
        db.query(Company)
        .filter(Company.deleted_at == None)
        .order_by(Company.company_id)
        .all()
    )
    now = datetime.utcnow()
    items = []

    for c in companies:
        # 빌링키
        bk = (
            db.query(BillingKey)
            .filter(BillingKey.company_id == c.company_id, BillingKey.is_active == True)
            .first()
        )

        # 관리자 수
        admin_count = (
            db.query(func.count(AdminUser.user_id))
            .filter(AdminUser.company_id == c.company_id)
            .scalar()
        )

        # 결제 합계
        pay_stats = (
            db.query(
                func.coalesce(func.sum(PaymentHistory.amount), 0),
                func.count(PaymentHistory.id),
                func.max(PaymentHistory.paid_at),
            )
            .filter(
                PaymentHistory.company_id == c.company_id,
                PaymentHistory.status == "success",
            )
            .first()
        )

        total_paid = pay_stats[0] if pay_stats else 0
        payment_count = pay_stats[1] if pay_stats else 0
        last_paid_at = pay_stats[2] if pay_stats else None

        # 구독 활성 여부
        billing_active = False
        if c.subscription_plan == "enterprise":
            billing_active = True
        elif c.subscription_plan == "trial" and c.trial_ends_at and c.trial_ends_at > now:
            billing_active = True

        items.append(SubscriberItem(
            company_id=c.company_id,
            company_name=c.company_name,
            business_number=c.business_number,
            address=c.address,
            subscription_plan=c.subscription_plan or "free",
            billing_active=billing_active,
            has_billing_key=bk is not None,
            card_company=bk.card_company if bk else None,
            card_number=bk.card_number if bk else None,
            admin_count=admin_count,
            total_paid=total_paid,
            payment_count=payment_count,
            last_paid_at=last_paid_at.isoformat() + "Z" if last_paid_at else None,
            trial_ends_at=c.trial_ends_at.isoformat() + "Z" if c.trial_ends_at else None,
            created_at=c.created_at.isoformat() + "Z",
        ))

    return SubscriberListResponse(success=True, items=items, total=len(items))


@router.get("/payments", response_model=PaymentListResponse)
def list_all_payments(
    status: str | None = Query(None),
    company_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user: dict = Depends(require_super_admin),
):
    """전체 결제 내역 (super_admin 전용). status/company_id로 필터 가능."""
    query = db.query(PaymentHistory)

    if status:
        query = query.filter(PaymentHistory.status == status)
    if company_id:
        query = query.filter(PaymentHistory.company_id == company_id)

    payments = query.order_by(PaymentHistory.paid_at.desc()).limit(200).all()

    items = []
    # 회사명 + 관리자 이메일 캐시
    company_cache: dict[int, str] = {}
    admin_cache: dict[int, str | None] = {}

    for p in payments:
        if p.company_id not in company_cache:
            c = db.query(Company).filter(Company.company_id == p.company_id).first()
            company_cache[p.company_id] = c.company_name if c else f"company_{p.company_id}"
            admin = (
                db.query(AdminUser)
                .filter(AdminUser.company_id == p.company_id, AdminUser.is_active == True)
                .order_by(AdminUser.user_id)
                .first()
            )
            admin_cache[p.company_id] = admin.email if admin else None

        items.append(PaymentItem(
            id=p.id,
            company_id=p.company_id,
            company_name=company_cache[p.company_id],
            admin_email=admin_cache.get(p.company_id),
            order_id=p.order_id,
            order_name=p.order_name,
            amount=p.amount,
            status=p.status,
            payment_key=p.payment_key,
            failure_reason=p.failure_reason,
            paid_at=p.paid_at.isoformat() + "Z",
        ))

    return PaymentListResponse(success=True, items=items, total=len(items))


@router.get("/companies/{company_id}/admins", response_model=AdminListResponse)
def list_company_admins(
    company_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_super_admin),
):
    """특정 회사의 관리자 목록 (super_admin 전용)"""
    admins = (
        db.query(AdminUser)
        .filter(AdminUser.company_id == company_id)
        .order_by(AdminUser.user_id)
        .all()
    )
    return AdminListResponse(items=admins, total=len(admins))
