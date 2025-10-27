"""Contract tests für Inbox Read-Model-Views."""
import pytest

try:
    import psycopg  # bevorzugter Treiber (psycopg v3)

    def _connect(dsn: str):
        return psycopg.connect(dsn)

except ImportError:  # Fallback für Umgebungen mit psycopg2
    import psycopg2 as psycopg

    def _connect(dsn: str):
        return psycopg.connect(dsn)

from backend.core.config import settings


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
    
    conn = _connect(
        settings.database_url.replace("postgresql+psycopg2://", "postgresql://").replace(
            "postgresql+psycopg://", "postgresql://"
        )
    )
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'inbox_parsed' 
            AND table_name = 'v_inbox_by_tenant'
            ORDER BY column_name
        """)
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
    
    conn = _connect(
        settings.database_url.replace("postgresql+psycopg2://", "postgresql://").replace(
            "postgresql+psycopg://", "postgresql://"
        )
    )
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_schema = 'inbox_parsed' 
            AND table_name = 'v_invoices_latest'
            ORDER BY column_name
        """)
        actual_columns = {row[0] for row in cur.fetchall()}
        cur.close()
        
        # Check that all expected columns exist
        missing = expected_columns - actual_columns
        assert not missing, f"Missing columns in v_invoices_latest: {missing}"
        
    finally:
        conn.close()
