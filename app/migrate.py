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
    """PostgreSQL column migrations for existing tables."""
    with engine.connect() as conn:
        # Enable pgvector extension
        try:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            logger.info("PG: pgvector extension ensured")
        except Exception as e:
            logger.warning("PG: Could not create pgvector extension: %s", e)

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

        # qa_knowledge table — new RAG columns
        if _pg_table_exists(conn, "qa_knowledge"):
            _pg_add_column_if_missing(conn, "qa_knowledge", "aliases", "TEXT DEFAULT ''")
            _pg_add_column_if_missing(conn, "qa_knowledge", "tags", "TEXT DEFAULT ''")

        # chat_logs table — RAG columns
        if _pg_table_exists(conn, "chat_logs"):
            _pg_add_column_if_missing(conn, "chat_logs", "used_rag", "BOOLEAN DEFAULT FALSE")
            _pg_add_column_if_missing(conn, "chat_logs", "evidence_ids", "TEXT DEFAULT ''")

        conn.commit()
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

        # --- qa_knowledge table ---
        if _table_exists(conn, "qa_knowledge"):
            _add_column_if_missing(conn, "qa_knowledge", "company_id", "INTEGER DEFAULT 1")
            _add_column_if_missing(conn, "qa_knowledge", "created_by", "INTEGER")
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

        conn.commit()
        logger.info("Migration completed successfully")
