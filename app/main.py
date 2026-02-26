import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text

from app.config import APP_ENV, CORS_ORIGINS, DATABASE_URL, LOG_LEVEL, TRUSTED_HOSTS
from app.database import Base, SessionLocal, engine
from app.middleware import RequestLoggingMiddleware, SecurityHeadersMiddleware, setup_logging
from app.migrate import run_migration
from app.models import (
    AdminActivityLog, AdminUser, BillingKey, ChatLog, Company,
    Feedback, PaymentHistory, PromptTemplate, QaEmbedding, QaKnowledge,
    TenantQuota, TenantUsageMonthly, UnansweredQuestion,
)
from app.rate_limit import limiter
from app.routers import (
    activity_logs, admin_dashboard, admins, auth, billing, chat,
    companies, qa, stats,
)
from app.routers import feedback as feedback_router
from app.routers import prompts as prompts_router
from app.routers import super_admin as super_admin_router
from app.routers import unanswered_questions as unanswered_questions_router
from app.routers import upload as upload_router
from app.rls import setup_rls
from app.seed import seed_data

logger = logging.getLogger("acchelper")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

_start_time: float = 0.0

INDEX_STATEMENTS = [
    "CREATE INDEX IF NOT EXISTS ix_qa_knowledge_category ON qa_knowledge (category)",
    "CREATE INDEX IF NOT EXISTS ix_qa_knowledge_is_active ON qa_knowledge (is_active)",
    "CREATE INDEX IF NOT EXISTS ix_qa_knowledge_category_is_active ON qa_knowledge (category, is_active)",
    "CREATE INDEX IF NOT EXISTS ix_qa_knowledge_company_id ON qa_knowledge (company_id)",
    "CREATE INDEX IF NOT EXISTS ix_qa_knowledge_company_category ON qa_knowledge (company_id, category)",
    "CREATE INDEX IF NOT EXISTS ix_chat_logs_session_id ON chat_logs (session_id)",
    "CREATE INDEX IF NOT EXISTS ix_chat_logs_qa_id ON chat_logs (qa_id)",
    "CREATE INDEX IF NOT EXISTS ix_chat_logs_category ON chat_logs (category)",
    "CREATE INDEX IF NOT EXISTS ix_chat_logs_timestamp ON chat_logs (timestamp)",
    "CREATE INDEX IF NOT EXISTS ix_chat_logs_company_id ON chat_logs (company_id)",
    "CREATE INDEX IF NOT EXISTS ix_admin_users_company_id ON admin_users (company_id)",
    "CREATE INDEX IF NOT EXISTS ix_admin_activity_logs_company_id ON admin_activity_logs (company_id)",
    "CREATE INDEX IF NOT EXISTS ix_admin_activity_logs_user_id ON admin_activity_logs (user_id)",
    "CREATE INDEX IF NOT EXISTS ix_admin_activity_logs_timestamp ON admin_activity_logs (timestamp)",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _start_time
    _start_time = time.time()

    setup_logging(LOG_LEVEL)
    db_type = DATABASE_URL.split("://")[0] if "://" in DATABASE_URL else "unknown"
    masked_url = DATABASE_URL[:30] + "..." if len(DATABASE_URL) > 30 else DATABASE_URL
    logger.info("Starting AccHelper (env=%s, db_type=%s, url=%s)", APP_ENV, db_type, masked_url)

    try:
        # Run migration before create_all
        run_migration(engine)

        Base.metadata.create_all(bind=engine)

        # Manual index creation only needed for SQLite migration path.
        # PostgreSQL gets indexes from model index=True via create_all.
        if DATABASE_URL.startswith("sqlite"):
            with engine.connect() as conn:
                for stmt in INDEX_STATEMENTS:
                    conn.execute(text(stmt))
                conn.commit()
            logger.info("SQLite indexes ensured")

        # Setup RLS for PostgreSQL
        setup_rls(engine)

        db = SessionLocal()
        try:
            seed_data(db)
        finally:
            db.close()

        logger.info("Database ready")
    except Exception as exc:
        logger.error("Database init failed: %s", exc)

    yield
    logger.info("Shutting down AccHelper")


app = FastAPI(title="경리 도우미 (Accounting Helper)", lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Middleware (order matters: last added = first executed)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
if TRUSTED_HOSTS:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=TRUSTED_HOSTS)

app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(qa.router)
app.include_router(stats.router)
app.include_router(companies.router)
app.include_router(admins.router)
app.include_router(activity_logs.router)
app.include_router(billing.router)
app.include_router(admin_dashboard.router)
app.include_router(feedback_router.router)
app.include_router(prompts_router.router)
app.include_router(super_admin_router.router)
app.include_router(unanswered_questions_router.router)
app.include_router(upload_router.router)

if (STATIC_DIR / "css").exists():
    app.mount("/css", StaticFiles(directory=str(STATIC_DIR / "css")), name="css")
if (STATIC_DIR / "js").exists():
    app.mount("/js", StaticFiles(directory=str(STATIC_DIR / "js")), name="js")


@app.get("/api/health")
def health_check():
    db_status = "connected"
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
    except Exception:
        db_status = "disconnected"

    db_type = "postgresql" if DATABASE_URL.startswith("postgresql") else "sqlite"
    return {
        "status": "healthy" if db_status == "connected" else "unhealthy",
        "database": db_status,
        "database_type": db_type,
        "environment": APP_ENV,
        "uptime_seconds": round(time.time() - _start_time, 1),
    }


_NO_CACHE = "no-cache, no-store, must-revalidate"

if STATIC_DIR.exists():

    @app.get("/", response_class=HTMLResponse)
    async def serve_index():
        response = FileResponse(str(STATIC_DIR / "index.html"))
        response.headers["Cache-Control"] = _NO_CACHE
        return response

    @app.get("/login.html", response_class=HTMLResponse)
    async def serve_login():
        response = FileResponse(str(STATIC_DIR / "login.html"))
        response.headers["Cache-Control"] = _NO_CACHE
        return response

    @app.get("/register.html", response_class=HTMLResponse)
    async def serve_register():
        response = FileResponse(str(STATIC_DIR / "register.html"))
        response.headers["Cache-Control"] = _NO_CACHE
        return response

    @app.get("/admin.html", response_class=HTMLResponse)
    async def serve_admin():
        response = FileResponse(str(STATIC_DIR / "admin.html"))
        response.headers["Cache-Control"] = _NO_CACHE
        return response

    @app.get("/privacy.html", response_class=HTMLResponse)
    async def serve_privacy():
        return FileResponse(str(STATIC_DIR / "privacy.html"))

    @app.get("/terms.html", response_class=HTMLResponse)
    async def serve_terms():
        return FileResponse(str(STATIC_DIR / "terms.html"))

    @app.get("/copyright.html", response_class=HTMLResponse)
    async def serve_copyright():
        return FileResponse(str(STATIC_DIR / "copyright.html"))

    @app.get("/contact.html", response_class=HTMLResponse)
    async def serve_contact():
        return FileResponse(str(STATIC_DIR / "contact.html"))

    @app.get("/billing.html", response_class=HTMLResponse)
    async def serve_billing():
        response = FileResponse(str(STATIC_DIR / "billing.html"))
        response.headers["Cache-Control"] = _NO_CACHE
        return response
