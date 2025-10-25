"""Tests for idempotent import functionality — auto-generated via PDD."""

import pytest
import os
import json
from sqlalchemy import create_engine, text
from backend.apps.inbox.importer.worker import process_artifact_file


class TestIdempotentImport:
    """Test idempotent import behavior."""
    
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
    
    def test_idempotent_import_same_artifact(self, engine, test_tenant_id, test_artifact_path):
        """Test that importing the same artifact multiple times results in only one record."""
        # Clean up any existing data
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM inbox_parsed.parsed_items WHERE tenant_id = :tenant_id"), 
                        {"tenant_id": test_tenant_id})
            conn.execute(text("DELETE FROM inbox_parsed.parsed_item_chunks WHERE parsed_item_id IN "
                            "(SELECT id FROM inbox_parsed.parsed_items WHERE tenant_id = :tenant_id)"), 
                        {"tenant_id": test_tenant_id})
        
        # Import the same artifact 3 times
        for i in range(3):
            result = process_artifact_file(
                tenant_id=test_tenant_id,
                artifact_path=test_artifact_path,
                engine=engine
            )
            assert result is not None
            assert result.parsed_item_id is not None
        
        # Check that only one parsed_item exists
        with engine.begin() as conn:
            parsed_items_count = conn.execute(
                text("SELECT COUNT(*) FROM inbox_parsed.parsed_items WHERE tenant_id = :tenant_id"),
                {"tenant_id": test_tenant_id}
            ).scalar()
            
            parsed_item_chunks_count = conn.execute(
                text("SELECT COUNT(*) FROM inbox_parsed.parsed_item_chunks WHERE parsed_item_id IN "
                    "(SELECT id FROM inbox_parsed.parsed_items WHERE tenant_id = :tenant_id)"),
                {"tenant_id": test_tenant_id}
            ).scalar()
        
        # Should have exactly 1 parsed_item (idempotent)
        assert parsed_items_count == 1, f"Expected 1 parsed_item, got {parsed_items_count}"
        
        # Should have expected number of chunks (not duplicated)
        assert parsed_item_chunks_count > 0, f"Expected > 0 chunks, got {parsed_item_chunks_count}"
    
    def test_deterministic_ids(self, engine, test_tenant_id, test_artifact_path):
        """Test that deterministic IDs are generated consistently."""
        # Clean up any existing data
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM inbox_parsed.parsed_items WHERE tenant_id = :tenant_id"), 
                        {"tenant_id": test_tenant_id})
        
        # Import the artifact
        result1 = process_artifact_file(
            tenant_id=test_tenant_id,
            artifact_path=test_artifact_path,
            engine=engine
        )
        
        # Get the ID from database
        with engine.begin() as conn:
            db_id = conn.execute(
                text("SELECT id FROM inbox_parsed.parsed_items WHERE tenant_id = :tenant_id"),
                {"tenant_id": test_tenant_id}
            ).scalar()
        
        # Import again (should be idempotent)
        result2 = process_artifact_file(
            tenant_id=test_tenant_id,
            artifact_path=test_artifact_path,
            engine=engine
        )
        
        # IDs should be the same (deterministic)
        assert result1.parsed_item_id == result2.parsed_item_id
        assert result1.parsed_item_id == db_id
    
    def test_upsert_behavior(self, engine, test_tenant_id, test_artifact_path):
        """Test that upsert behavior works correctly."""
        # Clean up any existing data
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM inbox_parsed.parsed_items WHERE tenant_id = :tenant_id"), 
                        {"tenant_id": test_tenant_id})
        
        # First import (should be INSERT)
        result1 = process_artifact_file(
            tenant_id=test_tenant_id,
            artifact_path=test_artifact_path,
            engine=engine
        )
        assert result1.action == "insert"
        
        # Second import (should be UPDATE)
        result2 = process_artifact_file(
            tenant_id=test_tenant_id,
            artifact_path=test_artifact_path,
            engine=engine
        )
        assert result2.action == "update"
        
        # Same item ID
        assert result1.parsed_item_id == result2.parsed_item_id
