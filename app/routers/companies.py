from datetime import datetime

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from sqlalchemy import text

from app.database import get_db
from app.dependencies import require_admin, require_super_admin
from app.models.admin_user import AdminUser
from app.models.qa_knowledge import QaKnowledge
from app.models.company import Company
from app.schemas.company import (
    CompanyCreate,
    CompanyListResponse,
    CompanyPublicResponse,
    CompanyRegisterRequest,
    CompanyRegisterResponse,
    CompanyResponse,
    CompanyUpdate,
)
from app.services.auth_service import hash_password
from app.services.jwt_service import decode_token

router = APIRouter(prefix="/api/companies", tags=["companies"])


# --- Public endpoints (no auth) ---

@router.get("/public", response_model=list[CompanyPublicResponse])
def list_public_companies(db: Session = Depends(get_db)):
    """List companies for public display (chatbot company selection). Only approved companies."""
    companies = (
        db.query(Company)
        .filter(Company.deleted_at == None, Company.approval_status == "approved")
        .order_by(Company.company_id)
        .all()
    )
    return companies


@router.get("/public/{company_id}", response_model=CompanyPublicResponse)
def get_public_company(
    company_id: int,
    request: Request,
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(None),
):
    """Get public company info by ID. Unapproved companies return 403 unless super_admin."""
    company = (
        db.query(Company)
        .filter(Company.company_id == company_id, Company.is_active == True, Company.deleted_at == None)
        .first()
    )
    if not company:
        raise HTTPException(status_code=404, detail="회사를 찾을 수 없습니다.")

    # 미승인 업체 접근 차단 (super_admin은 허용)
    if company.approval_status != "approved":
        is_super = False
        auth_header = request.headers.get("authorization", "")
        token = auth_header[7:] if auth_header.startswith("Bearer ") else session_token
        if token:
            payload = decode_token(token)
            if payload and payload.get("role") == "super_admin":
                is_super = True
        if not is_super:
            raise HTTPException(status_code=403, detail="승인되지 않은 업체입니다.")

    return company


@router.post("/register", response_model=CompanyRegisterResponse)
def register_company(
    data: CompanyRegisterRequest,
    db: Session = Depends(get_db),
):
    """비로그인 회사 등록 (회사 + 관리자 동시 생성)"""
    # company_id 중복 체크
    if data.company_id is not None:
        existing_id = db.query(Company).filter(Company.company_id == data.company_id).first()
        if existing_id:
            return CompanyRegisterResponse(success=False, message="이미 사용 중인 회사번호입니다.")

    # 사업자번호 중복 체크
    existing_bn = (
        db.query(Company)
        .filter(Company.business_number == data.business_number, Company.deleted_at == None)
        .first()
    )
    if existing_bn:
        return CompanyRegisterResponse(success=False, message="이미 등록된 회사입니다.")

    # 회사 생성
    company = Company(
        company_name=data.company_name,
        building_type=data.building_type,
        business_number=data.business_number,
        industry=data.industry,
        address=data.address,
        phone=data.phone,
    )
    if data.company_id is not None:
        company.company_id = data.company_id
    db.add(company)
    db.flush()  # company_id 확보

    # 수동 company_id 지정 시 PostgreSQL 시퀀스 동기화
    if data.company_id is not None:
        try:
            db.execute(text(
                "SELECT setval('companies_company_id_seq', "
                "(SELECT COALESCE(MAX(company_id), 1) FROM companies))"
            ))
        except Exception:
            pass  # SQLite는 시퀀스 없음

    # 이메일 중복 체크
    dup_email = (
        db.query(AdminUser)
        .filter(AdminUser.company_id == company.company_id, AdminUser.email == data.admin_email)
        .first()
    )
    if dup_email:
        db.rollback()
        return CompanyRegisterResponse(success=False, message="이미 등록된 이메일입니다.")

    # 관리자 생성
    admin = AdminUser(
        company_id=company.company_id,
        email=data.admin_email,
        password_hash=hash_password(data.admin_password),
        full_name=data.admin_name,
        phone=data.admin_phone,
        role="admin",
        is_active=True,
    )
    db.add(admin)

    # 최근 등록된 회사의 QA 데이터 복사
    latest_company = (
        db.query(Company)
        .filter(Company.company_id != company.company_id, Company.deleted_at == None)
        .order_by(Company.created_at.desc())
        .first()
    )
    if latest_company:
        source_qas = db.query(QaKnowledge).filter(
            QaKnowledge.company_id == latest_company.company_id
        ).all()
        for qa in source_qas:
            new_qa = QaKnowledge(
                company_id=company.company_id,
                category=qa.category,
                question=qa.question,
                answer=qa.answer,
                keywords=qa.keywords,
                is_active=qa.is_active,
            )
            db.add(new_qa)

    db.commit()

    return CompanyRegisterResponse(
        success=True,
        message=f"회사가 등록되었습니다. 회사 ID: {company.company_id}",
        company_id=company.company_id,
    )


# --- 로그인한 admin이 자기 회사 조회/수정 ---

