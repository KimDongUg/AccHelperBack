from fastapi import Cookie, Depends, HTTPException, Query, Request
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


def optional_admin(request: Request, session_token: str | None = Cookie(None)) -> dict | None:
    """Return admin payload if valid admin JWT present, else None (no error)."""
    token = _extract_token(request, session_token)
    if not token:
        return None
    payload = decode_token(token)
    if not payload:
        return None
    if payload.get("role") not in ("admin", "super_admin"):
        return None
    return payload


def require_auth_with_scope(
    company_id: int | None = Query(None, alias="company_id"),
    user: dict = Depends(require_auth),
) -> dict:
    """require_admin_with_scope와 동일한 회사 오버라이드를 admin 역할 제한 없이 적용한다
    (대시보드 통계처럼 role in (admin, super_admin, viewer) 모두 접근 가능한 엔드포인트용)."""
    if user["company_id"] == 0 and company_id is not None:
        return {**user, "company_id": company_id}
    return user


def require_admin_with_scope(
    company_id: int | None = Query(None, alias="company_id"),
    user: dict = Depends(require_admin),
) -> dict:
    """super_admin(company_id=0)이 company_id 쿼리 파라미터로 특정 회사를 지정하면,
    그 회사의 admin으로 로그인한 것과 동일하게 동작하도록 company_id를 바꿔치기한다.
    (super-admin 대시보드에서 개별 회사 관리자화면으로 들어갔을 때 그 회사 admin과
    동일한 데이터를 보게 하기 위함). 일반 admin은 파라미터를 무시하고 자기 회사로 고정."""
    if user["company_id"] == 0 and company_id is not None:
        return {**user, "company_id": company_id}
    return user


def require_super_admin(request: Request, session_token: str | None = Cookie(None)) -> dict:
    """Require super_admin role."""
    user = require_auth(request, session_token)
    role = user.get("role", "viewer")
    if role != "super_admin":
        raise HTTPException(status_code=403, detail="최고 관리자 권한이 필요합니다.")
    return user


def require_fee_token(request: Request, dong: str, ho: str, company_id: int = 1) -> dict:
    """관리비 조회용 JWT 검증. scope='fee'이며 토큰의 company_id/dong/ho가 쿼리 파라미터와 일치해야 함."""
    token = _extract_token(request, None)
    if not token:
        raise HTTPException(status_code=401, detail="인증이 필요합니다. 인증번호를 다시 확인해 주세요.")
    payload = decode_token(token)
    if not payload or payload.get("scope") != "fee":
        raise HTTPException(status_code=401, detail="인증이 만료되었습니다. 다시 인증해 주세요.")
    norm_dong = dong.strip().lstrip("0") or dong.strip()
    norm_ho = ho.strip().lstrip("0") or ho.strip()
    if (
        payload.get("dong") != norm_dong
        or payload.get("ho") != norm_ho
        or payload.get("company_id", 1) != company_id
    ):
        raise HTTPException(status_code=403, detail="인증 정보가 일치하지 않습니다.")
    return payload


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
