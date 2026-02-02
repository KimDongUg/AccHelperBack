from datetime import datetime

from pydantic import BaseModel


class LoginRequest(BaseModel):
    company_code: str
    email: str
    password: str
    remember: bool = False


class SessionData(BaseModel):
    user_id: int
    username: str | None = None
    company_id: int
    company_code: str
    company_name: str
    email: str
    full_name: str | None = None
    role: str
    permissions: str | None = None
    login_time: str
    expiry_time: str


class LoginResponse(BaseModel):
    success: bool
    message: str
    session: SessionData | None = None


class AuthCheckResponse(BaseModel):
    authenticated: bool
    session: SessionData | None = None
