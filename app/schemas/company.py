from datetime import datetime

from pydantic import BaseModel


class CompanyCreate(BaseModel):
    company_name: str
    building_type: str | None = None
    business_number: str | None = None
    industry: str | None = None
    address: str | None = None
    phone: str | None = None
    logo_url: str | None = None
    subscription_plan: str = "free"
    max_qa_count: int = 100
    max_admins: int = 5


class CompanyUpdate(BaseModel):
    company_name: str | None = None
    building_type: str | None = None
    business_number: str | None = None
    industry: str | None = None
    address: str | None = None
    phone: str | None = None
    logo_url: str | None = None
    subscription_plan: str | None = None
    max_qa_count: int | None = None
    max_admins: int | None = None
    is_active: bool | None = None


class CompanyResponse(BaseModel):
    company_id: int
    company_name: str
    building_type: str | None = None
    business_number: str | None = None
    industry: str | None = None
    address: str | None = None
    phone: str | None = None
    logo_url: str | None = None
    subscription_plan: str
    max_qa_count: int
    max_admins: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None

    model_config = {"from_attributes": True}


class CompanyPublicResponse(BaseModel):
    company_id: int
    company_name: str
    building_type: str | None = None
    address: str | None = None
    industry: str | None = None
    phone: str | None = None
    logo_url: str | None = None
    is_active: bool = True

    model_config = {"from_attributes": True}


class CompanyListResponse(BaseModel):
    items: list[CompanyResponse]
    total: int


class CompanyRegisterRequest(BaseModel):
    company_name: str
    building_type: str = "오피스텔"  # "오피스텔" | "아파트" | "기타"
    business_number: str
    industry: str | None = None
    address: str | None = None
    phone: str | None = None
    admin_email: str
    admin_password: str
    admin_name: str
    admin_phone: str | None = None


class CompanyRegisterResponse(BaseModel):
    success: bool
    message: str
    company_id: int | None = None
