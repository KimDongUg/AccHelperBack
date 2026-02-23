import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_super_admin
from app.models.admin_user import AdminUser
from app.models.billing import BillingKey, PaymentHistory
from app.models.company import Company
from app.models.qa_knowledge import QaKnowledge
from app.schemas.admin import AdminListResponse
from app.schemas.admin_dashboard import (
    ApprovalRequest,
    DashboardOverview,
    DataWarning,
    PaymentItem,
    PaymentListResponse,
    SubscriberItem,
    SubscriberListResponse,
    ValidateDataResponse,
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
            approval_status=c.approval_status or "pending",
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


@router.patch("/companies/{company_id}/approve")
def approve_company(
    company_id: int,
    body: ApprovalRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(require_super_admin),
):
    """회사 승인/반려 (super_admin 전용)"""
    company = db.query(Company).filter(Company.company_id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="회사를 찾을 수 없습니다.")

    if body.status not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="status는 'approved' 또는 'rejected'만 가능합니다.")

    if body.status == "approved":
        company.approval_status = "approved"
        company.approved_at = datetime.utcnow()
        company.approved_by = user["user_id"]
        company.rejection_reason = None
    else:
        company.approval_status = "rejected"
        company.rejection_reason = body.reason

    company.updated_at = datetime.utcnow()
    db.commit()

    return {
        "success": True,
        "message": f"회사가 {'승인' if body.status == 'approved' else '반려'}되었습니다.",
        "approval_status": company.approval_status,
    }


@router.get("/companies/{company_id}/validate-data", response_model=ValidateDataResponse)
def validate_company_data(
    company_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_super_admin),
):
    """회사 Q&A 데이터에 타 업체 정보가 잔존하는지 검증 (super_admin 전용)"""
    company = db.query(Company).filter(Company.company_id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="회사를 찾을 수 없습니다.")

    # 대상 회사의 모든 Q&A
    qa_items = (
        db.query(QaKnowledge)
        .filter(QaKnowledge.company_id == company_id)
        .all()
    )

    # 다른 모든 회사의 phone, company_name
    other_companies = (
        db.query(Company)
        .filter(Company.company_id != company_id, Company.deleted_at == None)
        .all()
    )

    # 전화번호 정규식: 02-xxx-xxxx, 010-xxxx-xxxx, 0xx-xxx-xxxx 등
    phone_pattern = re.compile(r"0\d{1,2}[-.\s]?\d{3,4}[-.\s]?\d{4}")
    # 계좌번호 정규식: 연속 숫자 10~14자리 (하이픈 포함)
    account_pattern = re.compile(r"\d{3,6}[-]?\d{2,6}[-]?\d{2,6}")

    warnings: list[DataWarning] = []

    for qa in qa_items:
        answer = qa.answer or ""

        # 다른 회사 이름 / 전화번호 포함 여부
        for oc in other_companies:
            if oc.company_name and oc.company_name in answer:
                context_start = answer.find(oc.company_name)
                context = answer[max(0, context_start - 20):context_start + len(oc.company_name) + 20]
                warnings.append(DataWarning(
                    type="company_name",
                    found_value=oc.company_name,
                    matched_company=oc.company_name,
                    matched_company_id=oc.company_id,
                    qa_id=qa.qa_id,
                    context=context,
                ))

            if oc.phone and oc.phone in answer:
                context_start = answer.find(oc.phone)
                context = answer[max(0, context_start - 20):context_start + len(oc.phone) + 20]
                warnings.append(DataWarning(
                    type="phone",
                    found_value=oc.phone,
                    matched_company=oc.company_name,
                    matched_company_id=oc.company_id,
                    qa_id=qa.qa_id,
                    context=context,
                ))

        # 전화번호 패턴 매칭 — 다른 회사 전화번호와 비교
        found_phones = phone_pattern.findall(answer)
        for fp in found_phones:
            normalized = re.sub(r"[-.\s]", "", fp)
            for oc in other_companies:
                if oc.phone:
                    oc_normalized = re.sub(r"[-.\s]", "", oc.phone)
                    if normalized == oc_normalized:
                        context_start = answer.find(fp)
                        context = answer[max(0, context_start - 20):context_start + len(fp) + 20]
                        warnings.append(DataWarning(
                            type="phone_pattern",
                            found_value=fp,
                            matched_company=oc.company_name,
                            matched_company_id=oc.company_id,
                            qa_id=qa.qa_id,
                            context=context,
                        ))

    # 중복 제거 (같은 qa_id + type + found_value)
    seen = set()
    unique_warnings = []
    for w in warnings:
        key = (w.qa_id, w.type, w.found_value, w.matched_company_id)
        if key not in seen:
            seen.add(key)
            unique_warnings.append(w)

    return ValidateDataResponse(
        valid=len(unique_warnings) == 0,
        warnings=unique_warnings,
    )
