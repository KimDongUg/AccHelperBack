import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# Application
APP_ENV = os.getenv("APP_ENV", "development")
DEBUG = os.getenv("DEBUG", "true").lower() in ("true", "1", "yes")

# Database
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'acchelper.db'}")

# Security
SECRET_KEY = os.getenv("SECRET_KEY", "acc-helper-secret-key-change-in-production")
SESSION_EXPIRE_HOURS = int(os.getenv("SESSION_EXPIRE_HOURS", "24"))

# CORS
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")

# Trusted Hosts
TRUSTED_HOSTS = os.getenv("TRUSTED_HOSTS", "").split(",") if os.getenv("TRUSTED_HOSTS") else []

# Rate Limiting
RATE_LIMIT_CHAT = os.getenv("RATE_LIMIT_CHAT", "60/minute")
RATE_LIMIT_AUTH = os.getenv("RATE_LIMIT_AUTH", "30/minute")

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# SMTP (Naver)
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "")
SITE_URL = os.getenv("SITE_URL", "http://localhost:8000")

# Rate Limiting (password reset — stricter)
RATE_LIMIT_PASSWORD_RESET = os.getenv("RATE_LIMIT_PASSWORD_RESET", "5/minute")

# Toss Payments
TOSS_CLIENT_KEY = os.getenv("TOSS_CLIENT_KEY", "")
TOSS_SECRET_KEY = os.getenv("TOSS_SECRET_KEY", "")

# OpenAI / RAG
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"))
CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", os.getenv("CHAT_MODEL", "gpt-4o-mini"))
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "6"))
RAG_MIN_SCORE = float(os.getenv("RAG_MIN_SCORE", "0.25"))

# JWT — no default; must be set via env in production
_jwt_secret_raw = os.getenv("JWT_SECRET_KEY", "").strip()
if not _jwt_secret_raw and APP_ENV != "development":
    raise RuntimeError(
        "JWT_SECRET_KEY 환경변수가 설정되지 않았습니다. "
        "프로덕션 환경에서는 반드시 강력한 랜덤 시크릿을 설정하세요."
    )
JWT_SECRET_KEY = _jwt_secret_raw or SECRET_KEY  # dev-only fallback
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))

# Upload
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(DATA_DIR / "uploads")))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Static files
STATIC_CACHE_MAX_AGE = int(os.getenv("STATIC_CACHE_MAX_AGE", "86400"))