@router.get("/me", response_model=CompanyResponse)
def get_my_company(
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
):
    """로그인한 사용자의 회사 정보 조회"""
    company_id = user["company_id"]
    # super_admin(company_id=0)은 전체 관리자이므로 별도 처리
    if company_id == 0:
        raise HTTPException(status_code=400, detail="시스템 관리자는 /api/companies/{id}를 사용하세요.")
    company = db.query(Company).filter(Company.company_id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="회사를 찾을 수 없습니다.")
    return company


@router.put("/me", response_model=CompanyResponse)
def update_my_company(
    data: CompanyUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
):
    """로그인한 사용자의 회사 정보 수정"""
    company_id = user["company_id"]
    if company_id == 0:
        raise HTTPException(status_code=400, detail="시스템 관리자는 /api/companies/{id}를 사용하세요.")
    company = db.query(Company).filter(Company.company_id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="회사를 찾을 수 없습니다.")

    # admin은 구독/한도 변경 불가
    update_data = data.model_dump(exclude_unset=True)
    blocked = {"subscription_plan", "max_qa_count", "max_admins", "is_active"}
    for key in blocked:
        update_data.pop(key, None)

    for key, value in update_data.items():
        setattr(company, key, value)
    company.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(company)
    return company


# --- Admin endpoints (super_admin only) ---

@router.get("", response_model=CompanyListResponse)
def list_companies(
    db: Session = Depends(get_db),
    user: dict = Depends(require_super_admin),
):
    """List all companies (including soft-deleted)."""
    companies = db.query(Company).order_by(Company.company_id).all()
    return CompanyListResponse(items=companies, total=len(companies))


@router.get("/{company_id}", response_model=CompanyResponse)
def get_company(
    company_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_super_admin),
):
    company = db.query(Company).filter(Company.company_id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="회사를 찾을 수 없습니다.")
    return company


@router.post("", response_model=CompanyResponse, status_code=201)
def create_company(
    data: CompanyCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_super_admin),
):
    company = Company(**data.model_dump())
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


@router.put("/{company_id}", response_model=CompanyResponse)
def update_company(
    company_id: int,
    data: CompanyUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_super_admin),
):
    company = db.query(Company).filter(Company.company_id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="회사를 찾을 수 없습니다.")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(company, key, value)
    company.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(company)
    return company


@router.delete("/{company_id}")
def delete_company(
    company_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_super_admin),
):
    """Soft delete a company."""
    company = db.query(Company).filter(Company.company_id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="회사를 찾을 수 없습니다.")
    if company.company_id == 1:
        raise HTTPException(status_code=400, detail="기본 회사는 삭제할 수 없습니다.")

    company.deleted_at = datetime.utcnow()
    company.is_active = False
    company.updated_at = datetime.utcnow()
    db.commit()
    return {"success": True, "message": "회사가 삭제되었습니다."}


@router.post("/{company_id}/restore")
def restore_company(
    company_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_super_admin),
):
    """Restore a soft-deleted company."""
    company = db.query(Company).filter(Company.company_id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="회사를 찾을 수 없습니다.")
    if not company.deleted_at:
        raise HTTPException(status_code=400, detail="삭제되지 않은 회사입니다.")

    company.deleted_at = None
    company.is_active = True
    company.updated_at = datetime.utcnow()
    db.commit()
    return {"success": True, "message": "회사가 복원되었습니다."}


@router.delete("/cleanup/except/{keep_id}")
def cleanup_companies(
    keep_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_super_admin),
):
    """keep_id 회사와 super_admin(company_id=0)만 남기고 나머지 모두 삭제 (super_admin 전용)"""
    tables = [
        "admin_activity_logs",
        "chat_logs",
        "payment_history",
        "billing_keys",
        "qa_knowledge",
        "admin_users",
    ]
    deleted = {}
    for table in tables:
        if table == "admin_users":
            # super_admin(company_id=0)은 보존
            result = db.execute(
                text(f"DELETE FROM {table} WHERE company_id != :kid AND company_id != 0"),
                {"kid": keep_id},
            )
        else:
            result = db.execute(
                text(f"DELETE FROM {table} WHERE company_id != :kid"),
                {"kid": keep_id},
            )
        deleted[table] = result.rowcount

    # 회사 테이블 삭제
    result = db.execute(
        text("DELETE FROM companies WHERE company_id != :kid"),
        {"kid": keep_id},
    )
    deleted["companies"] = result.rowcount

    # auto-increment 시퀀스 리셋 (PostgreSQL)
    max_id = db.execute(text("SELECT COALESCE(MAX(company_id), 0) FROM companies")).scalar()
    seq_reset = None
    try:
        # 실제 시퀀스 이름 조회
        seq_row = db.execute(text(
            "SELECT pg_get_serial_sequence('companies', 'company_id')"
        )).scalar()
        if seq_row:
            db.execute(text(f"SELECT setval('{seq_row}', :val)"), {"val": max_id})
            seq_reset = max_id
    except Exception as e:
        seq_reset = f"error: {e}"

    db.commit()
    return {"success": True, "message": f"회사 {keep_id}번 외 데이터 삭제 완료", "deleted": deleted, "sequence_reset_to": seq_reset}
