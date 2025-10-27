import json
import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from backend.core.config import settings
from backend.apps.inbox.mail import ingest as mail_ingest
from backend.apps.inbox.mail.ingest import Attachment, MailMessage
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from alembic.runtime.migration import MigrationContext


RUN_DB_TESTS = os.getenv("RUN_DB_TESTS") == "1"
if not RUN_DB_TESTS:
    pytest.skip("requires RUN_DB_TESTS=1 and DATABASE_URL/INBOX_DB_URL", allow_module_level=True)


ARTIFACTS_DIR = Path("artifacts")
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
REPORT_PATH = ARTIFACTS_DIR / "u5-m-mail-ingest-smoke.json"


def _db_engine():
    return create_engine(os.environ.get("DATABASE_URL", settings.database_url), future=True)


def _db_count(sql: str, params: dict) -> int:
    eng = _db_engine()
    with eng.begin() as conn:
        return conn.execute(text(sql), params).scalar() or 0


def _assert_alembic_head(report: dict) -> None:
    cfg = AlembicConfig("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", os.environ.get("DATABASE_URL", settings.database_url))
    script = ScriptDirectory.from_config(cfg)
    heads = set(script.get_heads())
    eng = _db_engine()
    with eng.connect() as conn:
        context = MigrationContext.configure(conn)
        current = context.get_current_revision()
    ok = current in heads
    report.setdefault("prechecks", []).append({"name": "precheck_alembic_head", "current": current, "heads": list(heads), "status": "passed" if ok else "failed"})
    if not ok:
        REPORT_PATH.write_text(json.dumps(report, indent=2))
        pytest.fail(f"Alembic not at head: current={current}, heads={','.join(heads)}")


def test_mail_ingest_smoke(monkeypatch, caplog):
    report = {"tests": []}
    _assert_alembic_head(report)

    tenant_id = os.environ.get("SMOKE_TENANT", str(uuid.uuid4()))
    base = settings.STORAGE_BASE_URI.replace("file://", "")
    Path(base).mkdir(parents=True, exist_ok=True)

    # Prepare attachments
    pdf = b"%PDF-1.4\nHello"
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 10
    exe = os.urandom(64)
    big_pdf = b"%PDF-1.4\n" + (b"0" * (2 * 1024 * 1024))

    def make_msg(msg_id: str, atts):
        return MailMessage(id=msg_id, mailbox="INBOX", received_at=None, attachments=atts)

    # Monkeypatch provider messages
    def provider_messages(provider, mailbox, limit):
        return [
            make_msg("m1", [Attachment(content=pdf, filename="a.pdf", size=len(pdf)), Attachment(content=png, filename="b.png", size=len(png))]),
        ]

    monkeypatch.setattr(mail_ingest, "fetch_messages", provider_messages)
    monkeypatch.setenv("MAIL_PROVIDER", "imap")

    caplog.set_level("INFO")

    # Ensure AUTO-DI is off for baseline
    monkeypatch.setenv("MAIL_CONNECTOR_AUTO", "0")

    # T-M1 IMAP Happy
    res1 = mail_ingest.process_mailbox(tenant_id, "INBOX")
    assert res1["processed"] == 2 and res1["duplicates"] == 0
    c_inbox = _db_count("SELECT COUNT(*) FROM inbox_items WHERE tenant_id=:t", {"t": tenant_id})
    assert c_inbox >= 2
    c_events = _db_count("SELECT COUNT(*) FROM event_outbox WHERE tenant_id=:t AND event_type='InboxItemValidated'", {"t": tenant_id})
    assert c_events >= 2
    report["tests"].append({"name": "T-M1 IMAP Happy", "status": "passed"})

    # T-M2 Graph Happy (same mock, different provider)
    monkeypatch.setenv("MAIL_PROVIDER", "graph")
    res2 = mail_ingest.process_mailbox(tenant_id, "INBOX")
    # duplicates expected now (same attachments)
    assert res2["duplicates"] >= 2
    report["tests"].append({"name": "T-M2 Graph Happy", "status": "passed"})

    # T-M3 Unsupported MIME
    def provider_bad(provider, mailbox, limit):
        return [make_msg("m2", [Attachment(content=exe, filename="evil.exe", size=len(exe))])]

    monkeypatch.setattr(mail_ingest, "fetch_messages", provider_bad)
    res3 = mail_ingest.process_mailbox(tenant_id, "INBOX")
    # processed remains unchanged, failures increased implicitly; check events unchanged
    c_events2 = _db_count("SELECT COUNT(*) FROM event_outbox WHERE tenant_id=:t AND event_type='InboxItemValidated'", {"t": tenant_id})
    assert c_events2 == c_events
    report["tests"].append({"name": "T-M3 Unsupported MIME", "status": "passed"})

    # T-M4 Size Limit
    old = settings.MAX_UPLOAD_MB
    try:
        settings.MAX_UPLOAD_MB = 1
        monkeypatch.setattr(mail_ingest, "fetch_messages", lambda p, m, l: [make_msg("m3", [Attachment(content=big_pdf, filename="big.pdf", size=len(big_pdf))])])
        res4 = mail_ingest.process_mailbox(tenant_id, "INBOX")
        c_events3 = _db_count("SELECT COUNT(*) FROM event_outbox WHERE tenant_id=:t AND event_type='InboxItemValidated'", {"t": tenant_id})
        assert c_events3 == c_events
        report["tests"].append({"name": "T-M4 Size Limit", "status": "passed"})
    finally:
        settings.MAX_UPLOAD_MB = old

    # T-M5 Idempotency duplicate run
    monkeypatch.setattr(mail_ingest, "fetch_messages", provider_messages)
    res5 = mail_ingest.process_mailbox(tenant_id, "INBOX")
    assert res5["duplicates"] >= 2
    # No PII in logs: look for email-like patterns (naive)
    log_text = "\n".join(r.getMessage() for r in caplog.records)
    assert "@" not in log_text and "Subject:" not in log_text
    report["tests"].append({"name": "T-M5 Idempotency + PII", "status": "passed"})

    # AUTO-DI on: prefer ImapConnectorImpl but mock fetch to avoid egress
    from backend.apps.inbox.mail import connectors as conn_mod

    class NoNetImap(conn_mod.ImapConnectorImpl):
        def fetch_messages(self, mailbox, since, limit):  # type: ignore[override]
            return [
                mail_ingest.MailMessage(id="auto1", mailbox=mailbox, received_at=None, attachments=[mail_ingest.Attachment(content=pdf, filename="x.pdf", size=len(pdf))])
            ]

    monkeypatch.setenv("MAIL_CONNECTOR_AUTO", "1")
    monkeypatch.setenv("MAIL_PROVIDER", "imap")
    monkeypatch.setenv("IMAP_HOST", "imap.example.com")
    monkeypatch.setenv("IMAP_USERNAME", "user")
    monkeypatch.setenv("IMAP_PASSWORD", "pass")
    monkeypatch.setattr(conn_mod, "ImapConnectorImpl", NoNetImap)
    res_auto = mail_ingest.process_mailbox(tenant_id, "INBOX")
    assert res_auto["processed"] >= 1

    REPORT_PATH.write_text(json.dumps(report, indent=2))
