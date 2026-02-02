from sqlalchemy.orm import Session

from app.models.activity_log import AdminActivityLog


def log_activity(
    db: Session,
    company_id: int,
    user_id: int,
    action_type: str,
    target_type: str | None = None,
    target_id: int | None = None,
    details: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
):
    """Log an admin activity."""
    log = AdminActivityLog(
        company_id=company_id,
        user_id=user_id,
        action_type=action_type,
        target_type=target_type,
        target_id=target_id,
        details=details,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(log)
    db.commit()
