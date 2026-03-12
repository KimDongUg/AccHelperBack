from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Integer as SAInteger, String, case, cast, func, literal_column
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


@router.get("/usage")
def get_usage_stats(
    period: str = Query("daily", regex="^(daily|monthly|quarterly|yearly)$"),
    date_from: str = Query(..., alias="from"),
    date_to: str = Query(..., alias="to"),
    company_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """
    Usage statistics (visitors, question views, answer views) grouped by period.
    Data is strictly filtered by company_id from JWT.
    super_admin can optionally pass company_id query param.
    """
    # Determine company filter — strict isolation
    cid = user["company_id"]
    role = user.get("role", "viewer")
    if role == "super_admin" and company_id is not None:
        cid = company_id
    # cid == 0 means super_admin without company (show all only if no filter)

    # Parse date range
    try:
        dt_from = datetime.strptime(date_from, "%Y-%m-%d")
        dt_to = datetime.strptime(date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    except ValueError:
        return {"items": []}

    # Base query filtered by company and date range
    base = db.query(ChatLog).filter(
        ChatLog.timestamp >= dt_from,
        ChatLog.timestamp <= dt_to,
    )
    if cid != 0:
        base = base.filter(ChatLog.company_id == cid)

    # Build period expression
    if period == "daily":
        period_expr = func.date(ChatLog.timestamp)
    elif period == "monthly":
        # Works for both PostgreSQL (to_char) and SQLite (strftime)
        period_expr = func.substr(func.cast(ChatLog.timestamp, String(30)), 1, 7)
    elif period == "quarterly":
        # Extract year and quarter
        period_expr = _quarter_expr(ChatLog.timestamp)
    else:  # yearly
        period_expr = func.substr(func.cast(ChatLog.timestamp, String(30)), 1, 4)

    # Aggregate
    rows = (
        base.with_entities(
            period_expr.label("period"),
            func.count(func.distinct(ChatLog.session_id)).label("visitors"),
            func.count(ChatLog.log_id).label("question_views"),
            func.sum(
                case(
                    (ChatLog.qa_id != None, 1),
                    else_=0,
                )
            ).label("answer_views"),
        )
        .group_by(period_expr)
        .order_by(period_expr)
        .all()
    )

    items = [
        {
            "period": str(row.period),
            "visitors": row.visitors or 0,
            "question_views": row.question_views or 0,
            "answer_views": int(row.answer_views or 0),
        }
        for row in rows
    ]

    return {"items": items}


def _quarter_expr(timestamp_col):
    """Build a quarter expression like '2026-Q1' compatible with SQLite and PostgreSQL."""
    ts_str = func.cast(timestamp_col, String(30))
    year_part = func.substr(ts_str, 1, 4)
    month_str = func.substr(ts_str, 6, 2)
    quarter = case(
        (month_str.in_(["01", "02", "03"]), "-Q1"),
        (month_str.in_(["04", "05", "06"]), "-Q2"),
        (month_str.in_(["07", "08", "09"]), "-Q3"),
        else_="-Q4",
    )
    return func.concat(year_part, quarter)
