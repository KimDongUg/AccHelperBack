from datetime import datetime

from pydantic import BaseModel, EmailStr


class AdminCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None
    phone: str | None = None
    department: str | None = None
    position: str | None = None
    role: str = "admin"


class AdminUpdate(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = None
    phone: str | None = None
    department: str | None = None
    position: str | None = None
    role: str | None = None
    is_active: bool | None = None


class AdminPasswordChange(BaseModel):
    current_password: str | None = None
    new_password: str


class AdminResponse(BaseModel):
    user_id: int
    company_id: int
    username: str | None = None
    email: str
    full_name: str | None = None
    phone: str | None = None
    department: str | None = None
    position: str | None = None
    role: str
    is_active: bool
    created_at: datetime
    last_login: datetime | None = None

    model_config = {"from_attributes": True}


class AdminListResponse(BaseModel):
    items: list[AdminResponse]
    total: int
