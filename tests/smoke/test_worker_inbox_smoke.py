import json
import os
import uuid
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from backend.core.config import settings
from agents.inbox_worker.runner import run_once


ARTIFACTS_DIR = Path("artifacts")
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
REPORT_PATH = ARTIFACTS_DIR / "u4-p1-worker-smoke.json"


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


def test_worker_parses_validated_pdf(tmp_path, monkeypatch):
    report = {"tests": []}

    # Prepare storage file
    base = settings.STORAGE_BASE_URI.replace("file://", "")
    Path(base).mkdir(parents=True, exist_ok=True)
    tenant_id = os.environ.get("SMOKE_TENANT", str(uuid.uuid4()))
    # Tenant allowlist for worker path
    monkeypatch.setenv("TENANT_ALLOWLIST", tenant_id)
    content = b"%PDF-1.4\nInvoice No.: INV-12345\nAmount: 123,45\nDue Date: 2025-12-31\n"
    import hashlib
    h = hashlib.sha256(content).hexdigest()
    hh = h[:2]
    dirp = Path(base) / tenant_id / hh
    dirp.mkdir(parents=True, exist_ok=True)
    uri = f"file://{dirp}/{h}.pdf"
    with open(dirp / f"{h}.pdf", "wb") as f:
        f.write(content)

    # Insert inbox and outbox rows
    inbox_id = str(uuid.uuid4())
    _db_exec(
        """
        INSERT INTO inbox_items (id, tenant_id, status, content_hash, uri, source, filename, mime)
        VALUES (:id, :t, 'validated', :ch, :uri, 'api', NULL, 'application/pdf')
        ON CONFLICT (id) DO NOTHING
        """,
        {"id": inbox_id, "t": tenant_id, "ch": h, "uri": uri},
    )
    trace_id = str(uuid.uuid4())
    payload = json.dumps({"inbox_item_id": inbox_id, "content_hash": h, "uri": uri, "source": "api", "filename": "doc.pdf", "mime": "application/pdf"})
    _db_exec(
        """
        INSERT INTO event_outbox (id, tenant_id, event_type, schema_version, idempotency_key, trace_id, payload_json, status, created_at)
        VALUES (:id, :t, 'InboxItemValidated', '1.0', :ik, :tr, :p, 'pending', NOW())
        """,
        {"id": str(uuid.uuid4()), "t": tenant_id, "ik": h, "tr": trace_id, "p": payload},
    )

    # Run worker once
    run_once(batch_size=10)

    # Assertions
    assert _db_count("SELECT COUNT(*) FROM parsed_items WHERE tenant_id=:t AND inbox_item_id=:i", {"t": tenant_id, "i": inbox_id}) == 1
    assert _db_count("SELECT COUNT(*) FROM event_outbox WHERE tenant_id=:t AND event_type='InboxItemParsed'", {"t": tenant_id}) >= 1
    report["tests"].append({"name": "T-W1 Happy", "status": "passed"})

    # Unsupported MIME path
    inbox2 = str(uuid.uuid4())
    _db_exec(
        """
        INSERT INTO inbox_items (id, tenant_id, status, content_hash, uri, source, filename, mime)
        VALUES (:id, :t, 'validated', :ch, :uri, 'api', NULL, 'application/octet-stream')
        ON CONFLICT (id) DO NOTHING
        """,
        {"id": inbox2, "t": tenant_id, "ch": h, "uri": uri},
    )
    payload2 = json.dumps({"inbox_item_id": inbox2, "content_hash": h, "uri": uri, "source": "api", "filename": "doc.bin", "mime": "application/octet-stream"})
    _db_exec(
        """
        INSERT INTO event_outbox (id, tenant_id, event_type, schema_version, idempotency_key, trace_id, payload_json, status, created_at)
        VALUES (:id, :t, 'InboxItemValidated', '1.0', :ik, :tr, :p, 'pending', NOW())
        """,
        {"id": str(uuid.uuid4()), "t": tenant_id, "ik": inbox2, "tr": trace_id, "p": payload2},
    )
    run_once(batch_size=10)
    # Should create ParseFailed event and mark inbox error
    assert _db_count("SELECT COUNT(*) FROM event_outbox WHERE tenant_id=:t AND event_type='InboxItemParseFailed'", {"t": tenant_id}) >= 1
    report["tests"].append({"name": "T-W2 Unsupported MIME", "status": "passed"})

    # T-W3 Idempotency: same idempotency_key second event is skipped (no-op)
    inbox3 = inbox_id  # refer to first parsed item
    ev2_id = str(uuid.uuid4())
    _db_exec(
        """
        INSERT INTO event_outbox (id, tenant_id, event_type, schema_version, idempotency_key, trace_id, payload_json, status, created_at)
        VALUES (:id, :t, 'InboxItemValidated', '1.0', :ik, :tr, :p, 'pending', NOW())
        """,
        {"id": ev2_id, "t": tenant_id, "ik": h, "tr": trace_id, "p": payload},
    )
    run_once(batch_size=10)
    # Ensure no new parsed_items and the second event marked sent
    assert _db_count("SELECT COUNT(*) FROM parsed_items WHERE tenant_id=:t AND inbox_item_id=:i", {"t": tenant_id, "i": inbox_id}) == 1
    # processed_events should have an entry for (tenant_id, event_type, idempotency_key)
    assert _db_count(
        "SELECT COUNT(*) FROM processed_events WHERE tenant_id=:t AND event_type='InboxItemValidated' AND idempotency_key=:k",
        {"t": tenant_id, "k": h},
    ) == 1
    # second outbox row becomes sent
    assert _db_count("SELECT COUNT(*) FROM event_outbox WHERE id=:id AND status='sent'", {"id": ev2_id}) == 1
    report["tests"].append({"name": "T-W3 Idempotency", "status": "passed"})

    # T-W4 Chunking path: force low threshold
    old_thr = settings.PARSER_CHUNK_THRESHOLD_BYTES
    try:
        settings.PARSER_CHUNK_THRESHOLD_BYTES = 32
        inbox4 = str(uuid.uuid4())
        _db_exec(
            """
            INSERT INTO inbox_items (id, tenant_id, status, content_hash, uri, source, filename, mime)
            VALUES (:id, :t, 'validated', :ch, :uri, 'api', NULL, 'application/pdf')
            ON CONFLICT (id) DO NOTHING
            """,
            {"id": inbox4, "t": tenant_id, "ch": h, "uri": uri},
        )
        payload4 = json.dumps({"inbox_item_id": inbox4, "content_hash": h, "uri": uri, "source": "api", "filename": "doc.pdf", "mime": "application/pdf"})
        _db_exec(
            """
            INSERT INTO event_outbox (id, tenant_id, event_type, schema_version, idempotency_key, trace_id, payload_json, status, created_at)
            VALUES (:id, :t, 'InboxItemValidated', '1.0', :ik, :tr, :p, 'pending', NOW())
            """,
            {"id": str(uuid.uuid4()), "t": tenant_id, "ik": inbox4, "tr": trace_id, "p": payload4},
        )
        run_once(batch_size=10)
        # Expect chunks > 0
        assert _db_count("SELECT COUNT(*) FROM chunks WHERE tenant_id=:t AND inbox_item_id=:i", {"t": tenant_id, "i": inbox4}) > 0
        report["tests"].append({"name": "T-W4 Chunking", "status": "passed"})
    finally:
        settings.PARSER_CHUNK_THRESHOLD_BYTES = old_thr

    # T-W5 Retry → DLQ for sb:// URI (io_error)
    old_steps = settings.PARSER_BACKOFF_STEPS
    old_max = settings.PARSER_RETRY_MAX
    try:
        settings.PARSER_BACKOFF_STEPS = "0,0,0"
        settings.PARSER_RETRY_MAX = 2
        inbox5 = str(uuid.uuid4())
        sb_uri = f"sb://bucket/{tenant_id}/x/{h}.pdf"
        _db_exec(
            """
            INSERT INTO inbox_items (id, tenant_id, status, content_hash, uri, source, filename, mime)
            VALUES (:id, :t, 'validated', :ch, :uri, 'api', NULL, 'application/pdf')
            ON CONFLICT (id) DO NOTHING
            """,
            {"id": inbox5, "t": tenant_id, "ch": h, "uri": sb_uri},
        )
        payload5 = json.dumps({"inbox_item_id": inbox5, "content_hash": h, "uri": sb_uri, "source": "api", "filename": "doc.pdf", "mime": "application/pdf"})
        ev5 = str(uuid.uuid4())
        _db_exec(
            """
            INSERT INTO event_outbox (id, tenant_id, event_type, schema_version, idempotency_key, trace_id, payload_json, status, created_at, attempt_count)
            VALUES (:id, :t, 'InboxItemValidated', '1.0', :ik, :tr, :p, 'pending', NOW(), 0)
            """,
            {"id": ev5, "t": tenant_id, "ik": inbox5, "tr": trace_id, "p": payload5},
        )
        # Run multiple times to exhaust retries
        run_once(batch_size=10)
        run_once(batch_size=10)
        # After retries exhausted, expect dead_letters and source event failed
        assert _db_count("SELECT COUNT(*) FROM dead_letters WHERE tenant_id=:t AND event_type='InboxItemValidated'", {"t": tenant_id}) >= 1
        assert _db_count("SELECT COUNT(*) FROM event_outbox WHERE id=:id AND status='failed'", {"id": ev5}) == 1
        # No parsed event for this inbox
        assert _db_count("SELECT COUNT(*) FROM event_outbox WHERE tenant_id=:t AND event_type='InboxItemParsed' AND payload_json::json->>'inbox_item_id'=:i", {"t": tenant_id, "i": inbox5}) == 0
        report["tests"].append({"name": "T-W5 Retry→DLQ", "status": "passed"})
    finally:
        settings.PARSER_BACKOFF_STEPS = old_steps
        settings.PARSER_RETRY_MAX = old_max

    REPORT_PATH.write_text(json.dumps(report, indent=2))

    REPORT_PATH.write_text(json.dumps(report, indent=2))
