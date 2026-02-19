"""Super admin endpoints for tenant and quota management."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_super_admin
from app.models.company import Company
from app.models.tenant_quota import TenantQuota
from app.services.embedding_service import bulk_rebuild_embeddings

router = APIRouter(prefix="/super", tags=["super-admin"])


class TenantUpdate(BaseModel):
    status: str | None = None  # active/suspended/trial_expired
    subscription_plan: str | None = None


class QuotaUpdate(BaseModel):
    monthly_chat_cnt: int | None = None
    monthly_tokens: int | None = None
    monthly_embed_cnt: int | None = None


@router.get("/tenants")
def list_tenants(
    db: Session = Depends(get_db),
    user: dict = Depends(require_super_admin),
):
    """List all tenants with quota info."""
    companies = (
        db.query(Company)
        .filter(Company.deleted_at == None)
        .order_by(Company.company_id)
        .all()
    )

    result = []
    for c in companies:
        quota = db.query(TenantQuota).filter(TenantQuota.company_id == c.company_id).first()
        result.append({
            "company_id": c.company_id,
            "company_name": c.company_name,
            "status": getattr(c, "status", "active"),
            "subscription_plan": c.subscription_plan,
            "is_active": c.is_active,
            "quota": {
                "monthly_chat_cnt": quota.monthly_chat_cnt if quota else None,
                "monthly_tokens": quota.monthly_tokens if quota else None,
                "monthly_embed_cnt": quota.monthly_embed_cnt if quota else None,
            } if quota else None,
        })

    return {"tenants": result, "total": len(result)}


@router.put("/tenants/{company_id}")
def update_tenant(
    company_id: int,
    data: TenantUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_super_admin),
):
    """Update tenant status or subscription plan."""
    company = db.query(Company).filter(Company.company_id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="회사를 찾을 수 없습니다.")

    if data.status is not None:
        company.status = data.status
    if data.subscription_plan is not None:
        company.subscription_plan = data.subscription_plan

    db.commit()
    return {"success": True, "message": "테넌트 정보가 업데이트되었습니다."}


@router.put("/tenants/{company_id}/quota")
def update_quota(
    company_id: int,
    data: QuotaUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_super_admin),
):
    """Update or create quota for a tenant."""
    quota = db.query(TenantQuota).filter(TenantQuota.company_id == company_id).first()
    if not quota:
        quota = TenantQuota(company_id=company_id)
        db.add(quota)

    if data.monthly_chat_cnt is not None:
        quota.monthly_chat_cnt = data.monthly_chat_cnt
    if data.monthly_tokens is not None:
        quota.monthly_tokens = data.monthly_tokens
    if data.monthly_embed_cnt is not None:
        quota.monthly_embed_cnt = data.monthly_embed_cnt

    db.commit()
    return {"success": True, "message": "쿼터가 업데이트되었습니다."}


@router.post("/embeddings/rebuild")
def rebuild_embeddings(
    company_id: int | None = Query(None),
    db: Session = Depends(get_db),
    user: dict = Depends(require_super_admin),
):
    """Rebuild all embeddings (optionally for a specific company)."""
    stats = bulk_rebuild_embeddings(db, company_id)
    return {"success": True, "message": "임베딩 재생성 완료", **stats}
