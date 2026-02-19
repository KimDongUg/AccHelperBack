from datetime import datetime

from pydantic import BaseModel


class LoginRequest(BaseModel):
    company_id: int
    email: str
    password: str
    remember: bool = False


class SessionData(BaseModel):
    user_id: int
    username: str | None = None
    company_id: int
    company_name: str
    email: str
    full_name: str | None = None
    role: str
    permissions: str | None = None
    subscription_plan: str | None = None
    billing_active: bool = False
    login_time: str
    expiry_time: str


class LoginResponse(BaseModel):
    success: bool
    message: str
    session: SessionData | None = None


class RegisterRequest(BaseModel):
    company_id: int
    email: str
    password: str
    full_name: str
    phone: str | None = None


class RegisterResponse(BaseModel):
    success: bool
    message: str


class AuthCheckResponse(BaseModel):
    authenticated: bool
    session: SessionData | None = None


class FindEmailRequest(BaseModel):
    company_id: int
    full_name: str


class FindEmailResponse(BaseModel):
    success: bool
    message: str
    masked_email: str | None = None


class ResetPasswordRequest(BaseModel):
    company_id: int
    email: str


class ResetPasswordResponse(BaseModel):
    success: bool
    message: str
