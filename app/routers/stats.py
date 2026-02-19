from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_auth, require_super_admin
from app.models.admin_user import AdminUser
from app.models.chat_log import ChatLog
from app.models.company import Company
from app.models.feedback import Feedback
from app.models.qa_knowledge import QaKnowledge
from app.models.tenant_quota import TenantQuota
from app.models.tenant_usage import TenantUsageMonthly

router = APIRouter(prefix="/api/stats", tags=["stats"])


def _current_yyyymm() -> str:
    return datetime.utcnow().strftime("%Y-%m")


@router.get("")
def get_stats(
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    company_id = user["company_id"]

    qa_query = db.query(QaKnowledge)
    if company_id != 0:
        qa_query = qa_query.filter(QaKnowledge.company_id == company_id)

    total_qa = qa_query.count()
    active_qa = qa_query.filter(QaKnowledge.is_active == True).count()

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    chat_query = db.query(ChatLog)
    if company_id != 0:
        chat_query = chat_query.filter(ChatLog.company_id == company_id)

    today_chats = chat_query.filter(ChatLog.timestamp >= today_start).count()
    total_chats = chat_query.count()

    # Category distribution
    categories = {}
    for qa in qa_query.all():
        categories[qa.category] = categories.get(qa.category, 0) + 1

    # QA 커스터마이즈 여부
    qa_customized = True
    if company_id != 0:
        company = db.query(Company).filter(Company.company_id == company_id).first()
        if company:
            qa_customized = company.qa_customized

    # Quota usage
    quota_info = None
    if company_id != 0:
        quota = db.query(TenantQuota).filter(TenantQuota.company_id == company_id).first()
        usage = (
            db.query(TenantUsageMonthly)
            .filter(TenantUsageMonthly.company_id == company_id, TenantUsageMonthly.yyyymm == _current_yyyymm())
            .first()
        )
        if quota:
            quota_info = {
                "chat": {"used": usage.chat_cnt if usage else 0, "limit": quota.monthly_chat_cnt},
                "tokens": {"used": usage.tokens_used if usage else 0, "limit": quota.monthly_tokens},
                "embed": {"used": usage.embed_cnt if usage else 0, "limit": quota.monthly_embed_cnt},
            }

    # Feedback stats (recent 7 days)
    week_ago = datetime.utcnow() - timedelta(days=7)
    fb_query = db.query(Feedback)
    if company_id != 0:
        fb_query = fb_query.filter(Feedback.company_id == company_id)
    dislike_count = fb_query.filter(Feedback.rating == "dislike", Feedback.created_at >= week_ago).count()

    # Unmatched questions count
    unmatched_query = db.query(ChatLog).filter(ChatLog.used_rag == False, ChatLog.qa_id == None)
    if company_id != 0:
        unmatched_query = unmatched_query.filter(ChatLog.company_id == company_id)
    unmatched_count = unmatched_query.count()

    return {
        "total_qa": total_qa,
        "active_qa": active_qa,
        "today_chats": today_chats,
        "total_chats": total_chats,
        "categories": categories,
        "qa_customized": qa_customized,
        "quota": quota_info,
        "dislike_7d": dislike_count,
        "unmatched_count": unmatched_count,
    }


@router.get("/overview")
def get_overview(
    db: Session = Depends(get_db),
    user: dict = Depends(require_super_admin),
):
    """Super admin: overview stats across all companies."""
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    total_companies = db.query(Company).filter(Company.deleted_at == None).count()
    active_companies = (
        db.query(Company)
        .filter(Company.is_active == True, Company.deleted_at == None)
        .count()
    )
    total_admins = db.query(AdminUser).count()
    total_qa = db.query(QaKnowledge).count()
    total_chats = db.query(ChatLog).count()
    today_chats = db.query(ChatLog).filter(ChatLog.timestamp >= today_start).count()

    # RAG success rate
    rag_total = db.query(ChatLog).count()
    rag_used = db.query(ChatLog).filter(ChatLog.used_rag == True).count()
    rag_success_rate = round(rag_used / max(rag_total, 1) * 100, 1)

    # Per-company breakdown
    company_stats = []
    companies = (
        db.query(Company)
        .filter(Company.deleted_at == None)
        .order_by(Company.company_id)
        .all()
    )
    yyyymm = _current_yyyymm()
    for c in companies:
        qa_count = db.query(QaKnowledge).filter(QaKnowledge.company_id == c.company_id).count()
        chat_count = db.query(ChatLog).filter(ChatLog.company_id == c.company_id).count()
        admin_count = db.query(AdminUser).filter(AdminUser.company_id == c.company_id).count()

        # Quota info
        quota = db.query(TenantQuota).filter(TenantQuota.company_id == c.company_id).first()
        usage = (
            db.query(TenantUsageMonthly)
            .filter(TenantUsageMonthly.company_id == c.company_id, TenantUsageMonthly.yyyymm == yyyymm)
            .first()
        )

        company_stats.append({
            "company_id": c.company_id,
            "company_name": c.company_name,
            "status": getattr(c, "status", "active"),
            "is_active": c.is_active,
            "subscription_plan": c.subscription_plan,
            "qa_count": qa_count,
            "chat_count": chat_count,
            "admin_count": admin_count,
            "max_qa_count": c.max_qa_count,
            "max_admins": c.max_admins,
            "quota_chat": f"{usage.chat_cnt if usage else 0}/{quota.monthly_chat_cnt if quota else '-'}",
            "quota_embed": f"{usage.embed_cnt if usage else 0}/{quota.monthly_embed_cnt if quota else '-'}",
        })

    return {
        "total_companies": total_companies,
        "active_companies": active_companies,
        "total_admins": total_admins,
        "total_qa": total_qa,
        "total_chats": total_chats,
        "today_chats": today_chats,
        "rag_success_rate": rag_success_rate,
        "companies": company_stats,
    }


@router.get("/trends")
def get_trends(
    days: int = Query(30, ge=1, le=90),
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Daily chat/RAG usage trends."""
    company_id = user["company_id"]
    start = datetime.utcnow() - timedelta(days=days)

    query = db.query(
        func.date(ChatLog.timestamp).label("date"),
        func.count(ChatLog.log_id).label("total"),
        func.sum(func.cast(ChatLog.used_rag == True, type_=func.count(ChatLog.log_id).type)).label("rag_count"),
    ).filter(ChatLog.timestamp >= start)

    if company_id != 0:
        query = query.filter(ChatLog.company_id == company_id)

    rows = query.group_by(func.date(ChatLog.timestamp)).order_by(func.date(ChatLog.timestamp)).all()

    return {
        "trends": [
            {
                "date": str(row.date),
                "total_chats": row.total,
                "rag_chats": row.rag_count or 0,
            }
            for row in rows
        ]
    }
