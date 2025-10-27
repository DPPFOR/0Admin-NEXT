import json
import time
import uuid

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import MetaData, create_engine
from sqlalchemy.exc import IntegrityError

from backend.apps.inbox.orchestration.run_shadow_analysis import run_shadow_analysis
from backend.core.config import settings
from backend.core.observability.logging import logger, set_tenant_id
from backend.core.observability.metrics import (
    increment_dedupe_hits,
    increment_inbox_received,
    increment_inbox_validated,
    observe_duration,
    record_fetch_duration,
)
from backend.core.tenant.context import require_tenant
from backend.mcp.server.observability import get_logger as get_mcp_logger

from .ingest import IngestError, ensure_url_allowed, fetch_remote
from .repository import InboxItem, get_inbox_item_by_hash, get_tables, insert_inbox_item
from .storage import StorageError, put_bytes
from .utils import detect_mime, extension_for_mime, sha256_hex

router = APIRouter(prefix="/api/v1/inbox/items")


class UploadResponse(BaseModel):
    id: str
    status: str
    tenant_id: str
    content_hash: str
    uri: str
    source: str | None = None
    filename: str | None = None
    mime: str | None = None
    duplicate: bool = False


def _error(status_code: int, code: str, detail: str):
    raise HTTPException(status_code=status_code, detail={"error": code, "detail": detail})


