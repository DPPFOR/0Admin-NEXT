import json
import os
import uuid

import pytest
from sqlalchemy import create_engine, text

from agents.outbox_publisher import runner as pub_runner
from agents.outbox_publisher import transports as pub_transports
from backend.core.config import settings

ARTIFACTS_DIR = "artifacts"

RUN_DB_TESTS = os.getenv("RUN_DB_TESTS") == "1"
pytestmark = pytest.mark.skipif(
    not RUN_DB_TESTS,
    reason="requires RUN_DB_TESTS=1 and DATABASE_URL/OUTBOX_DB_URL",
)

if not RUN_DB_TESTS:
    pytest.skip("requires RUN_DB_TESTS=1 and DATABASE_URL/OUTBOX_DB_URL", allow_module_level=True)


def _db_engine():
    return create_engine(os.environ.get("DATABASE_URL", settings.database_url), future=True)


def _db_exec(sql: str, params: dict = None):
    eng = _db_engine()
    with eng.begin() as conn:
        conn.execute(text(sql), params or {})


def _db_count(sql: str, params: dict) -> int:
    eng = _db_engine()
    with eng.begin() as conn:
        return conn.execute(text(sql), params).scalar() or 0


def seed_outbox(tenant_id: str, n: int) -> list[str]:
    ids = []
    for i in range(n):
        oid = str(uuid.uuid4())
        _db_exec(
            """
            INSERT INTO event_outbox (id, tenant_id, event_type, schema_version, idempotency_key, trace_id, payload_json, status, attempt_count, created_at)
            VALUES (:id, :t, 'InboxItemParsed', '1.0', :ik, :tr, :p, 'pending', 0, NOW())
            """,
            {
                "id": oid,
                "t": tenant_id,
                "ik": f"idem-{i}",
                "tr": str(uuid.uuid4()),
                "p": json.dumps({"ok": True}),
            },
        )
        ids.append(oid)
    return ids


def test_publisher_stdout(monkeypatch):
    tenant = os.environ.get("SMOKE_TENANT", str(uuid.uuid4()))
    # Tenant allowlist for publisher path
    monkeypatch.setenv("TENANT_ALLOWLIST", tenant)
    seed_outbox(tenant, 3)
    monkeypatch.setenv("PUBLISH_TRANSPORT", "stdout")
    processed = pub_runner.run_once(batch_size=10)
    assert processed >= 3
    # Sent count in DB
    assert (
        _db_count(
            "SELECT COUNT(*) FROM event_outbox WHERE tenant_id=:t AND status='sent'", {"t": tenant}
        )
        >= 3
    )


def test_publisher_webhook_success(monkeypatch):
    tenant = str(uuid.uuid4())
    monkeypatch.setenv("TENANT_ALLOWLIST", tenant)
    seed_outbox(tenant, 2)

    class FakeWebhook(pub_transports.WebhookTransport):
        def __init__(self):
            # Set https URL to pass scheme check
            self.url = "https://example.com/hook"
            self.success_codes = {200}
            self.headers = {}
            self.client = None

        def publish(self, tenant_id, event_type, payload_json, trace_id=None):
            return pub_transports.PublishResult(ok=True, status_code=200)

    monkeypatch.setenv("PUBLISH_TRANSPORT", "webhook")
    monkeypatch.setattr(pub_runner, "get_transport", lambda: FakeWebhook())
    processed = pub_runner.run_once(batch_size=10)
    assert processed >= 2
    assert (
        _db_count(
            "SELECT COUNT(*) FROM event_outbox WHERE tenant_id=:t AND status='sent'", {"t": tenant}
        )
        >= 2
    )


def test_publisher_webhook_retry_and_dlq(monkeypatch):
    tenant = str(uuid.uuid4())
    monkeypatch.setenv("TENANT_ALLOWLIST", tenant)
    seed_outbox(tenant, 1)

    class AlwaysFail(pub_transports.WebhookTransport):
        def __init__(self):
            self.url = "https://example.com/hook"
            self.success_codes = {200}
            self.headers = {}
            self.client = None

        def publish(self, tenant_id, event_type, payload_json, trace_id=None):
            return pub_transports.PublishResult(ok=False, status_code=500, error="http_500")

    monkeypatch.setenv("PUBLISH_TRANSPORT", "webhook")
    monkeypatch.setenv("PUBLISH_RETRY_MAX", "2")
    monkeypatch.setenv("PUBLISH_BACKOFF_STEPS", "0,0,0")
    monkeypatch.setattr(pub_runner, "get_transport", lambda: AlwaysFail())
    # First run: retry scheduled
    pub_runner.run_once(batch_size=10)
    # Second run: exceed max -> DLQ and failed
    pub_runner.run_once(batch_size=10)
    assert _db_count("SELECT COUNT(*) FROM dead_letters WHERE tenant_id=:t", {"t": tenant}) >= 1
    assert (
        _db_count(
            "SELECT COUNT(*) FROM event_outbox WHERE tenant_id=:t AND status='failed'",
            {"t": tenant},
        )
        >= 1
    )


