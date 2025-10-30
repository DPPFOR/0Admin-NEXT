"""Tests for Brevo webhook Basic Auth authentication."""

import base64
import json

import pytest
from fastapi.testclient import TestClient

from tools.operate.brevo_webhook import app, verify_basic_auth


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def payload():
    """Test payload."""
    return {"event": "delivered", "date": "2025-01-15T10:30:00Z", "message-id": "test-123"}


def test_verify_basic_auth_valid():
    """Test Basic Auth with valid credentials."""
    user_pass = "testuser:testpass"
    encoded = base64.b64encode(user_pass.encode()).decode()
    auth_header = f"Basic {encoded}"

    assert verify_basic_auth(auth_header, "testuser", "testpass") is True


def test_verify_basic_auth_invalid_user():
    """Test Basic Auth with invalid username."""
    user_pass = "wronguser:testpass"
    encoded = base64.b64encode(user_pass.encode()).decode()
    auth_header = f"Basic {encoded}"

    assert verify_basic_auth(auth_header, "testuser", "testpass") is False


def test_verify_basic_auth_invalid_password():
    """Test Basic Auth with invalid password."""
    user_pass = "testuser:wrongpass"
    encoded = base64.b64encode(user_pass.encode()).decode()
    auth_header = f"Basic {encoded}"

    assert verify_basic_auth(auth_header, "testuser", "testpass") is False


def test_verify_basic_auth_missing_header():
    """Test Basic Auth with missing Authorization header."""
    assert verify_basic_auth(None, "testuser", "testpass") is False


def test_verify_basic_auth_not_basic():
    """Test Basic Auth with non-Basic Authorization header."""
    assert verify_basic_auth("Bearer token", "testuser", "testpass") is False


def test_verify_basic_auth_invalid_base64():
    """Test Basic Auth with invalid Base64 encoding."""
    assert verify_basic_auth("Basic invalid-base64!", "testuser", "testpass") is False


def test_verify_basic_auth_no_credentials():
    """Test Basic Auth with no expected credentials configured."""
    user_pass = "testuser:testpass"
    encoded = base64.b64encode(user_pass.encode()).decode()
    auth_header = f"Basic {encoded}"

    assert verify_basic_auth(auth_header, None, None) is False


def test_webhook_basic_mode_valid(client, payload, monkeypatch):
    """Test webhook endpoint with Basic Auth mode and valid credentials."""
    monkeypatch.setenv("BREVO_WEBHOOK_AUTH_MODE", "basic")
    monkeypatch.setenv("BREVO_WEBHOOK_BASIC_USER", "testuser")
    monkeypatch.setenv("BREVO_WEBHOOK_BASIC_PASS", "testpass")
    monkeypatch.setenv("TENANT_DEFAULT", "00000000-0000-0000-0000-000000000001")

    # Reload module to pick up env changes
    import importlib

    import tools.operate.brevo_webhook

    importlib.reload(tools.operate.brevo_webhook)

    body = json.dumps(payload).encode("utf-8")
    user_pass = "testuser:testpass"
    encoded = base64.b64encode(user_pass.encode()).decode()
    auth_header = f"Basic {encoded}"

    response = client.post(
        "/operate/brevo/webhook",
        content=body,
        headers={
            "Authorization": auth_header,
            "X-Tenant-ID": "00000000-0000-0000-0000-000000000001",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_webhook_basic_mode_invalid(client, payload, monkeypatch):
    """Test webhook endpoint with Basic Auth mode and invalid credentials."""
    monkeypatch.setenv("BREVO_WEBHOOK_AUTH_MODE", "basic")
    monkeypatch.setenv("BREVO_WEBHOOK_BASIC_USER", "testuser")
    monkeypatch.setenv("BREVO_WEBHOOK_BASIC_PASS", "testpass")

    # Reload module
    import importlib

    import tools.operate.brevo_webhook

    importlib.reload(tools.operate.brevo_webhook)

    body = json.dumps(payload).encode("utf-8")
    user_pass = "wronguser:wrongpass"
    encoded = base64.b64encode(user_pass.encode()).decode()
    auth_header = f"Basic {encoded}"

    response = client.post(
        "/operate/brevo/webhook",
        content=body,
        headers={"Authorization": auth_header},
    )

    assert response.status_code == 401
    data = response.json()
    assert data["status"] == "error"


def test_webhook_basic_mode_missing(client, payload, monkeypatch):
    """Test webhook endpoint with Basic Auth mode but no Authorization header."""
    monkeypatch.setenv("BREVO_WEBHOOK_AUTH_MODE", "basic")
    monkeypatch.setenv("BREVO_WEBHOOK_BASIC_USER", "testuser")
    monkeypatch.setenv("BREVO_WEBHOOK_BASIC_PASS", "testpass")

    # Reload module
    import importlib

    import tools.operate.brevo_webhook

    importlib.reload(tools.operate.brevo_webhook)

    body = json.dumps(payload).encode("utf-8")

    response = client.post("/operate/brevo/webhook", content=body)

    assert response.status_code == 401
    data = response.json()
    assert data["status"] == "error"