@router.post("/upload", response_model=UploadResponse)
async def upload_item(
    file: UploadFile = File(...),
    source: str | None = Form(None),
    filename: str | None = Form(None),
    meta_json: str | None = Form(None),
    authorization: str | None = Header(None, alias="Authorization"),
    tenant_id: str = Depends(require_tenant),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    trace_header: str | None = Header(None, alias="X-Trace-ID"),
):
    start = time.time()

    # AuthN/AuthZ: Authorization header present, X-Tenant must be valid UUID
    if not authorization or not authorization.lower().startswith("bearer "):
        _error(
            status.HTTP_401_UNAUTHORIZED, "unauthorized", "Missing or invalid Authorization header"
        )
    # Minimal service-token validation: if whitelist configured, token must match
    token = (
        authorization.split(" ", 1)[1].strip() if " " in authorization else authorization.strip()
    )
    allowed = [t.strip() for t in settings.AUTH_SERVICE_TOKENS.split(",") if t.strip()]
    if allowed and token not in allowed:
        _error(status.HTTP_401_UNAUTHORIZED, "unauthorized", "Invalid service token")

    tenant_uuid = tenant_id
    set_tenant_id(tenant_id)

    # Read bytes
    data = await file.read()
    size_bytes = len(data)

    increment_inbox_received()
    trace_id = trace_header or str(uuid.uuid4())

    # Avoid PII: do not log original filename or raw content
    logger.info(
        "upload_start",
        extra={
            "trace_id": trace_id,
            "size": size_bytes,
            "idempotency_key": idempotency_key or "",
        },
    )

    # Size validation
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    if size_bytes > max_bytes:
        observe_duration(start, "ingest_duration_ms")
        _error(status.HTTP_400_BAD_REQUEST, "size_limit", "File exceeds MAX_UPLOAD_MB limit")

    # MIME detection and allowlist
    detected_mime = detect_mime(data)
    allowlist = [m.strip() for m in settings.MIME_ALLOWLIST.split(",")]
    if not detected_mime or detected_mime not in allowlist:
        observe_duration(start, "ingest_duration_ms")
        _error(status.HTTP_400_BAD_REQUEST, "unsupported_mime", "MIME not allowed by server policy")

    # Hash
    content_hash = sha256_hex(data)

    # Source, filename handling
    src_value = (source or "upload").strip()[:64]
    client_filename = (filename or file.filename or "").strip()

    # Store
    file_ext = extension_for_mime(detected_mime)
    try:
        uri = put_bytes(tenant_uuid, content_hash, data, file_ext)
    except StorageError as e:
        logger.error("storage_error", extra={"trace_id": trace_id, "error": str(e)})
        observe_duration(start, "ingest_duration_ms")
        _error(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "io_error", "Failed to persist file to storage"
        )

    # Prepare DB access
    engine = create_engine(settings.database_url, future=True)
    metadata = MetaData()
    inbox_items, event_outbox = get_tables(metadata)

    # Check duplicate by (tenant_id, content_hash)
    existing = get_inbox_item_by_hash(engine, inbox_items, tenant_uuid, content_hash)
    if existing:
        increment_dedupe_hits()
        logger.info(
            "dedupe_hit",
            extra={
                "trace_id": trace_id,
                "inbox_item_id": existing.id,
                "content_hash": content_hash,
            },
        )
        observe_duration(start, "ingest_duration_ms")
        return UploadResponse(
            id=existing.id,
            status=existing.status,
            tenant_id=existing.tenant_id,
            content_hash=existing.content_hash,
            uri=existing.uri,
            source=existing.source or src_value,
            filename=existing.filename or client_filename,
            mime=existing.mime or detected_mime,
            duplicate=True,
        )

    # Insert new inbox item (received -> validated)
    new_item = InboxItem(
        id=str(uuid.uuid4()),
        tenant_id=tenant_uuid,
        status="received",
        content_hash=content_hash,
        uri=uri,
        source=src_value,
        filename=client_filename,
        mime=detected_mime,
    )

    try:
        persisted = insert_inbox_item(engine, inbox_items, new_item)
    except IntegrityError:
        # Race: treat as duplicate and return the original
        increment_dedupe_hits()
        existing = get_inbox_item_by_hash(engine, inbox_items, tenant_uuid, content_hash)
        if existing is None:
            logger.error(
                "dedupe_resolution_failed",
                extra={"trace_id": trace_id, "content_hash": content_hash},
            )
            observe_duration(start, "ingest_duration_ms")
            _error(status.HTTP_409_CONFLICT, "hash_duplicate", "Duplicate content detected")
        observe_duration(start, "ingest_duration_ms")
        return UploadResponse(
            id=existing.id,
            status=existing.status,
            tenant_id=existing.tenant_id,
            content_hash=existing.content_hash,
            uri=existing.uri,
            source=existing.source or src_value,
            filename=existing.filename or client_filename,
            mime=existing.mime or detected_mime,
            duplicate=True,
        )
    except Exception as e:
        logger.error("db_error", extra={"trace_id": trace_id, "error": str(e)})
        observe_duration(start, "ingest_duration_ms")
        _error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "io_error",
            "Database error while persisting inbox item",
        )

    # Outbox event: InboxItemValidated (idempotent via UNIQUE (tenant_id, idempotency_key, event_type))
    payload = {
        "inbox_item_id": persisted.id,
        "content_hash": content_hash,
        "uri": uri,
        "source": src_value,
        "filename": client_filename,
        "mime": detected_mime,
    }
    try:
        with engine.begin() as conn:
            conn.execute(
                event_outbox.insert().values(
                    id=str(uuid.uuid4()),
                    tenant_id=tenant_uuid,
                    event_type="InboxItemValidated",
                    schema_version="1.0",
                    idempotency_key=(idempotency_key or None),
                    trace_id=trace_id,
                    payload_json=json.dumps(payload),
                )
            )
        logger.info(
            "event_emit",
            extra={
                "trace_id": trace_id,
                "event_type": "InboxItemValidated",
                "inbox_item_id": persisted.id,
                "idempotency_key": idempotency_key or "",
            },
        )
    except IntegrityError:
        # Idempotency guard: event already enqueued; treat as success
        logger.info(
            "event_emit_duplicate_guard",
            extra={
                "trace_id": trace_id,
                "event_type": "InboxItemValidated",
                "inbox_item_id": persisted.id,
                "idempotency_key": idempotency_key or "",
            },
        )
    except Exception as e:
        # Non-fatal: item persisted; log warning
        logger.warning("event_emit_failed", extra={"trace_id": trace_id, "error": str(e)})

    increment_inbox_validated()
    observe_duration(start, "ingest_duration_ms")

    # MCP shadow analysis (read-only). Build a local sample path by MIME for shadowing only.
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
        shadow_path = sample_map.get(detected_mime, "artifacts/inbox/samples/pdf/sample.pdf")
        artifact_path = run_shadow_analysis(
            tenant_id=tenant_uuid,
            trace_id=trace_id,
            source_uri_or_path=shadow_path,
            content_sha256=content_hash,
            inbox_item_id=persisted.id,
        )
        # Optional: emit info-event via outbox (flag)
        if getattr(settings, "MCP_SHADOW_EMIT_ANALYSIS_EVENT", False):
            payload2 = {
                "inbox_item_id": persisted.id,
                "tenant_id": tenant_uuid,
                "trace_id": trace_id,
                "mcp_artifact_path": artifact_path,
            }
            try:
                with engine.begin() as conn:
                    conn.execute(
                        event_outbox.insert().values(
                            id=str(uuid.uuid4()),
                            tenant_id=tenant_uuid,
                            event_type="InboxItemAnalysisReady",
                            schema_version="1.0",
                            idempotency_key=f"analysis:{persisted.id}",
                            trace_id=trace_id,
                            payload_json=json.dumps(payload2),
                        )
                    )
                mcp_logger.info(
                    "mcp_analysis_event_emitted",
                    extra={
                        "trace_id": trace_id,
                        "tenant_id": tenant_uuid,
                        "inbox_item_id": persisted.id,
                    },
                )
            except Exception:
                # Non-fatal; shadow analysis remains local-only
                pass
    except Exception:
        # Swallow any shadow errors to keep primary path unaffected
        pass

    return UploadResponse(
        id=persisted.id,
        status=persisted.status,
        tenant_id=persisted.tenant_id,
        content_hash=persisted.content_hash,
        uri=persisted.uri,
        source=persisted.source,
        filename=persisted.filename,
        mime=persisted.mime,
        duplicate=False,
    )


