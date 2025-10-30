"""Tests for Brevo webhook token authentication."""

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tools.operate.brevo_webhook import app, verify_token_auth


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def payload():
    """Test payload."""
    return {"event": "delivered", "date": "2025-01-15T10:30:00Z", "message-id": "test-123"}


def test_verify_token_auth_bearer_valid():
    """Test token auth with valid Bearer token."""
    assert verify_token_auth("Bearer test-token", None, "test-token") is True


def test_verify_token_auth_bearer_invalid():
    """Test token auth with invalid Bearer token."""
    assert verify_token_auth("Bearer wrong-token", None, "test-token") is False


def test_verify_token_auth_x_header_valid():
    """Test token auth with valid X-Webhook-Token header."""
    assert verify_token_auth(None, "test-token", "test-token") is True


def test_verify_token_auth_x_header_invalid():
    """Test token auth with invalid X-Webhook-Token header."""
    assert verify_token_auth(None, "wrong-token", "test-token") is False


def test_verify_token_auth_bearer_preferred():
    """Test that Bearer token is preferred over X-Webhook-Token."""
    # Bearer token matches, X-Webhook-Token is wrong - should succeed
    assert verify_token_auth("Bearer test-token", "wrong-token", "test-token") is True


def test_verify_token_auth_no_token():
    """Test token auth with no token provided."""
    assert verify_token_auth(None, None, "test-token") is False


def test_verify_token_auth_no_expected_token():
    """Test token auth with no expected token configured."""
    assert verify_token_auth("Bearer test-token", None, None) is False


def test_webhook_token_mode_bearer_valid(client, payload, monkeypatch):
    """Test webhook endpoint with token mode and valid Bearer token."""
    monkeypatch.setenv("BREVO_WEBHOOK_AUTH_MODE", "token")
    monkeypatch.setenv("BREVO_WEBHOOK_TOKEN", "test-token-123")
    monkeypatch.setenv("TENANT_DEFAULT", "00000000-0000-0000-0000-000000000001")

    # Reload module to pick up env changes
    import importlib

    import tools.operate.brevo_webhook

    importlib.reload(tools.operate.brevo_webhook)

    body = json.dumps(payload).encode("utf-8")

    response = client.post(
        "/operate/brevo/webhook",
        content=body,
        headers={
            "Authorization": "Bearer test-token-123",
            "X-Tenant-ID": "00000000-0000-0000-0000-000000000001",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_webhook_token_mode_x_header_valid(client, payload, monkeypatch):
    """Test webhook endpoint with token mode and valid X-Webhook-Token header."""
    monkeypatch.setenv("BREVO_WEBHOOK_AUTH_MODE", "token")
    monkeypatch.setenv("BREVO_WEBHOOK_TOKEN", "test-token-123")
    monkeypatch.setenv("TENANT_DEFAULT", "00000000-0000-0000-0000-000000000001")

    # Reload module
    import importlib

    import tools.operate.brevo_webhook

    importlib.reload(tools.operate.brevo_webhook)

    body = json.dumps(payload).encode("utf-8")

    response = client.post(
        "/operate/brevo/webhook",
        content=body,
        headers={
            "X-Webhook-Token": "test-token-123",
            "X-Tenant-ID": "00000000-0000-0000-0000-000000000001",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_webhook_token_mode_invalid(client, payload, monkeypatch):
    """Test webhook endpoint with token mode and invalid token."""
    monkeypatch.setenv("BREVO_WEBHOOK_AUTH_MODE", "token")
    monkeypatch.setenv("BREVO_WEBHOOK_TOKEN", "test-token-123")

    # Reload module
    import importlib

    import tools.operate.brevo_webhook

    importlib.reload(tools.operate.brevo_webhook)

    body = json.dumps(payload).encode("utf-8")

    response = client.post(
        "/operate/brevo/webhook",
        content=body,
        headers={"Authorization": "Bearer wrong-token"},
    )

    assert response.status_code == 401
    data = response.json()
    assert data["status"] == "error"


def test_webhook_token_mode_missing(client, payload, monkeypatch):
    """Test webhook endpoint with token mode but no token provided."""
    monkeypatch.setenv("BREVO_WEBHOOK_AUTH_MODE", "token")
    monkeypatch.setenv("BREVO_WEBHOOK_TOKEN", "test-token-123")

    # Reload module
    import importlib

    import tools.operate.brevo_webhook

    importlib.reload(tools.operate.brevo_webhook)

    body = json.dumps(payload).encode("utf-8")

    response = client.post("/operate/brevo/webhook", content=body)

    assert response.status_code == 401
    data = response.json()
    assert data["status"] == "error"