def test_publisher_webhook_unsupported_scheme(monkeypatch):
    tenant = str(uuid.uuid4())
    monkeypatch.setenv("TENANT_ALLOWLIST", tenant)
    seed_outbox(tenant, 1)

    class BadScheme(pub_transports.WebhookTransport):
        def __init__(self):
            self.url = "http://example.com/hook"  # not https
            self.success_codes = {200}
            self.headers = {}
            self.client = None

    monkeypatch.setenv("PUBLISH_TRANSPORT", "webhook")
    monkeypatch.setattr(pub_runner, "get_transport", lambda: BadScheme())
    pub_runner.run_once(batch_size=10)
    # Non-retriable: should be failed + DLQ
    assert _db_count("SELECT COUNT(*) FROM dead_letters WHERE tenant_id=:t", {"t": tenant}) >= 1
    assert (
        _db_count(
            "SELECT COUNT(*) FROM event_outbox WHERE tenant_id=:t AND status='failed'",
            {"t": tenant},
        )
        >= 1
    )


def test_publisher_webhook_domain_allowlist(monkeypatch):
    tenant = str(uuid.uuid4())
    monkeypatch.setenv("TENANT_ALLOWLIST", tenant)
    seed_outbox(tenant, 1)

    # Allowlist positive: events.example.com allowed
    monkeypatch.setenv("PUBLISH_TRANSPORT", "webhook")
    monkeypatch.setenv("WEBHOOK_DOMAIN_ALLOWLIST", "events.example.com")
    # Include forbidden headers in allowlist to verify sanitization
    monkeypatch.setenv("WEBHOOK_HEADERS_ALLOWLIST", "Authorization=secret, Cookie=foo, X-Custom=ok")

    class AllowWebhook(pub_transports.WebhookTransport):
        def __init__(self):
            super().__init__()
            self.url = "https://events.example.com/hook"
            # headers sanitized in super(): must not contain auth/cookie
            assert all(
                k.lower() not in ("authorization", "cookie", "set-cookie")
                for k in self.headers.keys()
            )
            assert "X-Custom" in self.headers or "x-custom" in {
                k.lower() for k in self.headers.keys()
            }
            self.client = None  # avoid real network

        def publish(self, tenant_id, event_type, payload_json, trace_id=None):
            # Should pass host allow check
            from urllib.parse import urlparse

            assert self._host_allowed(urlparse(self.url).hostname)
            return pub_transports.PublishResult(ok=True, status_code=200)

    monkeypatch.setattr(pub_runner, "get_transport", lambda: AllowWebhook())
    processed = pub_runner.run_once(batch_size=10)
    assert processed >= 1
    assert (
        _db_count(
            "SELECT COUNT(*) FROM event_outbox WHERE tenant_id=:t AND status='sent'", {"t": tenant}
        )
        >= 1
    )


def test_publisher_webhook_domain_block(monkeypatch):
    tenant = str(uuid.uuid4())
    monkeypatch.setenv("TENANT_ALLOWLIST", tenant)
    seed_outbox(tenant, 1)

    monkeypatch.setenv("PUBLISH_TRANSPORT", "webhook")
    monkeypatch.setenv("WEBHOOK_DOMAIN_ALLOWLIST", "events.example.com")

    class DenyWebhook(pub_transports.WebhookTransport):
        def __init__(self):
            super().__init__()
            self.url = "https://evil.example.net/hook"
            self.client = None

        def publish(self, tenant_id, event_type, payload_json, trace_id=None):
            from urllib.parse import urlparse

            # Should fail host allow check
            assert not self._host_allowed(urlparse(self.url).hostname)
            return pub_transports.PublishResult(ok=False, status_code=0, error="forbidden_address")

    monkeypatch.setattr(pub_runner, "get_transport", lambda: DenyWebhook())
    pub_runner.run_once(batch_size=10)
    # Forbidden address is non-retriable: DLQ + failed
    assert _db_count("SELECT COUNT(*) FROM dead_letters WHERE tenant_id=:t", {"t": tenant}) >= 1
    assert (
        _db_count(
            "SELECT COUNT(*) FROM event_outbox WHERE tenant_id=:t AND status='failed'",
            {"t": tenant},
        )
        >= 1
    )
