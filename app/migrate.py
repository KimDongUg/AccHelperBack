"""Idempotent migration script for multi-tenant conversion.

Uses PRAGMA table_info to check column existence, then ALTER TABLE ADD COLUMN
for missing columns. Creates default company and backfills existing rows.
"""

import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger("acchelper")


def _table_exists(conn, table_name: str) -> bool:
    result = conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:t"),
        {"t": table_name},
    )
    return result.fetchone() is not None


def _get_columns(conn, table_name: str) -> set[str]:
    result = conn.execute(text(f"PRAGMA table_info({table_name})"))
    return {row[1] for row in result.fetchall()}


def _add_column_if_missing(conn, table_name: str, col_name: str, col_def: str):
    cols = _get_columns(conn, table_name)
    if col_name not in cols:
        stmt = f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def}"
        conn.execute(text(stmt))
        logger.info("Added column %s.%s", table_name, col_name)


def _pg_add_column_if_missing(conn, table_name: str, col_name: str, col_def: str):
    """PostgreSQL: add column if it doesn't exist."""
    result = conn.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = :table AND column_name = :col"
    ), {"table": table_name, "col": col_name})
    if result.fetchone() is None:
        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def}"))
        logger.info("PG: Added column %s.%s", table_name, col_name)


def _pg_table_exists(conn, table_name: str) -> bool:
    result = conn.execute(text(
        "SELECT 1 FROM information_schema.tables WHERE table_name = :t"
    ), {"t": table_name})
    return result.fetchone() is not None


