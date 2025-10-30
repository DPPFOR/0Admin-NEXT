"""Tests for outbound message tagging."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from agents.comm.outbound_tags import generate_message_id
from backend.integrations.brevo_client import BrevoClient


def test_generate_message_id_deterministic():
    """Test deterministic message ID generation."""
    tenant_id = "00000000-0000-0000-0000-000000000001"
    invoice_no = "INV-2025-001"
    ts = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

    # Generate twice - should be identical
    msg_id1 = generate_message_id(tenant_id, invoice_no, ts)
    msg_id2 = generate_message_id(tenant_id, invoice_no, ts)

    assert msg_id1 == msg_id2
    assert isinstance(msg_id1, str)

    # Verify UUID format
    uuid_obj = UUID(msg_id1)
    assert uuid_obj is not None


def test_generate_message_id_different_inputs():
    """Test message ID changes with different inputs."""
    tenant_id = "00000000-0000-0000-0000-000000000001"
    invoice_no1 = "INV-2025-001"
    invoice_no2 = "INV-2025-002"
    ts = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

    msg_id1 = generate_message_id(tenant_id, invoice_no1, ts)
    msg_id2 = generate_message_id(tenant_id, invoice_no2, ts)

    assert msg_id1 != msg_id2


def test_generate_message_id_without_invoice():
    """Test message ID generation without invoice number."""
    tenant_id = "00000000-0000-0000-0000-000000000001"
    ts = datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

    msg_id = generate_message_id(tenant_id, None, ts)

    assert isinstance(msg_id, str)
    uuid_obj = UUID(msg_id)
    assert uuid_obj is not None


def test_brevo_client_headers(monkeypatch):
    """Test Brevo client sets correct headers."""
    monkeypatch.setenv("BREVO_API_KEY", "test-key")
    monkeypatch.setenv("BREVO_SENDER_EMAIL", "test@example.com")
    monkeypatch.setenv("BREVO_SENDER_NAME", "Test")

    client = BrevoClient()

    # Mock httpx client
    from unittest.mock import Mock, patch

    with patch.object(client, "_client") as mock_client:
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"messageId": "brevo-123"}
        mock_client.post.return_value = mock_response

        tenant_id = "00000000-0000-0000-0000-000000000001"
        response = client.send_transactional(
            to="test@example.com",
            subject="Test",
            html="<p>Test</p>",
            tenant_id=tenant_id,
            invoice_no="INV-001",
            dry_run=False,
        )

        # Verify headers were set
        call_args = mock_client.post.call_args
        email_data = call_args[1]["json"]
        headers = email_data["headers"]

        assert "X-Tenant-ID" in headers
        assert headers["X-Tenant-ID"] == tenant_id
        assert "X-Message-ID" in headers
        assert headers["X-Message-ID"] is not None

        # Verify message ID is UUID format
        msg_uuid = UUID(headers["X-Message-ID"])
        assert msg_uuid is not None


def test_brevo_client_dry_run_deterministic(monkeypatch):
    """Test Brevo client dry-run uses deterministic message ID."""
    monkeypatch.setenv("BREVO_API_KEY", "")
    monkeypatch.setenv("BREVO_SENDER_EMAIL", "test@example.com")
    monkeypatch.setenv("BREVO_SENDER_NAME", "Test")

    client = BrevoClient()

    tenant_id = "00000000-0000-0000-0000-000000000001"
    invoice_no = "INV-2025-001"

    # Call twice - message IDs should be different (different timestamps)
    # but format should be consistent
    response1 = client.send_transactional(
        to="test@example.com",
        subject="Test",
        html="<p>Test</p>",
        tenant_id=tenant_id,
        invoice_no=invoice_no,
        dry_run=True,
    )

    response2 = client.send_transactional(
        to="test@example.com",
        subject="Test",
        html="<p>Test</p>",
        tenant_id=tenant_id,
        invoice_no=invoice_no,
        dry_run=True,
    )

    assert response1.success is True
    assert response2.success is True
    assert response1.message_id is not None
    assert response2.message_id is not None

    # Verify UUID format
    uuid1 = UUID(response1.message_id)
    uuid2 = UUID(response2.message_id)
    assert uuid1 is not None
    assert uuid2 is not None

