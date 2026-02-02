from datetime import datetime

from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str
    remember: bool = False


class SessionData(BaseModel):
    user_id: int
    username: str
    login_time: str
    expiry_time: str


class LoginResponse(BaseModel):
    success: bool
    message: str
    session: SessionData | None = None


class AuthCheckResponse(BaseModel):
    authenticated: bool
    session: SessionData | None = None
