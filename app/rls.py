"""Row-Level Security (RLS) setup for PostgreSQL.

Applies RLS policies so that each tenant can only access its own rows.
DB sessions must SET app.tenant_id before queries.
"""

import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger("acchelper")

RLS_TABLES = [
    "qa_knowledge",
    "qa_embeddings",
    "chat_logs",
    "feedbacks",
    "tenant_usage_monthly",
]


def setup_rls(engine: Engine):
    """Create RLS policies on tenant-scoped tables. PostgreSQL only."""
    if "sqlite" in str(engine.url):
        logger.info("RLS skipped (SQLite)")
        return

    with engine.connect() as conn:
        for table in RLS_TABLES:
            try:
                # Check if table exists
                exists = conn.execute(text(
                    "SELECT 1 FROM information_schema.tables WHERE table_name = :t"
                ), {"t": table}).fetchone()
                if not exists:
                    continue

                # Enable RLS
                conn.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))

                # Drop existing policy to make idempotent
                conn.execute(text(
                    f"DROP POLICY IF EXISTS tenant_isolation ON {table}"
                ))

                # Create policy: rows visible only when company_id matches app.tenant_id
                conn.execute(text(
                    f"CREATE POLICY tenant_isolation ON {table} "
                    f"USING (company_id = current_setting('app.tenant_id', true)::int)"
                ))

                # Allow the app role to bypass RLS when tenant_id is not set (super_admin)
                conn.execute(text(
                    f"DROP POLICY IF EXISTS super_admin_bypass ON {table}"
                ))
                conn.execute(text(
                    f"CREATE POLICY super_admin_bypass ON {table} "
                    f"USING (current_setting('app.tenant_id', true) IS NULL "
                    f"OR current_setting('app.tenant_id', true) = '' "
                    f"OR current_setting('app.tenant_id', true) = '0')"
                ))

                logger.info("RLS enabled on %s", table)
            except Exception as e:
                logger.warning("RLS setup failed for %s: %s", table, e)

        conn.commit()
    logger.info("RLS setup completed")


def set_tenant_id(conn, tenant_id: int | None):
    """Set app.tenant_id for the current DB session/transaction."""
    value = str(tenant_id) if tenant_id and tenant_id != 0 else "0"
    conn.execute(text(f"SET LOCAL app.tenant_id = '{value}'"))
