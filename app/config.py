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

# Static files
STATIC_CACHE_MAX_AGE = int(os.getenv("STATIC_CACHE_MAX_AGE", "86400"))
