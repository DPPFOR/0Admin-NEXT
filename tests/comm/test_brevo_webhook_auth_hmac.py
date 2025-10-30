"""Regression tests for Brevo webhook HMAC authentication."""

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from tools.operate.brevo_webhook import app, verify_hmac_signature


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def secret():
    """Test webhook secret."""
    return "test-secret-key-12345"


@pytest.fixture
def payload():
    """Test payload."""
    return {"event": "delivered", "date": "2025-01-15T10:30:00Z", "message-id": "test-123"}


def test_verify_hmac_signature_valid(secret, payload):
    """Test HMAC signature verification with valid signature."""
    body = json.dumps(payload).encode("utf-8")
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    signature_header = f"sha256={signature}"

    assert verify_hmac_signature(body, signature_header, secret) is True


def test_verify_hmac_signature_invalid(secret, payload):
    """Test HMAC signature verification with invalid signature."""
    body = json.dumps(payload).encode("utf-8")
    signature_header = "sha256=invalid-signature"

    assert verify_hmac_signature(body, signature_header, secret) is False


def test_verify_hmac_signature_no_secret(payload):
    """Test HMAC signature verification without secret."""
    body = json.dumps(payload).encode("utf-8")
    signature_header = "sha256=test"

    assert verify_hmac_signature(body, signature_header, None) is False


def test_verify_hmac_signature_no_header(secret, payload):
    """Test HMAC signature verification without signature header."""
    body = json.dumps(payload).encode("utf-8")

    assert verify_hmac_signature(body, None, secret) is False


def test_verify_hmac_signature_wrong_format(secret, payload):
    """Test HMAC signature verification with wrong header format."""
    body = json.dumps(payload).encode("utf-8")
    signature_header = "invalid-format"

    assert verify_hmac_signature(body, signature_header, secret) is False


def test_webhook_hmac_mode_valid(client, secret, payload, monkeypatch):
    """Test webhook endpoint with HMAC mode and valid signature."""
    monkeypatch.setenv("BREVO_WEBHOOK_AUTH_MODE", "hmac")
    monkeypatch.setenv("BREVO_WEBHOOK_SECRET", secret)
    monkeypatch.setenv("TENANT_DEFAULT", "00000000-0000-0000-0000-000000000001")

    # Reload module to pick up env changes
    import importlib

    import tools.operate.brevo_webhook

    importlib.reload(tools.operate.brevo_webhook)

    body = json.dumps(payload).encode("utf-8")
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    signature_header = f"sha256={signature}"

    response = client.post(
        "/operate/brevo/webhook",
        content=body,
        headers={
            "X-Brevo-Signature": signature_header,
            "X-Tenant-ID": "00000000-0000-0000-0000-000000000001",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_webhook_hmac_mode_invalid(client, secret, payload, monkeypatch):
    """Test webhook endpoint with HMAC mode and invalid signature."""
    monkeypatch.setenv("BREVO_WEBHOOK_AUTH_MODE", "hmac")
    monkeypatch.setenv("BREVO_WEBHOOK_SECRET", secret)

    # Reload module
    import importlib

    import tools.operate.brevo_webhook

    importlib.reload(tools.operate.brevo_webhook)

    body = json.dumps(payload).encode("utf-8")
    signature_header = "sha256=invalid-signature"

    response = client.post(
        "/operate/brevo/webhook",
        content=body,
        headers={"X-Brevo-Signature": signature_header},
    )

    assert response.status_code == 401
    data = response.json()
    assert data["status"] == "error"


def test_webhook_hmac_mode_missing(client, secret, payload, monkeypatch):
    """Test webhook endpoint with HMAC mode but no signature header."""
    monkeypatch.setenv("BREVO_WEBHOOK_AUTH_MODE", "hmac")
    monkeypatch.setenv("BREVO_WEBHOOK_SECRET", secret)

    # Reload module
    import importlib

    import tools.operate.brevo_webhook

    importlib.reload(tools.operate.brevo_webhook)

    body = json.dumps(payload).encode("utf-8")

    response = client.post("/operate/brevo/webhook", content=body)

    assert response.status_code == 401
    data = response.json()
    assert data["status"] == "error"

