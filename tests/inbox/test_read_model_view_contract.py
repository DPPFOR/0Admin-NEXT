"""Contract tests für Inbox Read-Model-Views."""

import os

import pytest

RUN_DB_TESTS = os.getenv("RUN_DB_TESTS") == "1"
if not RUN_DB_TESTS:
    pytest.skip("requires RUN_DB_TESTS=1 and DATABASE_URL/INBOX_DB_URL", allow_module_level=True)

try:
    import psycopg  # bevorzugter Treiber (psycopg v3)

    PsyError = psycopg.Error

    def _connect(dsn: str):
        return psycopg.connect(dsn)

except ImportError:  # Fallback für Umgebungen mit psycopg2
    import psycopg2 as psycopg

    PsyError = psycopg.Error

    def _connect(dsn: str):
        return psycopg.connect(dsn)


from backend.core.config import settings

DB_URL = os.getenv("INBOX_DB_URL") or os.getenv("DATABASE_URL") or settings.database_url


def _dsn() -> str:
    return DB_URL.replace("postgresql+psycopg2://", "postgresql://").replace(
        "postgresql+psycopg://", "postgresql://"
    )


def test_v_inbox_by_tenant_columns():
    """Contract test: v_inbox_by_tenant must have expected columns."""
    expected_columns = {
        "tenant_id",
        "total_items",
        "invoices",
        "payments",
        "others",
        "avg_confidence",
    }

    try:
        conn = _connect(_dsn())
    except PsyError as exc:
        pytest.skip(f"database connection not available: {exc}")
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'inbox_parsed' 
            AND table_name = 'v_inbox_by_tenant'
            ORDER BY column_name
        """
        )
        actual_columns = {row[0] for row in cur.fetchall()}
        cur.close()

        # Check that all expected columns exist
        missing = expected_columns - actual_columns
        assert not missing, f"Missing columns in v_inbox_by_tenant: {missing}"

    finally:
        conn.close()


def test_v_invoices_latest_columns():
    """Contract test: v_invoices_latest must have expected columns."""
    expected_columns = {
        "tenant_id",
        "id",
        "confidence",
        "created_at",
        "amount",
        "invoice_no",
    }

    try:
        conn = _connect(_dsn())
    except PsyError as exc:
        pytest.skip(f"database connection not available: {exc}")
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'inbox_parsed' 
            AND table_name = 'v_invoices_latest'
            ORDER BY column_name
        """
        )
        actual_columns = {row[0] for row in cur.fetchall()}
        cur.close()

        # Check that all expected columns exist
        missing = expected_columns - actual_columns
        assert not missing, f"Missing columns in v_invoices_latest: {missing}"

    finally:
        conn.close()
