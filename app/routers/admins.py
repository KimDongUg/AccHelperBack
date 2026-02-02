from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin, require_auth
from app.models.admin_user import AdminUser
from app.models.company import Company
from app.schemas.admin import (
    AdminCreate,
    AdminListResponse,
    AdminPasswordChange,
    AdminResponse,
    AdminUpdate,
)
from app.services.auth_service import hash_password, verify_password

router = APIRouter(prefix="/api/admins", tags=["admins"])


@router.get("/me", response_model=AdminResponse)
def get_me(
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Get current user profile."""
    admin = db.query(AdminUser).filter(AdminUser.user_id == user["user_id"]).first()
    if not admin:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    return admin


@router.patch("/me", response_model=AdminResponse)
def update_me(
    data: AdminUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Update current user profile (limited fields)."""
    admin = db.query(AdminUser).filter(AdminUser.user_id == user["user_id"]).first()
    if not admin:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    # Self-update: only allow name, phone, department, position
    allowed = {"full_name", "phone", "department", "position"}
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if key in allowed:
            setattr(admin, key, value)
    db.commit()
    db.refresh(admin)
    return admin


@router.patch("/me/password")
def change_my_password(
    data: AdminPasswordChange,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Change current user password."""
    admin = db.query(AdminUser).filter(AdminUser.user_id == user["user_id"]).first()
    if not admin:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    if data.current_password and not verify_password(data.current_password, admin.password_hash):
        raise HTTPException(status_code=400, detail="현재 비밀번호가 올바르지 않습니다.")

    admin.password_hash = hash_password(data.new_password)
    db.commit()
    return {"success": True, "message": "비밀번호가 변경되었습니다."}


@router.get("", response_model=AdminListResponse)
def list_admins(
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
):
    """List admins for current company."""
    company_id = user["company_id"]
    admins = (
        db.query(AdminUser)
        .filter(AdminUser.company_id == company_id)
        .order_by(AdminUser.user_id)
        .all()
    )
    return AdminListResponse(items=admins, total=len(admins))


@router.get("/{user_id}", response_model=AdminResponse)
def get_admin(
    user_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
):
    company_id = user["company_id"]
    admin = (
        db.query(AdminUser)
        .filter(AdminUser.user_id == user_id, AdminUser.company_id == company_id)
        .first()
    )
    if not admin:
        raise HTTPException(status_code=404, detail="관리자를 찾을 수 없습니다.")
    return admin


@router.post("", response_model=AdminResponse, status_code=201)
def create_admin(
    data: AdminCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
):
    company_id = user["company_id"]

    # Check max_admins quota
    company = db.query(Company).filter(Company.company_id == company_id).first()
    if company:
        current_count = db.query(AdminUser).filter(AdminUser.company_id == company_id).count()
        if current_count >= company.max_admins:
            raise HTTPException(
                status_code=403,
                detail=f"관리자 수 한도({company.max_admins}명)를 초과했습니다.",
            )

    # Check duplicate email within company
    existing = (
        db.query(AdminUser)
        .filter(AdminUser.company_id == company_id, AdminUser.email == data.email)
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="이미 등록된 이메일입니다.")

    # Only super_admin can create other super_admins
    if data.role == "super_admin" and user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="최고 관리자만 최고 관리자를 생성할 수 있습니다.")

    admin = AdminUser(
        company_id=company_id,
        email=data.email,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        phone=data.phone,
        department=data.department,
        position=data.position,
        role=data.role,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin


@router.put("/{user_id}", response_model=AdminResponse)
def update_admin(
    user_id: int,
    data: AdminUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
):
    company_id = user["company_id"]
    admin = (
        db.query(AdminUser)
        .filter(AdminUser.user_id == user_id, AdminUser.company_id == company_id)
        .first()
    )
    if not admin:
        raise HTTPException(status_code=404, detail="관리자를 찾을 수 없습니다.")

    # Only super_admin can change roles to super_admin
    update_data = data.model_dump(exclude_unset=True)
    if "role" in update_data and update_data["role"] == "super_admin" and user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="최고 관리자만 역할을 변경할 수 있습니다.")

    # Check email uniqueness if changing
    if "email" in update_data and update_data["email"] != admin.email:
        existing = (
            db.query(AdminUser)
            .filter(
                AdminUser.company_id == company_id,
                AdminUser.email == update_data["email"],
                AdminUser.user_id != user_id,
            )
            .first()
        )
        if existing:
            raise HTTPException(status_code=400, detail="이미 등록된 이메일입니다.")

    for key, value in update_data.items():
        setattr(admin, key, value)
    db.commit()
    db.refresh(admin)
    return admin


@router.delete("/{user_id}")
def delete_admin(
    user_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
):
    company_id = user["company_id"]
    admin = (
        db.query(AdminUser)
        .filter(AdminUser.user_id == user_id, AdminUser.company_id == company_id)
        .first()
    )
    if not admin:
        raise HTTPException(status_code=404, detail="관리자를 찾을 수 없습니다.")
    if admin.user_id == user["user_id"]:
        raise HTTPException(status_code=400, detail="자기 자신은 삭제할 수 없습니다.")

    db.delete(admin)
    db.commit()
    return {"success": True, "message": "관리자가 삭제되었습니다."}


@router.patch("/{user_id}/reset-password")
def reset_password(
    user_id: int,
    data: AdminPasswordChange,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
):
    """Admin resets another user's password."""
    company_id = user["company_id"]
    admin = (
        db.query(AdminUser)
        .filter(AdminUser.user_id == user_id, AdminUser.company_id == company_id)
        .first()
    )
    if not admin:
        raise HTTPException(status_code=404, detail="관리자를 찾을 수 없습니다.")

    admin.password_hash = hash_password(data.new_password)
    db.commit()
    return {"success": True, "message": "비밀번호가 초기화되었습니다."}