def _run_pg_migration(engine: Engine):
    """PostgreSQL column migrations for existing tables.

    Uses separate transactions for safe DDL vs risky pgvector operations
    so that a vector index failure doesn't poison the entire migration.
    """
    # --- Transaction 1: pgvector extension + safe column migrations ---
    with engine.connect() as conn:
        # Enable pgvector extension
        try:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            logger.info("PG: pgvector extension ensured")
        except Exception as e:
            logger.warning("PG: Could not create pgvector extension: %s", e)
            conn.rollback()

        # companies table
        _pg_add_column_if_missing(conn, "companies", "building_type", "VARCHAR(20)")
        _pg_add_column_if_missing(conn, "companies", "business_number", "VARCHAR(20)")
        _pg_add_column_if_missing(conn, "companies", "industry", "VARCHAR(50)")
        _pg_add_column_if_missing(conn, "companies", "address", "TEXT")
        _pg_add_column_if_missing(conn, "companies", "phone", "VARCHAR(20)")
        _pg_add_column_if_missing(conn, "companies", "logo_url", "VARCHAR(500)")
        _pg_add_column_if_missing(conn, "companies", "trial_ends_at", "TIMESTAMP")
        _pg_add_column_if_missing(conn, "companies", "deleted_at", "TIMESTAMP")
        _pg_add_column_if_missing(conn, "companies", "qa_customized", "BOOLEAN DEFAULT FALSE")
        _pg_add_column_if_missing(conn, "companies", "status", "VARCHAR(20) DEFAULT 'active'")
        _pg_add_column_if_missing(conn, "companies", "approval_status", "VARCHAR(20) DEFAULT 'pending'")
        _pg_add_column_if_missing(conn, "companies", "approved_at", "TIMESTAMP")
        _pg_add_column_if_missing(conn, "companies", "approved_by", "INTEGER")
        _pg_add_column_if_missing(conn, "companies", "rejection_reason", "TEXT")
        _pg_add_column_if_missing(conn, "companies", "hero_text", "TEXT")
        _pg_add_column_if_missing(conn, "companies", "greeting_text", "TEXT")
        _pg_add_column_if_missing(conn, "companies", "categories", "TEXT")
        _pg_add_column_if_missing(conn, "companies", "notice_active", "BOOLEAN DEFAULT FALSE")
        _pg_add_column_if_missing(conn, "companies", "notice_text", "TEXT")
        _pg_add_column_if_missing(conn, "companies", "notice_text_link", "VARCHAR(500)")
        _pg_add_column_if_missing(conn, "companies", "notice_image_url", "VARCHAR(500)")
        _pg_add_column_if_missing(conn, "companies", "notice_image_link", "VARCHAR(500)")
        # Backfill: mark existing companies as approved
        conn.execute(text(
            "UPDATE companies SET approval_status = 'approved' WHERE approval_status IS NULL"
        ))

        # Reset sample company (1000) QA if it contains un-anonymized data
        # (account numbers, real company names, etc.) so seed re-copies cleanly.
        _has_raw = conn.execute(text(
            "SELECT COUNT(*) FROM qa_knowledge WHERE company_id = 1000"
            " AND (answer LIKE '%세종%' OR answer LIKE '%355-0031%'"
            "      OR answer LIKE '%915-910007%' OR answer LIKE '%60771%'"
            "      OR answer LIKE '%070-%' OR answer LIKE '%044-%'"
            "      OR answer LIKE '%1577-%' OR answer LIKE '%1588-%')"
        )).scalar()
        if _has_raw and _has_raw > 0:
            conn.execute(text(
                "DELETE FROM qa_knowledge WHERE company_id = 1000"
            ))
            logger.info("PG: Reset sample company 1000 QA for re-anonymization")

        # qa_knowledge table — new RAG columns + created_by
        if _pg_table_exists(conn, "qa_knowledge"):
            _pg_add_column_if_missing(conn, "qa_knowledge", "aliases", "TEXT DEFAULT ''")
            _pg_add_column_if_missing(conn, "qa_knowledge", "tags", "TEXT DEFAULT ''")
            _pg_add_column_if_missing(conn, "qa_knowledge", "created_by", "VARCHAR(100)")
            _pg_add_column_if_missing(conn, "qa_knowledge", "updated_by", "INTEGER")
            _pg_add_column_if_missing(conn, "qa_knowledge", "view_count", "INTEGER DEFAULT 0")
            _pg_add_column_if_missing(conn, "qa_knowledge", "used_count", "INTEGER DEFAULT 0")
            # Fix: created_by was INTEGER, now VARCHAR(100)
            try:
                conn.execute(text(
                    "ALTER TABLE qa_knowledge "
                    "ALTER COLUMN created_by TYPE VARCHAR(100) USING created_by::text"
                ))
            except Exception:
                pass  # already VARCHAR or doesn't exist

        # chat_logs table — RAG columns
        if _pg_table_exists(conn, "chat_logs"):
            _pg_add_column_if_missing(conn, "chat_logs", "used_rag", "BOOLEAN DEFAULT FALSE")
            _pg_add_column_if_missing(conn, "chat_logs", "evidence_ids", "TEXT DEFAULT ''")

        # complaints table — writer_phone, privacy_agreed_at
        if _pg_table_exists(conn, "complaints"):
            _pg_add_column_if_missing(conn, "complaints", "writer_phone", "VARCHAR(30)")
            _pg_add_column_if_missing(conn, "complaints", "privacy_agreed_at", "TIMESTAMP")

        # complaint_persons 테이블 — 민원인 별도 관리
        if not _pg_table_exists(conn, "complaint_persons"):
            conn.execute(text("""
                CREATE TABLE complaint_persons (
                    id SERIAL PRIMARY KEY,
                    company_id INTEGER REFERENCES companies(company_id) ON DELETE CASCADE,
                    dong VARCHAR(20) NOT NULL,
                    ho VARCHAR(20) NOT NULL,
                    name VARCHAR(100) NOT NULL,
                    phone VARCHAR(30),
                    first_complained_at TIMESTAMP DEFAULT NOW(),
                    last_complained_at TIMESTAMP DEFAULT NOW(),
                    complaint_count INTEGER DEFAULT 1
                )
            """))
            logger.info("PG: Created table complaint_persons")

        # feedbacks table — status + session_id
        if _pg_table_exists(conn, "feedbacks"):
            _pg_add_column_if_missing(conn, "feedbacks", "session_id", "VARCHAR(100)")
            _pg_add_column_if_missing(conn, "feedbacks", "status", "VARCHAR(20) DEFAULT 'pending'")

        # unanswered_questions table — 알림톡 발송 추적 컬럼
        if _pg_table_exists(conn, "unanswered_questions"):
            _pg_add_column_if_missing(conn, "unanswered_questions", "alert_sent_at", "TIMESTAMP")
            _pg_add_column_if_missing(conn, "unanswered_questions", "alert_count", "INTEGER DEFAULT 0")

        # admin_users table — 알림톡 수신 여부
        _pg_add_column_if_missing(conn, "admin_users", "receive_unanswered_alert", "BOOLEAN DEFAULT TRUE")

        # --- 우리아파트 당근 market 테이블 (PostgreSQL) ---
        if not _pg_table_exists(conn, "apartment_residents"):
            conn.execute(text("""
                CREATE TABLE apartment_residents (
                    id SERIAL PRIMARY KEY,
                    building VARCHAR(20) NOT NULL,
                    unit_number VARCHAR(20) NOT NULL,
                    resident_name VARCHAR(100),
                    resident_phone VARCHAR(30),
                    owner_name VARCHAR(100),
                    owner_phone VARCHAR(30),
                    company_id INTEGER,
                    is_self_registered BOOLEAN DEFAULT FALSE,
                    is_verified BOOLEAN DEFAULT TRUE,
                    registered_at TIMESTAMP DEFAULT NOW()
                )
            """))
            logger.info("PG: Created table apartment_residents")
        else:
            _pg_add_column_if_missing(conn, "apartment_residents", "company_id", "INTEGER")
            _pg_add_column_if_missing(conn, "apartment_residents", "is_self_registered", "BOOLEAN DEFAULT FALSE")
            _pg_add_column_if_missing(conn, "apartment_residents", "is_verified", "BOOLEAN DEFAULT TRUE")
            _pg_add_column_if_missing(conn, "apartment_residents", "registered_at", "TIMESTAMP DEFAULT NOW()")

        if not _pg_table_exists(conn, "market_posts"):
            conn.execute(text("""
                CREATE TABLE market_posts (
                    id SERIAL PRIMARY KEY,
                    category VARCHAR(50) NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    content TEXT NOT NULL,
                    price INTEGER DEFAULT 0,
                    status VARCHAR(30) DEFAULT '판매중',
                    writer_building VARCHAR(20) NOT NULL,
                    writer_unit VARCHAR(20) NOT NULL,
                    is_hidden BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """))
            logger.info("PG: Created table market_posts")

        if not _pg_table_exists(conn, "market_images"):
            conn.execute(text("""
                CREATE TABLE market_images (
                    id SERIAL PRIMARY KEY,
                    post_id INTEGER NOT NULL REFERENCES market_posts(id) ON DELETE CASCADE,
                    image_url TEXT NOT NULL
                )
            """))
            logger.info("PG: Created table market_images")

        if not _pg_table_exists(conn, "market_comments"):
            conn.execute(text("""
                CREATE TABLE market_comments (
                    id SERIAL PRIMARY KEY,
                    post_id INTEGER NOT NULL REFERENCES market_posts(id) ON DELETE CASCADE,
                    writer_unit VARCHAR(20) NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """))
            logger.info("PG: Created table market_comments")

        if not _pg_table_exists(conn, "market_reports"):
            conn.execute(text("""
                CREATE TABLE market_reports (
                    id SERIAL PRIMARY KEY,
                    post_id INTEGER NOT NULL REFERENCES market_posts(id) ON DELETE CASCADE,
                    reporter_unit VARCHAR(20) NOT NULL,
                    reason VARCHAR(100) NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """))
            logger.info("PG: Created table market_reports")

        conn.commit()
    logger.info("PG: Column migrations committed")

    # --- Transaction 2: Fix embedding column type + HNSW index ---
    # This is isolated so failure doesn't break the rest of startup.
    with engine.connect() as conn:
        if _pg_table_exists(conn, "qa_embeddings"):
            try:
                # Check current column type — if it's 'text', ALTER to vector(1536)
                result = conn.execute(text(
                    "SELECT data_type, udt_name FROM information_schema.columns "
                    "WHERE table_name = 'qa_embeddings' AND column_name = 'embedding'"
                ))
                row = result.fetchone()
                if row and row[1] != "vector":
                    logger.info("PG: embedding column is '%s', converting to vector(1536)", row[1])
                    # Drop existing data (text values can't cast to vector)
                    conn.execute(text(
                        "ALTER TABLE qa_embeddings "
                        "ALTER COLUMN embedding TYPE vector(1536) "
                        "USING NULL"
                    ))
                    logger.info("PG: embedding column converted to vector(1536)")

                # Now create the HNSW index
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_qa_embeddings_vector_cosine "
                    "ON qa_embeddings USING hnsw (embedding vector_cosine_ops)"
                ))
                logger.info("PG: HNSW vector index ensured")
                conn.commit()
            except Exception as e:
                logger.warning("PG: Could not fix embedding column/index: %s", e)
                conn.rollback()

    logger.info("PostgreSQL migration completed")


