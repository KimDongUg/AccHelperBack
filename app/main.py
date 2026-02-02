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

from app.config import APP_ENV, CORS_ORIGINS, LOG_LEVEL, TRUSTED_HOSTS
from app.database import Base, SessionLocal, engine
from app.middleware import RequestLoggingMiddleware, SecurityHeadersMiddleware, setup_logging
from app.models.admin_user import AdminUser
from app.models.chat_log import ChatLog
from app.models.qa_knowledge import QaKnowledge
from app.rate_limit import limiter
from app.routers import auth, chat, qa, stats
from app.seed import seed_data

logger = logging.getLogger("acchelper")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

_start_time: float = 0.0

INDEX_STATEMENTS = [
    "CREATE INDEX IF NOT EXISTS ix_qa_knowledge_category ON qa_knowledge (category)",
    "CREATE INDEX IF NOT EXISTS ix_qa_knowledge_is_active ON qa_knowledge (is_active)",
    "CREATE INDEX IF NOT EXISTS ix_qa_knowledge_category_is_active ON qa_knowledge (category, is_active)",
    "CREATE INDEX IF NOT EXISTS ix_chat_logs_session_id ON chat_logs (session_id)",
    "CREATE INDEX IF NOT EXISTS ix_chat_logs_qa_id ON chat_logs (qa_id)",
    "CREATE INDEX IF NOT EXISTS ix_chat_logs_category ON chat_logs (category)",
    "CREATE INDEX IF NOT EXISTS ix_chat_logs_timestamp ON chat_logs (timestamp)",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _start_time
    _start_time = time.time()

    setup_logging(LOG_LEVEL)
    logger.info("Starting AccHelper (env=%s)", APP_ENV)

    Base.metadata.create_all(bind=engine)

    with engine.connect() as conn:
        for stmt in INDEX_STATEMENTS:
            conn.execute(text(stmt))
        conn.commit()
    logger.info("Database indexes ensured")

    db = SessionLocal()
    try:
        seed_data(db)
    finally:
        db.close()

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

app.mount("/css", StaticFiles(directory=str(STATIC_DIR / "css")), name="css")
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

    return {
        "status": "healthy" if db_status == "connected" else "unhealthy",
        "database": db_status,
        "environment": APP_ENV,
        "uptime_seconds": round(time.time() - _start_time, 1),
    }


_NO_CACHE = "no-cache, no-store, must-revalidate"


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


@app.get("/admin.html", response_class=HTMLResponse)
async def serve_admin():
    response = FileResponse(str(STATIC_DIR / "admin.html"))
    response.headers["Cache-Control"] = _NO_CACHE
    return response
