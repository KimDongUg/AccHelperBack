from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.config import JWT_EXPIRE_HOURS, RATE_LIMIT_AUTH, RATE_LIMIT_PASSWORD_RESET
from app.database import get_db
from app.dependencies import require_auth
from app.models.admin_user import AdminUser
from app.models.company import Company
from app.rate_limit import limiter
from app.schemas.auth import (
    AuthCheckResponse,
    FindEmailRequest,
    FindEmailResponse,
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    RegisterResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
    SessionData,
)
from app.services.auth_service import (
    generate_temp_password,
    hash_password,
    mask_email,
    verify_password,
)
from app.services.email_service import send_temp_password_email
from app.services.jwt_service import create_access_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _build_session_data(user_row, company_name: str, plan: str, billing_active: bool, expiry_time: str) -> SessionData:
    return SessionData(
        user_id=user_row.user_id,
        username=user_row.username,
        company_id=user_row.company_id if user_row.company_id != 0 else 0,
        company_name=company_name,
        email=user_row.email,
        full_name=user_row.full_name,
        role=user_row.role,
        permissions=user_row.permissions,
        subscription_plan=plan,
        billing_active=billing_active,
        login_time=datetime.utcnow().isoformat() + "Z",
        expiry_time=expiry_time,
    )


@router.post("/login", response_model=LoginResponse)
@limiter.limit(RATE_LIMIT_AUTH)
def login(req: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    now = datetime.utcnow()
    expire_hours = JWT_EXPIRE_HOURS * 7 if req.remember else JWT_EXPIRE_HOURS
    expiry = now + timedelta(hours=expire_hours)
    expiry_str = expiry.isoformat() + "Z"

    # super_admin direct login with company_id=0
    if req.company_id == 0:
        user = (
            db.query(AdminUser)
            .filter(AdminUser.company_id == 0, AdminUser.email == req.email)
            .first()
        )
        if not user or not user.is_active:
            return LoginResponse(success=False, message="사용자를 찾을 수 없습니다.")
        if not verify_password(req.password, user.password_hash):
            return LoginResponse(success=False, message="비밀번호가 올바르지 않습니다.")

        user.last_login = now
        db.commit()

        token = create_access_token(
            {
                "user_id": user.user_id,
                "company_id": 0,
                "company_name": "시스템 관리",
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role,
                "subscription_plan": "enterprise",
                "billing_active": True,
            },
            expire_hours=expire_hours,
        )

        session = _build_session_data(user, "시스템 관리", "enterprise", True, expiry_str)
        return LoginResponse(success=True, message="로그인 성공", token=token, session=session)

    # Lookup company by ID
    company = (
        db.query(Company)
        .filter(Company.company_id == req.company_id, Company.is_active == True, Company.deleted_at == None)
        .first()
    )
    if not company:
        return LoginResponse(success=False, message="회사 ID를 찾을 수 없습니다.")

    # Check company status
    if hasattr(company, "status") and company.status not in ("active", None):
        return LoginResponse(success=False, message="이용이 중지된 회사입니다.")

    # Try normal company-scoped lookup first
    user = (
        db.query(AdminUser)
        .filter(AdminUser.company_id == company.company_id, AdminUser.email == req.email)
        .first()
    )

    # If not found, check for super_admin (company_id=0) by email only
    if not user:
        user = (
            db.query(AdminUser)
            .filter(AdminUser.company_id == 0, AdminUser.email == req.email)
            .first()
        )

    if not user or not user.is_active:
        return LoginResponse(success=False, message="사용자를 찾을 수 없습니다.")

    if not verify_password(req.password, user.password_hash):
        return LoginResponse(success=False, message="비밀번호가 올바르지 않습니다.")

    user.last_login = now
    db.commit()

    # super_admin (company_id=0) keeps company_id=0 in token
    session_company_id = user.company_id if user.company_id == 0 else company.company_id

    plan = company.subscription_plan or "free"
    billing_active = False
    if plan == "enterprise":
        billing_active = True
    elif plan == "trial" and company.trial_ends_at:
        billing_active = company.trial_ends_at > now

    token = create_access_token(
        {
            "user_id": user.user_id,
            "company_id": session_company_id,
            "company_name": company.company_name,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "subscription_plan": plan,
            "billing_active": billing_active,
        },
        expire_hours=expire_hours,
    )

    session = _build_session_data(user, company.company_name, plan, billing_active, expiry_str)
    # Override company_id for super_admin accessing a company
    session.company_id = session_company_id

    return LoginResponse(success=True, message="로그인 성공", token=token, session=session)


@router.post("/register", response_model=RegisterResponse)
@limiter.limit(RATE_LIMIT_AUTH)
def register(req: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    # Validate company
    company = (
        db.query(Company)
        .filter(Company.company_id == req.company_id, Company.is_active == True, Company.deleted_at == None)
        .first()
    )
    if not company:
        return RegisterResponse(success=False, message="회사 ID를 찾을 수 없습니다.")

    # Check max_admins quota
    current_count = db.query(AdminUser).filter(AdminUser.company_id == company.company_id).count()
    if current_count >= company.max_admins:
        return RegisterResponse(
            success=False,
            message=f"해당 회사의 관리자 수 한도({company.max_admins}명)를 초과했습니다.",
        )

    # Check duplicate email within company
    existing = (
        db.query(AdminUser)
        .filter(AdminUser.company_id == company.company_id, AdminUser.email == req.email)
        .first()
    )
    if existing:
        return RegisterResponse(success=False, message="이미 등록된 이메일입니다.")

    # Create user with viewer role
    user = AdminUser(
        company_id=company.company_id,
        email=req.email,
        password_hash=hash_password(req.password),
        full_name=req.full_name,
        phone=req.phone,
        role="viewer",
        is_active=True,
    )
    db.add(user)
    db.commit()

    return RegisterResponse(success=True, message="회원가입이 완료되었습니다. 로그인해 주세요.")


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie("session_token")
    return {"success": True, "message": "로그아웃 되었습니다."}


@router.get("/check", response_model=AuthCheckResponse)
def check_auth(request: Request, user: dict = Depends(require_auth), db: Session = Depends(get_db)):
    company_id = user.get("company_id", 0)

    # Refresh subscription status from DB
    if company_id and company_id != 0:
        company = db.query(Company).filter(Company.company_id == company_id).first()
        if company:
            plan = company.subscription_plan or "free"
            now = datetime.utcnow()
            billing_active = False
            if plan == "enterprise":
                billing_active = True
            elif plan == "trial" and company.trial_ends_at:
                billing_active = company.trial_ends_at > now
            user["subscription_plan"] = plan
            user["billing_active"] = billing_active

    session = SessionData(
        user_id=user.get("user_id", 0),
        username=user.get("username"),
        company_id=company_id,
        company_name=user.get("company_name", ""),
        email=user.get("email", ""),
        full_name=user.get("full_name"),
        role=user.get("role", "viewer"),
        permissions=user.get("permissions"),
        subscription_plan=user.get("subscription_plan"),
        billing_active=user.get("billing_active", False),
        login_time=user.get("iat", ""),
        expiry_time=user.get("exp", ""),
    )
    return AuthCheckResponse(authenticated=True, session=session)


@router.post("/find-email", response_model=FindEmailResponse)
@limiter.limit(RATE_LIMIT_AUTH)
def find_email(req: FindEmailRequest, request: Request, db: Session = Depends(get_db)):
    """Find email by company_id + full_name. Returns masked email."""
    company = (
        db.query(Company)
        .filter(Company.company_id == req.company_id, Company.is_active == True, Company.deleted_at == None)
        .first()
    )
    if not company:
        return FindEmailResponse(success=False, message="일치하는 정보를 찾을 수 없습니다.")

    user = (
        db.query(AdminUser)
        .filter(
            AdminUser.company_id == company.company_id,
            AdminUser.full_name == req.full_name,
            AdminUser.is_active == True,
        )
        .first()
    )
    # Fallback: check super_admin (company_id=0)
    if not user:
        user = (
            db.query(AdminUser)
            .filter(
                AdminUser.company_id == 0,
                AdminUser.full_name == req.full_name,
                AdminUser.is_active == True,
            )
            .first()
        )
    if not user:
        return FindEmailResponse(success=False, message="일치하는 정보를 찾을 수 없습니다.")

    masked = mask_email(user.email)
    return FindEmailResponse(
        success=True,
        message="이메일을 찾았습니다.",
        masked_email=masked,
    )


@router.post("/reset-password", response_model=ResetPasswordResponse)
@limiter.limit(RATE_LIMIT_PASSWORD_RESET)
def reset_password(req: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)):
    """Generate temp password and send via email."""
    company = (
        db.query(Company)
        .filter(Company.company_id == req.company_id, Company.is_active == True, Company.deleted_at == None)
        .first()
    )
    if not company:
        return ResetPasswordResponse(success=True, message="등록된 이메일이라면 임시 비밀번호가 발송됩니다.")

    user = (
        db.query(AdminUser)
        .filter(
            AdminUser.company_id == company.company_id,
            AdminUser.email == req.email,
            AdminUser.is_active == True,
        )
        .first()
    )
    # Fallback: check super_admin (company_id=0)
    if not user:
        user = (
            db.query(AdminUser)
            .filter(
                AdminUser.company_id == 0,
                AdminUser.email == req.email,
                AdminUser.is_active == True,
            )
            .first()
        )
    if not user:
        return ResetPasswordResponse(success=True, message="등록된 이메일이라면 임시 비밀번호가 발송됩니다.")

    temp_pw = generate_temp_password(10)
    old_hash = user.password_hash

    # Update password in DB first
    user.password_hash = hash_password(temp_pw)
    db.commit()

    # Send email — rollback on failure
    if not send_temp_password_email(user.email, temp_pw):
        user.password_hash = old_hash
        db.commit()
        return ResetPasswordResponse(
            success=False,
            message="이메일 발송에 실패했습니다. 잠시 후 다시 시도해 주세요.",
        )

    return ResetPasswordResponse(success=True, message="임시 비밀번호가 이메일로 발송되었습니다.")
