import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any, Tuple

from sqlalchemy import create_engine, MetaData
from sqlalchemy.exc import IntegrityError

from backend.core.config import settings
from backend.core.observability.logging import logger, set_tenant_id
from backend.core.observability.metrics import (
    increment_counter,
    record_histogram,
)
from backend.apps.inbox.utils import sha256_hex, detect_mime, extension_for_mime
from backend.apps.inbox.storage import put_bytes, StorageError
from backend.apps.inbox.repository import (
    InboxItem,
    get_tables,
    insert_inbox_item,
    get_inbox_item_by_hash,
)
from backend.apps.inbox.mail.connectors import MailConnector
from backend.apps.inbox.mail.connectors import ImapConnectorImpl, GraphConnectorImpl
from backend.core.observability.logging import logger
from backend.mcp.server.observability import get_logger as get_mcp_logger
from backend.apps.inbox.orchestration.run_shadow_analysis import run_shadow_analysis


# Metrics helpers
def _inc_mail_messages(n: int = 1) -> None:
    increment_counter("mail_messages_total", value=float(n))


def _inc_mail_attachments(n: int = 1) -> None:
    increment_counter("mail_attachments_total", value=float(n))


def _inc_mail_failures(n: int = 1) -> None:
    increment_counter("mail_ingest_failures_total", value=float(n))


def _record_mail_latency(ms: float) -> None:
    record_histogram("mail_ingest_duration_ms", ms)


@dataclass
class Attachment:
    content: bytes
    filename: Optional[str]
    size: int


@dataclass
class MailMessage:
    id: str
    mailbox: str
    received_at: Optional[str]
    attachments: List[Attachment]


def fetch_messages(provider: str, mailbox: str, batch_limit: int) -> List[MailMessage]:
    """Fetch messages with attachments from the provider.

    Default implementation returns empty list. Real connectors are out of scope
    for egress-free tests and can be monkeypatched.
    """
    return []


class _EnvConnector(MailConnector):
    """Default connector adapter that delegates to the legacy fetch_messages(provider, ...).

    This preserves backwards compatibility and remains egress-free for tests.
    """

    def __init__(self, provider: str) -> None:
        self.provider = provider

    def fetch_messages(self, mailbox: str, since: datetime, limit: int) -> List[MailMessage]:  # type: ignore[override]
        # since is currently not used in the legacy path; callers may still apply filtering upstream.
        return fetch_messages(self.provider, mailbox, limit)


_auto_di_logged = False


def _auto_connector(provider: str) -> MailConnector:
    """Return a connector instance based on env credentials and AUTO flag.

    - When MAIL_CONNECTOR_AUTO is false, returns the legacy env adapter.
    - When true and required creds for the provider are present, returns the
      concrete connector (ImapConnectorImpl or GraphConnectorImpl).
    - No PII in logs; logs a single banner once when AUTO-DI is enabled.
    """
    global _auto_di_logged
    if not bool(getattr(settings, "MAIL_CONNECTOR_AUTO", False)):
        return _EnvConnector(provider)

    if not _auto_di_logged:
        logger.info("AUTO_DI_ENABLED", extra={"mail_provider": provider})
        _auto_di_logged = True

    if provider == "imap":
        if settings.IMAP_HOST and settings.IMAP_USERNAME and settings.IMAP_PASSWORD:
            return ImapConnectorImpl()
        return _EnvConnector(provider)
    if provider == "graph":
        if settings.GRAPH_TENANT_ID and settings.GRAPH_CLIENT_ID and settings.GRAPH_CLIENT_SECRET and settings.GRAPH_USER_ID:
            return GraphConnectorImpl()
        return _EnvConnector(provider)
    return _EnvConnector(provider)