def run_migration(engine: Engine):
    """Run idempotent migration before create_all."""
    if engine.url.get_backend_name() != "sqlite":
        _run_pg_migration(engine)
        return

    with engine.connect() as conn:
        # --- admin_users table ---
        if _table_exists(conn, "admin_users"):
            _add_column_if_missing(conn, "admin_users", "company_id", "INTEGER DEFAULT 1")
            _add_column_if_missing(conn, "admin_users", "full_name", "VARCHAR(100)")
            _add_column_if_missing(conn, "admin_users", "phone", "VARCHAR(20)")
            _add_column_if_missing(conn, "admin_users", "department", "VARCHAR(50)")
            _add_column_if_missing(conn, "admin_users", "position", "VARCHAR(50)")
            _add_column_if_missing(conn, "admin_users", "role", "VARCHAR(20) DEFAULT 'admin'")
            _add_column_if_missing(conn, "admin_users", "permissions", "TEXT")

            # Backfill: set email from username if email is null
            conn.execute(text(
                "UPDATE admin_users SET email = username || '@example.com' "
                "WHERE email IS NULL OR email = ''"
            ))

            # Backfill: ensure company_id = 1 for existing rows
            conn.execute(text(
                "UPDATE admin_users SET company_id = 1 WHERE company_id IS NULL"
            ))

            # Set first admin as super_admin if no super_admin exists
            conn.execute(text(
                "UPDATE admin_users SET role = 'super_admin' "
                "WHERE user_id = (SELECT MIN(user_id) FROM admin_users) "
                "AND NOT EXISTS (SELECT 1 FROM admin_users WHERE role = 'super_admin')"
            ))

        # --- companies table ---
        if _table_exists(conn, "companies"):
            _add_column_if_missing(conn, "companies", "building_type", "VARCHAR(20)")
            _add_column_if_missing(conn, "companies", "qa_customized", "BOOLEAN DEFAULT 0")
            _add_column_if_missing(conn, "companies", "status", "VARCHAR(20) DEFAULT 'active'")
            _add_column_if_missing(conn, "companies", "approval_status", "VARCHAR(20) DEFAULT 'pending'")
            _add_column_if_missing(conn, "companies", "approved_at", "DATETIME")
            _add_column_if_missing(conn, "companies", "approved_by", "INTEGER")
            _add_column_if_missing(conn, "companies", "rejection_reason", "TEXT")
            _add_column_if_missing(conn, "companies", "hero_text", "TEXT")
            _add_column_if_missing(conn, "companies", "greeting_text", "TEXT")
            _add_column_if_missing(conn, "companies", "categories", "TEXT")
            # Backfill: mark existing companies as approved
            conn.execute(text(
                "UPDATE companies SET approval_status = 'approved' WHERE approval_status IS NULL"
            ))

        # --- qa_knowledge table ---
        if _table_exists(conn, "qa_knowledge"):
            _add_column_if_missing(conn, "qa_knowledge", "company_id", "INTEGER DEFAULT 1")
            _add_column_if_missing(conn, "qa_knowledge", "created_by", "VARCHAR(100)")
            _add_column_if_missing(conn, "qa_knowledge", "updated_by", "INTEGER")
            _add_column_if_missing(conn, "qa_knowledge", "view_count", "INTEGER DEFAULT 0")
            _add_column_if_missing(conn, "qa_knowledge", "used_count", "INTEGER DEFAULT 0")
            _add_column_if_missing(conn, "qa_knowledge", "aliases", "TEXT DEFAULT ''")
            _add_column_if_missing(conn, "qa_knowledge", "tags", "TEXT DEFAULT ''")

            # Backfill company_id
            conn.execute(text(
                "UPDATE qa_knowledge SET company_id = 1 WHERE company_id IS NULL"
            ))

        # --- chat_logs table ---
        if _table_exists(conn, "chat_logs"):
            _add_column_if_missing(conn, "chat_logs", "company_id", "INTEGER DEFAULT 1")
            _add_column_if_missing(conn, "chat_logs", "confidence_score", "REAL")
            _add_column_if_missing(conn, "chat_logs", "response_time_ms", "INTEGER")
            _add_column_if_missing(conn, "chat_logs", "user_feedback", "VARCHAR(20)")
            _add_column_if_missing(conn, "chat_logs", "ip_address", "VARCHAR(45)")
            _add_column_if_missing(conn, "chat_logs", "user_agent", "VARCHAR(500)")
            _add_column_if_missing(conn, "chat_logs", "used_rag", "BOOLEAN DEFAULT 0")
            _add_column_if_missing(conn, "chat_logs", "evidence_ids", "TEXT DEFAULT ''")

            # Backfill company_id
            conn.execute(text(
                "UPDATE chat_logs SET company_id = 1 WHERE company_id IS NULL"
            ))

        # --- complaints table ---
        if _table_exists(conn, "complaints"):
            _add_column_if_missing(conn, "complaints", "writer_phone", "VARCHAR(30)")
            _add_column_if_missing(conn, "complaints", "privacy_agreed_at", "DATETIME")

        # --- complaint_persons 테이블 ---
        if not _table_exists(conn, "complaint_persons"):
            conn.execute(text("""
                CREATE TABLE complaint_persons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_id INTEGER REFERENCES companies(company_id) ON DELETE CASCADE,
                    dong VARCHAR(20) NOT NULL,
                    ho VARCHAR(20) NOT NULL,
                    name VARCHAR(100) NOT NULL,
                    phone VARCHAR(30),
                    first_complained_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_complained_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    complaint_count INTEGER DEFAULT 1
                )
            """))
            logger.info("Created table complaint_persons")

        # --- feedbacks table ---
        if _table_exists(conn, "feedbacks"):
            _add_column_if_missing(conn, "feedbacks", "session_id", "VARCHAR(100)")
            _add_column_if_missing(conn, "feedbacks", "status", "VARCHAR(20) DEFAULT 'pending'")

        # --- unanswered_questions table: 알림톡 발송 추적 ---
        if _table_exists(conn, "unanswered_questions"):
            _add_column_if_missing(conn, "unanswered_questions", "alert_sent_at", "DATETIME")
            _add_column_if_missing(conn, "unanswered_questions", "alert_count", "INTEGER DEFAULT 0")

        # --- admin_users table: 알림톡 수신 여부 ---
        if _table_exists(conn, "admin_users"):
            _add_column_if_missing(conn, "admin_users", "receive_unanswered_alert", "BOOLEAN DEFAULT 1")

        # --- 우리아파트 당근 market 테이블 ---
        if not _table_exists(conn, "apartment_residents"):
            conn.execute(text("""
                CREATE TABLE apartment_residents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    building VARCHAR(20) NOT NULL,
                    unit_number VARCHAR(20) NOT NULL,
                    resident_name VARCHAR(100),
                    resident_phone VARCHAR(30),
                    owner_name VARCHAR(100),
                    owner_phone VARCHAR(30),
                    company_id INTEGER,
                    is_self_registered BOOLEAN DEFAULT 0,
                    is_verified BOOLEAN DEFAULT 1,
                    registered_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            logger.info("Created table apartment_residents")
        else:
            _add_column_if_missing(conn, "apartment_residents", "company_id", "INTEGER")
            _add_column_if_missing(conn, "apartment_residents", "is_self_registered", "BOOLEAN DEFAULT 0")
            _add_column_if_missing(conn, "apartment_residents", "is_verified", "BOOLEAN DEFAULT 1")
            _add_column_if_missing(conn, "apartment_residents", "registered_at", "DATETIME DEFAULT CURRENT_TIMESTAMP")

        if not _table_exists(conn, "market_posts"):
            conn.execute(text("""
                CREATE TABLE market_posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category VARCHAR(50) NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    content TEXT NOT NULL,
                    price INTEGER DEFAULT 0,
                    status VARCHAR(30) DEFAULT '판매중',
                    writer_building VARCHAR(20) NOT NULL,
                    writer_unit VARCHAR(20) NOT NULL,
                    is_hidden BOOLEAN DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            logger.info("Created table market_posts")

        if not _table_exists(conn, "market_images"):
            conn.execute(text("""
                CREATE TABLE market_images (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id INTEGER NOT NULL REFERENCES market_posts(id) ON DELETE CASCADE,
                    image_url TEXT NOT NULL
                )
            """))
            logger.info("Created table market_images")

        if not _table_exists(conn, "market_comments"):
            conn.execute(text("""
                CREATE TABLE market_comments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id INTEGER NOT NULL REFERENCES market_posts(id) ON DELETE CASCADE,
                    writer_unit VARCHAR(20) NOT NULL,
                    content TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            logger.info("Created table market_comments")

        if not _table_exists(conn, "market_reports"):
            conn.execute(text("""
                CREATE TABLE market_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id INTEGER NOT NULL REFERENCES market_posts(id) ON DELETE CASCADE,
                    reporter_unit VARCHAR(20) NOT NULL,
                    reason VARCHAR(100) NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            logger.info("Created table market_reports")

        conn.commit()
        logger.info("Migration completed successfully")
