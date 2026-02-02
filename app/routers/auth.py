import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Cookie, Depends, Request, Response
from sqlalchemy.orm import Session

from app.config import RATE_LIMIT_AUTH, SESSION_EXPIRE_HOURS
from app.database import get_db
from app.models.admin_user import AdminUser
from app.rate_limit import limiter
from app.schemas.auth import AuthCheckResponse, LoginRequest, LoginResponse, SessionData
from app.services.auth_service import verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

# In-memory session store
# {token: {"user_id": int, "username": str, "login_time": datetime, "expiry_time": datetime}}
sessions: dict[str, dict] = {}


def _cleanup_expired():
    """Remove expired sessions."""
    now = datetime.utcnow()
    expired = [k for k, v in sessions.items() if v["expiry_time"] <= now]
    for k in expired:
        del sessions[k]


def _make_session_data(sess: dict) -> SessionData:
    return SessionData(
        user_id=sess["user_id"],
        username=sess["username"],
        login_time=sess["login_time"].isoformat() + "Z",
        expiry_time=sess["expiry_time"].isoformat() + "Z",
    )


def get_current_user(session_token: str | None = Cookie(None)) -> dict | None:
    if not session_token or session_token not in sessions:
        return None
    sess = sessions[session_token]
    if sess["expiry_time"] <= datetime.utcnow():
        del sessions[session_token]
        return None
    return sess


@router.post("/login", response_model=LoginResponse)
@limiter.limit(RATE_LIMIT_AUTH)
def login(req: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    _cleanup_expired()

    user = db.query(AdminUser).filter(AdminUser.username == req.username).first()
    if not user or not user.is_active:
        return LoginResponse(success=False, message="사용자를 찾을 수 없습니다.")

    if not verify_password(req.password, user.password_hash):
        return LoginResponse(success=False, message="비밀번호가 올바르지 않습니다.")

    user.last_login = datetime.utcnow()
    db.commit()

    now = datetime.utcnow()
    expire_hours = SESSION_EXPIRE_HOURS * 7 if req.remember else SESSION_EXPIRE_HOURS
    expiry = now + timedelta(hours=expire_hours)

    token = str(uuid.uuid4())
    sessions[token] = {
        "user_id": user.user_id,
        "username": user.username,
        "login_time": now,
        "expiry_time": expiry,
    }

    cookie_max_age = int(expire_hours * 3600)
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=cookie_max_age,
    )

    return LoginResponse(
        success=True,
        message="로그인 성공",
        session=_make_session_data(sessions[token]),
    )


@router.post("/logout")
def logout(response: Response, session_token: str | None = Cookie(None)):
    if session_token and session_token in sessions:
        del sessions[session_token]
    response.delete_cookie("session_token")
    return {"success": True, "message": "로그아웃 되었습니다."}


@router.get("/check", response_model=AuthCheckResponse)
def check_auth(session_token: str | None = Cookie(None)):
    user = get_current_user(session_token)
    if user:
        return AuthCheckResponse(
            authenticated=True,
            session=_make_session_data(user),
        )
    return AuthCheckResponse(authenticated=False)
