from fastapi import Cookie, HTTPException

from app.routers.auth import get_current_user, sessions


def require_auth(session_token: str | None = Cookie(None)) -> dict:
    """Require any authenticated user."""
    user = get_current_user(session_token)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    return user


def require_admin(session_token: str | None = Cookie(None)) -> dict:
    """Require admin or super_admin role."""
    user = require_auth(session_token)
    role = user.get("role", "viewer")
    if role not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    return user


def require_super_admin(session_token: str | None = Cookie(None)) -> dict:
    """Require super_admin role."""
    user = require_auth(session_token)
    role = user.get("role", "viewer")
    if role != "super_admin":
        raise HTTPException(status_code=403, detail="최고 관리자 권한이 필요합니다.")
    return user


def get_company_id(session_token: str | None = Cookie(None)) -> int:
    """Extract company_id from the current session."""
    user = require_auth(session_token)
    return user["company_id"]
