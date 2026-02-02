from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_auth
from app.models.activity_log import AdminActivityLog

router = APIRouter(prefix="/api/activity-logs", tags=["activity-logs"])


@router.get("")
def list_activity_logs(
    action_type: str | None = Query(None),
    target_type: str | None = Query(None),
    page: int = 1,
    size: int = 20,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """List activity logs for current company."""
    company_id = user["company_id"]
    query = db.query(AdminActivityLog).filter(AdminActivityLog.company_id == company_id)

    if action_type:
        query = query.filter(AdminActivityLog.action_type == action_type)
    if target_type:
        query = query.filter(AdminActivityLog.target_type == target_type)

    total = query.count()
    pages = max(1, (total + size - 1) // size)
    items = (
        query.order_by(AdminActivityLog.timestamp.desc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    return {
        "items": [
            {
                "activity_id": log.activity_id,
                "company_id": log.company_id,
                "user_id": log.user_id,
                "action_type": log.action_type,
                "target_type": log.target_type,
                "target_id": log.target_id,
                "details": log.details,
                "ip_address": log.ip_address,
                "timestamp": log.timestamp.isoformat() + "Z" if log.timestamp else None,
            }
            for log in items
        ],
        "total": total,
        "page": page,
        "pages": pages,
    }
