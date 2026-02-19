from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_auth, require_super_admin
from app.models.admin_user import AdminUser
from app.models.chat_log import ChatLog
from app.models.company import Company
from app.models.qa_knowledge import QaKnowledge

router = APIRouter(prefix="/api/stats", tags=["stats"])


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

    return {
        "total_qa": total_qa,
        "active_qa": active_qa,
        "today_chats": today_chats,
        "total_chats": total_chats,
        "categories": categories,
        "qa_customized": qa_customized,
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

    # Per-company breakdown
    company_stats = []
    companies = (
        db.query(Company)
        .filter(Company.deleted_at == None)
        .order_by(Company.company_id)
        .all()
    )
    for c in companies:
        qa_count = db.query(QaKnowledge).filter(QaKnowledge.company_id == c.company_id).count()
        chat_count = db.query(ChatLog).filter(ChatLog.company_id == c.company_id).count()
        admin_count = db.query(AdminUser).filter(AdminUser.company_id == c.company_id).count()
        company_stats.append({
            "company_id": c.company_id,
            "company_name": c.company_name,
            "is_active": c.is_active,
            "qa_count": qa_count,
            "chat_count": chat_count,
            "admin_count": admin_count,
            "max_qa_count": c.max_qa_count,
            "max_admins": c.max_admins,
        })

    return {
        "total_companies": total_companies,
        "active_companies": active_companies,
        "total_admins": total_admins,
        "total_qa": total_qa,
        "total_chats": total_chats,
        "today_chats": today_chats,
        "companies": company_stats,
    }