class ProgrammaticIngestRequest(BaseModel):
    remote_url: str
    source: str | None = "api"
    meta_json: str | None = None


@router.post("")
async def ingest_item(
    body: ProgrammaticIngestRequest,
    authorization: str | None = Header(None, alias="Authorization"),
    tenant_id: str = Depends(require_tenant),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    trace_header: str | None = Header(None, alias="X-Trace-ID"),
):
    start = time.time()

    # Auth
    if not authorization or not authorization.lower().startswith("bearer "):
        _error(
            status.HTTP_401_UNAUTHORIZED, "unauthorized", "Missing or invalid Authorization header"
        )
    token = (
        authorization.split(" ", 1)[1].strip() if " " in authorization else authorization.strip()
    )
    allowed = [t.strip() for t in settings.AUTH_SERVICE_TOKENS.split(",") if t.strip()]
    if allowed and token not in allowed:
        _error(status.HTTP_401_UNAUTHORIZED, "unauthorized", "Invalid service token")
    tenant_uuid = tenant_id
    set_tenant_id(tenant_uuid)

    increment_inbox_received()
    trace_id = trace_header or str(uuid.uuid4())
    logger.info(
        "programmatic_ingest_start",
        extra={
            "trace_id": trace_id,
            "ingest_source": "remote_url",
            "idempotency_key": idempotency_key or "",
        },
    )

    # URL allow/deny and scheme checks before network
    try:
        ensure_url_allowed(body.remote_url)
    except IngestError as e:
        observe_duration(start, "ingest_duration_ms")
        _error(e.http_status, e.code, str(e))

    # Fetch
    try:
        content, filename_guess, detected_mime, fetch_ms = fetch_remote(body.remote_url)
    except IngestError as e:
        logger.warning(
            "programmatic_ingest_fetch_error", extra={"trace_id": trace_id, "code": e.code}
        )
        observe_duration(start, "ingest_duration_ms")
        _error(e.http_status, e.code, str(e))
    except Exception as e:
        logger.error("programmatic_ingest_io_error", extra={"trace_id": trace_id, "error": str(e)})
        observe_duration(start, "ingest_duration_ms")
        _error(status.HTTP_500_INTERNAL_SERVER_ERROR, "io_error", "Fetch failed")
    # Record fetch latency metric
    try:
        record_fetch_duration(fetch_ms)
    except Exception:
        pass

    # Size re-check (defense-in-depth)
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    if len(content) > max_bytes:
        observe_duration(start, "ingest_duration_ms")
        _error(status.HTTP_400_BAD_REQUEST, "size_limit", "Payload exceeds size limit")

    # MIME allowlist
    allowlist = [m.strip() for m in settings.MIME_ALLOWLIST.split(",")]
    if not detected_mime or detected_mime not in allowlist:
        observe_duration(start, "ingest_duration_ms")
        _error(status.HTTP_400_BAD_REQUEST, "unsupported_mime", "MIME not allowed by server policy")

    # Hash
    content_hash = sha256_hex(content)

    # Source/filename handling
    src_value = (body.source or "api").strip()[:64]
    client_filename = (filename_guess or "").strip()

    # Store
    file_ext = extension_for_mime(detected_mime)
    try:
        uri = put_bytes(tenant_uuid, content_hash, content, file_ext)
    except StorageError as e:
        logger.error("storage_error", extra={"trace_id": trace_id, "error": str(e)})
        observe_duration(start, "ingest_duration_ms")
        _error(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "io_error", "Failed to persist file to storage"
        )

    # DB setup
    engine = create_engine(settings.database_url, future=True)
    metadata = MetaData()
    inbox_items, event_outbox = get_tables(metadata)

    # Dedupe
    existing = get_inbox_item_by_hash(engine, inbox_items, tenant_uuid, content_hash)
    if existing:
        increment_dedupe_hits()
        logger.info(
            "dedupe_hit",
            extra={
                "trace_id": trace_id,
                "inbox_item_id": existing.id,
                "content_hash": content_hash,
            },
        )
        observe_duration(start, "ingest_duration_ms")
        return UploadResponse(
            id=existing.id,
            status=existing.status,
            tenant_id=existing.tenant_id,
            content_hash=existing.content_hash,
            uri=existing.uri,
            source=existing.source or src_value,
            filename=existing.filename or client_filename,
            mime=existing.mime or detected_mime,
            duplicate=True,
        )

    new_item = InboxItem(
        id=str(uuid.uuid4()),
        tenant_id=tenant_uuid,
        status="received",
        content_hash=content_hash,
        uri=uri,
        source=src_value,
        filename=client_filename,
        mime=detected_mime,
    )

    try:
        persisted = insert_inbox_item(engine, inbox_items, new_item)
    except IntegrityError:
        increment_dedupe_hits()
        existing = get_inbox_item_by_hash(engine, inbox_items, tenant_uuid, content_hash)
        if existing is None:
            logger.error(
                "dedupe_resolution_failed",
                extra={"trace_id": trace_id, "content_hash": content_hash},
            )
            observe_duration(start, "ingest_duration_ms")
            _error(status.HTTP_409_CONFLICT, "hash_duplicate", "Duplicate content detected")
        observe_duration(start, "ingest_duration_ms")
        return UploadResponse(
            id=existing.id,
            status=existing.status,
            tenant_id=existing.tenant_id,
            content_hash=existing.content_hash,
            uri=existing.uri,
            source=existing.source or src_value,
            filename=existing.filename or client_filename,
            mime=existing.mime or detected_mime,
            duplicate=True,
        )
    except Exception as e:
        logger.error("db_error", extra={"trace_id": trace_id, "error": str(e)})
        observe_duration(start, "ingest_duration_ms")
        _error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "io_error",
            "Database error while persisting inbox item",
        )

    # Outbox event
    payload = {
        "inbox_item_id": persisted.id,
        "content_hash": content_hash,
        "uri": uri,
        "source": src_value,
        "filename": client_filename,
        "mime": detected_mime,
    }
    try:
        with engine.begin() as conn:
            conn.execute(
                event_outbox.insert().values(
                    id=str(uuid.uuid4()),
                    tenant_id=tenant_uuid,
                    event_type="InboxItemValidated",
                    schema_version="1.0",
                    idempotency_key=(idempotency_key or None),
                    trace_id=trace_id,
                    payload_json=json.dumps(payload),
                )
            )
        logger.info(
            "event_emit",
            extra={
                "trace_id": trace_id,
                "event_type": "InboxItemValidated",
                "inbox_item_id": persisted.id,
                "idempotency_key": idempotency_key or "",
                "ingest_source": "remote_url",
                "fetch_duration_ms": fetch_ms,
            },
        )
    except IntegrityError:
        logger.info(
            "event_emit_duplicate_guard",
            extra={
                "trace_id": trace_id,
                "event_type": "InboxItemValidated",
                "inbox_item_id": persisted.id,
                "idempotency_key": idempotency_key or "",
            },
        )
    except Exception as e:
        logger.warning("event_emit_failed", extra={"trace_id": trace_id, "error": str(e)})

    increment_inbox_validated()
    observe_duration(start, "ingest_duration_ms")

    return UploadResponse(
        id=persisted.id,
        status=persisted.status,
        tenant_id=persisted.tenant_id,
        content_hash=persisted.content_hash,
        uri=persisted.uri,
        source=persisted.source,
        filename=persisted.filename,
        mime=persisted.mime,
        duplicate=False,
    )
