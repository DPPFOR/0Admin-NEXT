"""Tests for views contract — auto-generated via PDD."""

import os

import pytest
from sqlalchemy import create_engine, text


class TestViewsContract:
    """Test that views have the expected structure and data types."""

    @pytest.fixture
    def engine(self):
        """Database engine for tests."""
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            pytest.skip("DATABASE_URL not set")
        return create_engine(database_url, future=True)

    def test_v_inbox_by_tenant_structure(self, engine):
        """Test that v_inbox_by_tenant view has expected columns and types."""
        with engine.begin() as conn:
            # Get view structure
            result = conn.execute(
                text(
                    """
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns 
                WHERE table_schema = 'inbox_parsed' 
                AND table_name = 'v_inbox_by_tenant'
                ORDER BY ordinal_position
            """
                )
            )

            columns = {row.column_name: (row.data_type, row.is_nullable) for row in result}

            # Expected columns
            expected_columns = {
                "tenant_id": ("uuid", "NO"),
                "total_items": ("bigint", "YES"),
                "invoices": ("bigint", "YES"),
                "payments": ("bigint", "YES"),
                "others": ("bigint", "YES"),
                "avg_confidence": ("numeric", "YES"),
            }

            # Check that all expected columns exist
            for col_name, (expected_type, expected_nullable) in expected_columns.items():
                assert col_name in columns, f"Column {col_name} not found in view"
                actual_type, actual_nullable = columns[col_name]
                assert (
                    actual_type == expected_type
                ), f"Column {col_name} has type {actual_type}, expected {expected_type}"
                assert (
                    actual_nullable == expected_nullable
                ), f"Column {col_name} nullable is {actual_nullable}, expected {expected_nullable}"

    def test_v_invoices_latest_structure(self, engine):
        """Test that v_invoices_latest view has expected columns and types."""
        with engine.begin() as conn:
            # Get view structure
            result = conn.execute(
                text(
                    """
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns 
                WHERE table_schema = 'inbox_parsed' 
                AND table_name = 'v_invoices_latest'
                ORDER BY ordinal_position
            """
                )
            )

            columns = {row.column_name: (row.data_type, row.is_nullable) for row in result}

            # Expected columns (should match parsed_items table)
            expected_columns = {
                "id": ("uuid", "NO"),
                "tenant_id": ("uuid", "NO"),
                "content_hash": ("character varying", "NO"),
                "doc_type": ("character varying", "NO"),
                "doctype": ("character varying", "NO"),
                "amount": ("numeric", "YES"),
                "invoice_no": ("character varying", "YES"),
                "due_date": ("date", "YES"),
                "quality_status": ("character varying", "NO"),
                "confidence": ("numeric", "NO"),
                "rules": ("jsonb", "NO"),
                "flags": ("jsonb", "NO"),
                "mvr_preview": ("boolean", "NO"),
                "mvr_score": ("numeric", "YES"),
                "payload": ("jsonb", "NO"),
                "created_at": ("timestamp with time zone", "NO"),
                "updated_at": ("timestamp with time zone", "NO"),
            }

            # Check that all expected columns exist
            for col_name, (expected_type, expected_nullable) in expected_columns.items():
                assert col_name in columns, f"Column {col_name} not found in view"
                actual_type, actual_nullable = columns[col_name]
                # Note: PostgreSQL type names might vary slightly
                assert actual_type in [
                    expected_type,
                    expected_type.replace("character varying", "text"),
                ], f"Column {col_name} has type {actual_type}, expected {expected_type}"

    def test_views_are_queryable(self, engine):
        """Test that views can be queried without errors."""
        with engine.begin() as conn:
            # Test v_inbox_by_tenant
            result = conn.execute(text("SELECT COUNT(*) FROM inbox_parsed.v_inbox_by_tenant"))
            count = result.scalar()
            assert isinstance(count, int)

            # Test v_invoices_latest
            result = conn.execute(text("SELECT COUNT(*) FROM inbox_parsed.v_invoices_latest"))
            count = result.scalar()
            assert isinstance(count, int)

    def test_views_data_consistency(self, engine):
        """Test that views return consistent data."""
        with engine.begin() as conn:
            # Get counts from base table
            base_count = conn.execute(
                text("SELECT COUNT(*) FROM inbox_parsed.parsed_items")
            ).scalar()
            invoice_count = conn.execute(
                text("SELECT COUNT(*) FROM inbox_parsed.parsed_items WHERE doctype = 'invoice'")
            ).scalar()

            # Get counts from views
            view_count = conn.execute(
                text("SELECT SUM(total_items) FROM inbox_parsed.v_inbox_by_tenant")
            ).scalar()
            view_invoice_count = conn.execute(
                text("SELECT COUNT(*) FROM inbox_parsed.v_invoices_latest")
            ).scalar()

            # Should be consistent
            assert (
                view_count == base_count
            ), f"View total_items {view_count} != base count {base_count}"
            assert (
                view_invoice_count == invoice_count
            ), f"View invoice count {view_invoice_count} != base invoice count {invoice_count}"
