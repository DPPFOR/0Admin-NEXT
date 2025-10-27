"""Contract tests for inbox read model database views.

Ensures that database views have expected columns to catch schema mismatches early.
These tests require a live Postgres connection and are therefore optional in CI.
"""
import os

import pytest

RUN_DB_TESTS = os.getenv("RUN_DB_TESTS") == "1"

if not RUN_DB_TESTS:
    pytest.skip("requires RUN_DB_TESTS=1 and DATABASE_URL", allow_module_level=True)

from backend.core.config import settings  # noqa: E402

DB_URL = getattr(settings, "database_url", None)

if not DB_URL:
    pytest.skip("requires RUN_DB_TESTS=1 and DATABASE_URL", allow_module_level=True)

import psycopg2  # noqa: E402


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
    conn = psycopg2.connect(DB_URL.replace("postgresql+psycopg2://", "postgresql://"))
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
    conn = psycopg2.connect(DB_URL.replace("postgresql+psycopg2://", "postgresql://"))
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
