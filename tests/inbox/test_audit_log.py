"""Tests for audit log functionality — auto-generated via PDD."""

import os

import pytest
from sqlalchemy import create_engine, text

from backend.apps.inbox.importer.worker import process_artifact_file


class TestAuditLog:
    """Test audit log functionality."""

    @pytest.fixture
    def engine(self):
        """Database engine for tests."""
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            pytest.skip("DATABASE_URL not set")
        return create_engine(database_url, future=True)

    @pytest.fixture
    def test_tenant_id(self):
        """Test tenant ID."""
        return "00000000-0000-0000-0000-000000000001"

    @pytest.fixture
    def test_artifact_path(self):
        """Path to test artifact."""
        return "artifacts/inbox_local/samples/invoice_good.json"

    def test_audit_log_created_on_import(self, engine, test_tenant_id, test_artifact_path):
        """Test that audit log entry is created on import."""
        # Clean up any existing data
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM ops.audit_log WHERE tenant_id = :tenant_id"),
                {"tenant_id": test_tenant_id},
            )
            conn.execute(
                text("DELETE FROM inbox_parsed.parsed_items WHERE tenant_id = :tenant_id"),
                {"tenant_id": test_tenant_id},
            )

        # Import artifact
        result = process_artifact_file(
            tenant_id=test_tenant_id, artifact_path=test_artifact_path, engine=engine
        )

        # Check that audit log entry was created
        with engine.begin() as conn:
            audit_count = conn.execute(
                text(
                    "SELECT COUNT(*) FROM ops.audit_log WHERE tenant_id = :tenant_id AND op = 'IMPORT_UPSERT'"
                ),
                {"tenant_id": test_tenant_id},
            ).scalar()

            assert audit_count == 1, f"Expected 1 audit log entry, got {audit_count}"

            # Check audit log entry details
            audit_entry = conn.execute(
                text(
                    """
                    SELECT id, tenant_id, item_id, source, op, meta
                    FROM ops.audit_log 
                    WHERE tenant_id = :tenant_id AND op = 'IMPORT_UPSERT'
                """
                ),
                {"tenant_id": test_tenant_id},
            ).fetchone()

            assert audit_entry is not None
            assert audit_entry.tenant_id == test_tenant_id
            assert audit_entry.item_id == result.parsed_item_id
            assert audit_entry.source == "importer"
            assert audit_entry.op == "IMPORT_UPSERT"
            assert audit_entry.meta is not None
            assert "action" in audit_entry.meta
            assert "content_hash" in audit_entry.meta

    def test_audit_log_idempotent_import(self, engine, test_tenant_id, test_artifact_path):
        """Test that audit log entries are created for both insert and update operations."""
        # Clean up any existing data
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM ops.audit_log WHERE tenant_id = :tenant_id"),
                {"tenant_id": test_tenant_id},
            )
            conn.execute(
                text("DELETE FROM inbox_parsed.parsed_items WHERE tenant_id = :tenant_id"),
                {"tenant_id": test_tenant_id},
            )

        # First import (should be INSERT)
        result1 = process_artifact_file(
            tenant_id=test_tenant_id, artifact_path=test_artifact_path, engine=engine
        )

        # Second import (should be UPDATE)
        result2 = process_artifact_file(
            tenant_id=test_tenant_id, artifact_path=test_artifact_path, engine=engine
        )

        # Check audit log entries
        with engine.begin() as conn:
            audit_entries = conn.execute(
                text(
                    """
                    SELECT id, tenant_id, item_id, source, op, meta
                    FROM ops.audit_log 
                    WHERE tenant_id = :tenant_id AND op = 'IMPORT_UPSERT'
                    ORDER BY ts
                """
                ),
                {"tenant_id": test_tenant_id},
            ).fetchall()

            assert (
                len(audit_entries) == 2
            ), f"Expected 2 audit log entries, got {len(audit_entries)}"

            # Check first entry (INSERT)
            first_entry = audit_entries[0]
            assert first_entry.meta["action"] == "insert"

            # Check second entry (UPDATE)
            second_entry = audit_entries[1]
            assert second_entry.meta["action"] == "update"

            # Both should have same item_id
            assert first_entry.item_id == second_entry.item_id
            assert first_entry.item_id == result1.parsed_item_id

    def test_audit_log_schema(self, engine):
        """Test that audit_log table has expected schema."""
        with engine.begin() as conn:
            # Get table structure
            result = conn.execute(
                text(
                    """
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns 
                WHERE table_schema = 'ops' 
                AND table_name = 'audit_log'
                ORDER BY ordinal_position
            """
                )
            )

            columns = {row.column_name: (row.data_type, row.is_nullable) for row in result}

            # Expected columns
            expected_columns = {
                "id": ("uuid", "NO"),
                "ts": ("timestamp with time zone", "NO"),
                "trace_id": ("character varying", "YES"),
                "actor": ("character varying", "YES"),
                "tenant_id": ("uuid", "YES"),
                "item_id": ("uuid", "YES"),
                "source": ("character varying", "YES"),
                "op": ("character varying", "YES"),
                "meta": ("jsonb", "YES"),
            }

            # Check that all expected columns exist
            for col_name, (expected_type, expected_nullable) in expected_columns.items():
                assert col_name in columns, f"Column {col_name} not found in audit_log table"
                actual_type, actual_nullable = columns[col_name]
                assert (
                    actual_type == expected_type
                ), f"Column {col_name} has type {actual_type}, expected {expected_type}"
                assert (
                    actual_nullable == expected_nullable
                ), f"Column {col_name} nullable is {actual_nullable}, expected {expected_nullable}"