def _process_attachment(
    engine, inbox_items, event_outbox, tenant_id: str, message_id: str, mailbox: str, att: Attachment
) -> Tuple[Optional[InboxItem], bool]:
    # Validate size
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    if att.size > max_bytes:
        _inc_mail_failures(1)
        return None, False

    # Detect MIME
    mime = detect_mime(att.content)
    allow = [m.strip() for m in settings.MIME_ALLOWLIST.split(",")]
    if not mime or mime not in allow:
        _inc_mail_failures(1)
        return None, False

    # Hash and storage
    content_hash = sha256_hex(att.content)
    existing = get_inbox_item_by_hash(engine, inbox_items, tenant_id, content_hash)
    if existing:
        # Duplicate: idempotent 200 path
        return existing, True

    file_ext = extension_for_mime(mime)
    uri = put_bytes(tenant_id, content_hash, att.content, file_ext)

    item = InboxItem(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        status="received",
        content_hash=content_hash,
        uri=uri,
        source="mail",
        filename=(att.filename or ""),
        mime=mime,
    )

    persisted = insert_inbox_item(engine, inbox_items, item)

    # Outbox event; idempotency key combines message and content hash
    idem_key = f"{message_id}:{content_hash}"
    payload = {
        "inbox_item_id": persisted.id,
        "content_hash": content_hash,
        "uri": persisted.uri,
        "source": "mail",
        "filename": persisted.filename,
        "mime": mime,
        "message_id": message_id,
        "mailbox": mailbox,
    }
    try:
        with engine.begin() as conn:
            conn.execute(
                event_outbox.insert().values(
                    id=str(uuid.uuid4()),
                    tenant_id=tenant_id,
                    event_type="InboxItemValidated",
                    schema_version="1.0",
                    idempotency_key=idem_key,
                    trace_id=str(uuid.uuid4()),
                    payload_json=json.dumps(payload),
                    status="pending",
                )
            )
    except IntegrityError:
        # duplicate event; ignore
        pass

    # Trigger MCP shadow analysis (local-only) using sample path by MIME
    try:
        mcp_logger = get_mcp_logger("mcp")
        sample_map = {
            "application/pdf": "artifacts/inbox/samples/pdf/sample.pdf",
            "image/png": "artifacts/inbox/samples/images/sample.png",
            "image/jpeg": "artifacts/inbox/samples/images/sample.png",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "artifacts/inbox/samples/office/sample.docx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation": "artifacts/inbox/samples/office/sample.pptx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "artifacts/inbox/samples/excel/sample.xlsx",
        }
        shadow_path = sample_map.get(mime, "artifacts/inbox/samples/pdf/sample.pdf")
        trace_id = str(uuid.uuid4())
        artifact_path = run_shadow_analysis(
            tenant_id=tenant_id,
            trace_id=trace_id,
            source_uri_or_path=shadow_path,
            content_sha256=content_hash,
            inbox_item_id=persisted.id,
        )
        if getattr(settings, "MCP_SHADOW_EMIT_ANALYSIS_EVENT", False):
            payload2 = {
                "inbox_item_id": persisted.id,
                "tenant_id": tenant_id,
                "trace_id": trace_id,
                "mcp_artifact_path": artifact_path,
            }
            try:
                with engine.begin() as conn:
                    conn.execute(
                        event_outbox.insert().values(
                            id=str(uuid.uuid4()),
                            tenant_id=tenant_id,
                            event_type="InboxItemAnalysisReady",
                            schema_version="1.0",
                            idempotency_key=f"analysis:{persisted.id}",
                            trace_id=trace_id,
                            payload_json=json.dumps(payload2),
                        )
                    )
                mcp_logger.info("mcp_analysis_event_emitted", extra={"trace_id": trace_id, "tenant_id": tenant_id, "inbox_item_id": persisted.id})
            except Exception:
                pass
    except Exception:
        pass

    return persisted, False


def process_mailbox(tenant_id: str, mailbox: Optional[str] = None, connector: Optional[MailConnector] = None) -> Dict[str, Any]:
    """Process one batch of messages from configured provider.

    Returns summary stats for logging and tests.
    """
    t0 = time.time()
    set_tenant_id(tenant_id)
    mailbox = mailbox or settings.MAILBOX_NAME

    engine = create_engine(settings.database_url, future=True)
    metadata = MetaData()
    inbox_items, event_outbox = get_tables(metadata)

    # Connector DI: prefer provided connector, otherwise use env-based adapter
    provider = settings.MAIL_PROVIDER.lower()
    connector = connector or _auto_connector(provider)

    # Compute since time window
    since_hours = max(0, int(settings.MAIL_SINCE_HOURS))
    since = datetime.now(timezone.utc) - timedelta(hours=since_hours)

    msgs = connector.fetch_messages(mailbox, since, settings.MAIL_BATCH_LIMIT)

    _inc_mail_messages(len(msgs))
    processed = 0
    duplicates = 0
    total_atts = 0
    deferred = 0
    bytes_budget = int(settings.MAIL_MAX_BYTES_PER_RUN or 0)
    used_bytes = 0

    for msg in msgs:
        att_count = len(msg.attachments)
        _inc_mail_attachments(att_count)
        total_atts += att_count
        for att in msg.attachments:
            try:
                if bytes_budget and (used_bytes + att.size) > bytes_budget:
                    deferred += 1
                    try:
                        from backend.core.observability.metrics import increment_mail_deferred

                        increment_mail_deferred()
                    except Exception:
                        pass
                    continue
                res, dup = _process_attachment(engine, inbox_items, event_outbox, tenant_id, msg.id, mailbox, att)
                if dup:
                    duplicates += 1
                if res is not None:
                    used_bytes += att.size
                    processed += 1
            except StorageError as e:
                _inc_mail_failures(1)
            except Exception:
                _inc_mail_failures(1)

    dur_ms = (time.time() - t0) * 1000.0
    _record_mail_latency(dur_ms)
    logger.info(
        "mail_ingest_end",
        extra={
            "tenant_id": tenant_id,
            "mailbox": mailbox,
            "attach_count": total_atts,
            "processed_count": processed,
            "duplicates": duplicates,
            "duration_ms": dur_ms,
        },
    )
    return {
        "messages": len(msgs),
        "attachments": total_atts,
        "processed": processed,
        "duplicates": duplicates,
        "deferred": deferred,
        "duration_ms": dur_ms,
    }
