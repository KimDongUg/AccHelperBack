"""Quota checking and usage tracking for tenants."""

import logging
from datetime import datetime

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_auth
from app.models.company import Company
from app.models.tenant_quota import TenantQuota
from app.models.tenant_usage import TenantUsageMonthly

logger = logging.getLogger("acchelper")


def _current_yyyymm() -> str:
    return datetime.utcnow().strftime("%Y-%m")


def _get_or_create_usage(db: Session, company_id: int) -> TenantUsageMonthly:
    yyyymm = _current_yyyymm()
    usage = (
        db.query(TenantUsageMonthly)
        .filter(TenantUsageMonthly.company_id == company_id, TenantUsageMonthly.yyyymm == yyyymm)
        .first()
    )
    if not usage:
        usage = TenantUsageMonthly(company_id=company_id, yyyymm=yyyymm)
        db.add(usage)
        db.flush()
    return usage


def _get_quota(db: Session, company_id: int) -> TenantQuota | None:
    return db.query(TenantQuota).filter(TenantQuota.company_id == company_id).first()


def check_tenant_active(
    request: Request,
    user: dict = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Check that tenant status is active. Returns user dict."""
    company_id = user.get("company_id", 0)
    if company_id == 0:
        return user  # super_admin bypass

    company = db.query(Company).filter(Company.company_id == company_id).first()
    if company and hasattr(company, "status") and company.status not in ("active", None, ""):
        raise HTTPException(status_code=403, detail="이용이 중지된 회사입니다.")
    return user


def check_chat_quota(
    request: Request,
    user: dict = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Check monthly chat quota. Returns user dict."""
    company_id = user.get("company_id", 0)
    if company_id == 0:
        return user

    quota = _get_quota(db, company_id)
    if not quota:
        return user  # no quota set = unlimited

    usage = _get_or_create_usage(db, company_id)
    if usage.chat_cnt >= quota.monthly_chat_cnt:
        raise HTTPException(status_code=429, detail="월간 채팅 횟수 한도를 초과했습니다.")
    return user


def check_embed_quota(
    request: Request,
    user: dict = Depends(require_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Check monthly embedding quota. Returns user dict."""
    company_id = user.get("company_id", 0)
    if company_id == 0:
        return user

    quota = _get_quota(db, company_id)
    if not quota:
        return user

    usage = _get_or_create_usage(db, company_id)
    if usage.embed_cnt >= quota.monthly_embed_cnt:
        raise HTTPException(status_code=429, detail="월간 임베딩 횟수 한도를 초과했습니다.")
    return user


def increment_usage(db: Session, company_id: int, chat_cnt: int = 0, tokens_used: int = 0, embed_cnt: int = 0):
    """UPSERT usage counters for current month."""
    if company_id == 0:
        return

    usage = _get_or_create_usage(db, company_id)
    usage.chat_cnt += chat_cnt
    usage.tokens_used += tokens_used
    usage.embed_cnt += embed_cnt
    db.flush()
