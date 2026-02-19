from fastapi import Cookie, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.jwt_service import decode_token


def _extract_token(request: Request, session_token: str | None = Cookie(None)) -> str | None:
    """Extract JWT from Authorization header or fallback to cookie."""
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return session_token


def require_auth(request: Request, session_token: str | None = Cookie(None)) -> dict:
    """Require any authenticated user via JWT."""
    token = _extract_token(request, session_token)
    if not token:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="인증이 만료되었습니다. 다시 로그인해 주세요.")
    return payload


def require_admin(request: Request, session_token: str | None = Cookie(None)) -> dict:
    """Require admin or super_admin role."""
    user = require_auth(request, session_token)
    role = user.get("role", "viewer")
    if role not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    return user


def require_super_admin(request: Request, session_token: str | None = Cookie(None)) -> dict:
    """Require super_admin role."""
    user = require_auth(request, session_token)
    role = user.get("role", "viewer")
    if role != "super_admin":
        raise HTTPException(status_code=403, detail="최고 관리자 권한이 필요합니다.")
    return user


def get_company_id(request: Request, session_token: str | None = Cookie(None)) -> int:
    """Extract company_id from the current JWT."""
    user = require_auth(request, session_token)
    return user["company_id"]


def get_tenant_db(
    request: Request,
    session_token: str | None = Cookie(None),
    db: Session = Depends(get_db),
) -> Session:
    """Get a DB session with RLS tenant_id set (PostgreSQL only)."""
    token = _extract_token(request, session_token)
    if token:
        payload = decode_token(token)
        if payload:
            company_id = payload.get("company_id", 0)
            try:
                db.execute(text(f"SET LOCAL app.tenant_id = '{company_id}'"))
            except Exception:
                pass  # SQLite — no RLS
    return db
