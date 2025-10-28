from __future__ import annotations

import json
import os
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine, create_engine
from sqlalchemy.sql import func

from backend.core.config import settings
from backend.mcp.server.observability import get_logger

try:  # pragma: no cover - regular import path
    from .dto import ParsedItemChunkDTO, ParsedItemDTO, ProcessResult  # type: ignore
    from .mapper import artifact_to_dtos  # type: ignore
    from .validators import validate_artifact_minimum, validate_tables_shape  # type: ignore
except Exception:  # pragma: no cover - fallback for direct module load (tests/CLI)
    import importlib.util as _iu
    import sys as _sys

    _BASE = os.path.dirname(__file__)

    def _load(name: str):
        spec = _iu.spec_from_file_location(name, os.path.join(_BASE, f"{name}.py"))
        module = _iu.module_from_spec(spec)  # type: ignore[arg-type]
        assert spec and spec.loader
        _sys.modules[spec.name] = module
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        return module

    dto_mod = _load("dto")
    validators_mod = _load("validators")
    mapper_mod = _load("mapper")

    ParsedItemDTO = dto_mod.ParsedItemDTO  # type: ignore[attr-defined]
    ParsedItemChunkDTO = dto_mod.ParsedItemChunkDTO  # type: ignore[attr-defined]
    validate_artifact_minimum = validators_mod.validate_artifact_minimum  # type: ignore[attr-defined]
    validate_tables_shape = validators_mod.validate_tables_shape  # type: ignore[attr-defined]
    artifact_to_dtos = mapper_mod.artifact_to_dtos  # type: ignore[attr-defined]


SCHEMA = "inbox_parsed"
_METADATA = sa.MetaData()

PARSED_ITEMS_TABLE = sa.Table(
    "parsed_items",
    _METADATA,
    sa.Column("id", PGUUID(as_uuid=False), primary_key=True),
    sa.Column("tenant_id", PGUUID(as_uuid=False), nullable=False),
    sa.Column("content_hash", sa.String(), nullable=False),
    sa.Column("doc_type", sa.String(), nullable=False),
    sa.Column("quality_flags", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
    sa.Column("payload", JSONB, nullable=False),
    sa.Column("amount", sa.Numeric(18, 2)),
    sa.Column("invoice_no", sa.String()),
    sa.Column("due_date", sa.Date()),
    sa.Column("doctype", sa.String(), nullable=False, server_default=sa.text("'unknown'")),
    sa.Column(
        "quality_status", sa.String(), nullable=False, server_default=sa.text("'needs_review'")
    ),
    sa.Column("confidence", sa.Numeric(5, 2), nullable=False, server_default=sa.text("0")),
    sa.Column("rules", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
    sa.Column("flags", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    sa.Column("mvr_preview", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    sa.Column("mvr_score", sa.Numeric(5, 2)),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("timezone('utc', now())"),
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("timezone('utc', now())"),
        onupdate=func.now(),
    ),
    schema=SCHEMA,
    extend_existing=True,
)

PARSED_ITEM_CHUNKS_TABLE = sa.Table(
    "parsed_item_chunks",
    _METADATA,
    sa.Column("id", PGUUID(as_uuid=False), primary_key=True),
    sa.Column("parsed_item_id", PGUUID(as_uuid=False), nullable=False),
    sa.Column("seq", sa.Integer(), nullable=False),
    sa.Column("kind", sa.String(), nullable=False),
    sa.Column("payload", JSONB, nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("timezone('utc', now())"),
    ),
    schema=SCHEMA,
    extend_existing=True,
)

CHUNK_UNIQUE_ELEMENTS = [
    PARSED_ITEM_CHUNKS_TABLE.c.parsed_item_id,
    PARSED_ITEM_CHUNKS_TABLE.c.kind,
    PARSED_ITEM_CHUNKS_TABLE.c.seq,
]

# Audit log table
AUDIT_LOG_TABLE = sa.Table(
    "audit_log",
    _METADATA,
    sa.Column("id", PGUUID(as_uuid=False), primary_key=True),
    sa.Column(
        "ts",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("timezone('utc', now())"),
    ),
    sa.Column("trace_id", sa.String()),
    sa.Column("actor", sa.String()),
    sa.Column("tenant_id", PGUUID(as_uuid=False)),
    sa.Column("item_id", PGUUID(as_uuid=False)),
    sa.Column("source", sa.String()),
    sa.Column("op", sa.String()),
    sa.Column("meta", JSONB),
    schema="ops",
    extend_existing=True,
)


def _valid_artifact_path(path: str) -> bool:
    return (
        isinstance(path, str)
        and path.startswith("artifacts/")
        and not path.startswith("/")
        and ".." not in path
    )


def _ensure_engine(engine: Engine | None) -> Engine:
    return engine or create_engine(settings.database_url, future=True)


def _log_audit_event(
    conn,
    tenant_id: str,
    item_id: str,
    source: str,
    op: str,
    trace_id: str | None = None,
    actor: str | None = None,
    meta: dict | None = None,
) -> None:
    """Log an audit event to the audit_log table."""
    audit_id = str(uuid.uuid4())
    audit_stmt = sa.insert(AUDIT_LOG_TABLE).values(
        id=audit_id,
        tenant_id=tenant_id,
        item_id=item_id,
        source=source,
        op=op,
        trace_id=trace_id,
        actor=actor,
        meta=meta or {},
    )
    conn.execute(audit_stmt)


def process_artifact_file(
    tenant_id: str,
    artifact_path: str,
    engine: Engine | None = None,
) -> ProcessResult:
    """Process an artifact file and return the result."""

    engine = _ensure_engine(engine)

    with engine.begin() as conn:
        # Load artifact data
        import json

        with open(artifact_path) as f:
            artifact_data = json.load(f)

        # Convert to DTOs
        from .mapper import artifact_to_dtos

        item, chunks = artifact_to_dtos(artifact_data)
        item.tenant_id = tenant_id

        # Upsert item
        parsed_item_id, action = _upsert_parsed_item(conn, item)

        # Insert chunks
        chunk_count = 0
        for chunk in chunks:
            chunk.parsed_item_id = parsed_item_id
            try:
                conn.execute(
                    sa.insert(PARSED_ITEM_CHUNKS_TABLE).values(
                        id=str(uuid.uuid4()),
                        parsed_item_id=chunk.parsed_item_id,
                        seq=chunk.seq,
                        kind=chunk.kind,
                        payload=chunk.payload,
                    )
                )
                chunk_count += 1
            except Exception:
                # Ignore duplicate chunks
                pass

        return ProcessResult(parsed_item_id=parsed_item_id, action=action, chunk_count=chunk_count)


def _upsert_parsed_item(
    conn,
    item: ParsedItemDTO,
) -> tuple[str, str]:
    # Deterministic ID generation based on tenant_id and content_hash
    import hashlib

    deterministic_input = f"{item.tenant_id}|{item.content_hash}"
    deterministic_hash = hashlib.sha256(deterministic_input.encode()).hexdigest()[:32]
    insert_id = str(uuid.UUID(deterministic_hash))
    upsert_stmt = (
        pg_insert(PARSED_ITEMS_TABLE)
        .values(
            id=sa.bindparam("id"),
            tenant_id=sa.bindparam("tenant_id"),
            content_hash=sa.bindparam("content_hash", type_=sa.String),
            doc_type=sa.bindparam("doc_type", type_=sa.String),
            doctype=sa.bindparam("doctype", type_=sa.String),
            quality_status=sa.bindparam("quality_status", type_=sa.String),
            confidence=sa.bindparam("confidence", type_=sa.Numeric(5, 2)),
            rules=sa.bindparam("rules", type_=JSONB),
            quality_flags=sa.bindparam("quality_flags", type_=JSONB),
            payload=sa.bindparam("payload", type_=JSONB),
            amount=sa.bindparam("amount", type_=sa.Numeric(18, 2)),
            invoice_no=sa.bindparam("invoice_no", type_=sa.String),
            due_date=sa.bindparam("due_date", type_=sa.Date),
            flags=sa.bindparam("flags", type_=JSONB),
            mvr_preview=sa.bindparam("mvr_preview", type_=sa.Boolean),
            mvr_score=sa.bindparam("mvr_score", type_=sa.Numeric(5, 2)),
        )
        .on_conflict_do_update(
            index_elements=[PARSED_ITEMS_TABLE.c.tenant_id, PARSED_ITEMS_TABLE.c.content_hash],
            set_={
                "doc_type": sa.bindparam("u_doc_type", type_=sa.String),
                "doctype": sa.bindparam("u_doctype", type_=sa.String),
                "quality_status": sa.bindparam("u_quality_status", type_=sa.String),
                "confidence": sa.bindparam("u_confidence", type_=sa.Numeric(5, 2)),
                "rules": sa.bindparam("u_rules", type_=JSONB),
                "quality_flags": sa.bindparam("u_quality_flags", type_=JSONB),
                "payload": sa.bindparam("u_payload", type_=JSONB),
                "amount": sa.bindparam("u_amount", type_=sa.Numeric(18, 2)),
                "invoice_no": sa.bindparam("u_invoice_no", type_=sa.String),
                "due_date": sa.bindparam("u_due_date", type_=sa.Date),
                "flags": sa.bindparam("u_flags", type_=JSONB),
                "mvr_preview": sa.bindparam("u_mvr_preview", type_=sa.Boolean),
                "mvr_score": sa.bindparam("u_mvr_score", type_=sa.Numeric(5, 2)),
                "updated_at": func.now(),
            },
        )
        .returning(PARSED_ITEMS_TABLE.c.id)
    )
    params = {
        "id": insert_id,
        "tenant_id": item.tenant_id,
        "content_hash": item.content_hash,
        "doc_type": item.doc_type,
        "doctype": item.doctype,
        "quality_status": item.quality_status,
        "confidence": item.confidence,
        "rules": item.rules,
        "quality_flags": item.quality_flags,
        "payload": item.payload,
        "amount": item.amount,
        "invoice_no": item.invoice_no,
        "due_date": item.due_date,
        "flags": item.flags,
        "mvr_preview": item.mvr_preview,
        "mvr_score": item.mvr_score,
        "u_doc_type": item.doc_type,
        "u_doctype": item.doctype,
        "u_quality_status": item.quality_status,
        "u_confidence": item.confidence,
        "u_rules": item.rules,
        "u_quality_flags": item.quality_flags,
        "u_payload": item.payload,
        "u_amount": item.amount,
        "u_invoice_no": item.invoice_no,
        "u_due_date": item.due_date,
        "u_flags": item.flags,
        "u_mvr_preview": item.mvr_preview,
        "u_mvr_score": item.mvr_score,
    }
    row = conn.execute(upsert_stmt, params).fetchone()
    parsed_item_id = row.id
    action = "insert" if parsed_item_id == insert_id else "update"

    # Log audit event
    _log_audit_event(
        conn=conn,
        tenant_id=item.tenant_id,
        item_id=parsed_item_id,
        source="importer",
        op="IMPORT_UPSERT",
        trace_id=getattr(item, "trace_id", None),
        actor=getattr(item, "actor", None),
        meta={"action": action, "content_hash": item.content_hash},
    )

    return parsed_item_id, action


def _insert_only(
    conn,
    item: ParsedItemDTO,
) -> str:
    insert_stmt = (
        PARSED_ITEMS_TABLE.insert()
        .values(
            id=sa.bindparam("id"),
            tenant_id=sa.bindparam("tenant_id"),
            content_hash=sa.bindparam("content_hash", type_=sa.String),
            doc_type=sa.bindparam("doc_type", type_=sa.String),
            doctype=sa.bindparam("doctype", type_=sa.String),
            quality_status=sa.bindparam("quality_status", type_=sa.String),
            confidence=sa.bindparam("confidence", type_=sa.Numeric(5, 2)),
            rules=sa.bindparam("rules", type_=JSONB),
            quality_flags=sa.bindparam("quality_flags", type_=JSONB),
            payload=sa.bindparam("payload", type_=JSONB),
            amount=sa.bindparam("amount", type_=sa.Numeric(18, 2)),
            invoice_no=sa.bindparam("invoice_no", type_=sa.String),
            due_date=sa.bindparam("due_date", type_=sa.Date),
            flags=sa.bindparam("flags", type_=JSONB),
            mvr_preview=sa.bindparam("mvr_preview", type_=sa.Boolean),
            mvr_score=sa.bindparam("mvr_score", type_=sa.Numeric(5, 2)),
        )
        .returning(PARSED_ITEMS_TABLE.c.id)
    )
    params = {
        "id": str(uuid.uuid4()),
        "tenant_id": item.tenant_id,
        "content_hash": item.content_hash,
        "doc_type": item.doc_type,
        "doctype": item.doctype,
        "quality_status": item.quality_status,
        "confidence": item.confidence,
        "rules": item.rules,
        "quality_flags": item.quality_flags,
        "payload": item.payload,
        "amount": item.amount,
        "invoice_no": item.invoice_no,
        "due_date": item.due_date,
        "flags": item.flags,
        "mvr_preview": item.mvr_preview,
        "mvr_score": item.mvr_score,
    }
    row = conn.execute(insert_stmt, params).fetchone()
    return row.id


def _insert_chunks(
    conn,
    parsed_item_id: str,
    chunks: list[ParsedItemChunkDTO],
    *,
    replace_chunks: bool,
) -> int:
    if not chunks:
        return 0

    if replace_chunks:
        conn.execute(
            sa.delete(PARSED_ITEM_CHUNKS_TABLE).where(
                PARSED_ITEM_CHUNKS_TABLE.c.parsed_item_id == parsed_item_id
            )
        )

    chunk_insert = pg_insert(PARSED_ITEM_CHUNKS_TABLE).values(
        id=sa.bindparam("id"),
        parsed_item_id=sa.bindparam("parsed_item_id"),
        seq=sa.bindparam("seq", type_=sa.Integer),
        kind=sa.bindparam("kind", type_=sa.String),
        payload=sa.bindparam("payload", type_=JSONB),
    )
    if not replace_chunks:
        chunk_insert = chunk_insert.on_conflict_do_nothing(index_elements=CHUNK_UNIQUE_ELEMENTS)

    inserted = 0
    for chunk in chunks:
        params = {
            "id": str(uuid.uuid4()),
            "parsed_item_id": parsed_item_id,
            "seq": chunk.seq,
            "kind": chunk.kind,
            "payload": chunk.payload,
        }
        result = conn.execute(chunk_insert, params)
        if result.rowcount and result.rowcount > 0:
            inserted += 1
    return inserted


def _upsert_parsed_item_with_chunks(
    engine: Engine,
    item: ParsedItemDTO,
    chunk_dtos: list[ParsedItemChunkDTO],
    *,
    upsert: bool,
    replace_chunks: bool,
) -> tuple[str, str, int]:
    with engine.begin() as conn:
        existing_row = conn.execute(
            sa.select(PARSED_ITEMS_TABLE.c.id)
            .where(PARSED_ITEMS_TABLE.c.tenant_id == item.tenant_id)
            .where(PARSED_ITEMS_TABLE.c.content_hash == item.content_hash)
        ).fetchone()

        if existing_row and not upsert:
            return existing_row.id, "skip", 0

        if not existing_row and not upsert:
            parsed_id = _insert_only(conn, item)
            inserted_chunks = _insert_chunks(
                conn, parsed_id, chunk_dtos, replace_chunks=replace_chunks
            )
            return parsed_id, "insert", inserted_chunks

        parsed_id, action = _upsert_parsed_item(conn, item)
        inserted_chunks = _insert_chunks(conn, parsed_id, chunk_dtos, replace_chunks=replace_chunks)
        return parsed_id, action, inserted_chunks


def run_importer(
    *,
    tenant_id: str,
    artifact_path: str,
    trace_id: str | None = None,
    dry_run: bool = False,
    upsert: bool = True,
    replace_chunks: bool = False,
    engine: Engine | None = None,
    enforce_invoice: bool = True,
    enforce_payment: bool = True,
    enforce_other: bool = True,
    strict: bool = False,
) -> str:
    logger = get_logger("importer")

    if not _valid_artifact_path(artifact_path):
        raise ValueError("invalid artifact path")

    data = json.loads(open(artifact_path, encoding="utf-8").read())
    validate_artifact_minimum(data, tenant_id)
    validate_tables_shape(data.get("extracted", {}).get("tables", []))

    item_dto, chunk_dtos = artifact_to_dtos(
        data,
        enforce_invoice=enforce_invoice,
        enforce_payment=enforce_payment,
        enforce_other=enforce_other,
    )
    if item_dto.tenant_id != tenant_id:
        raise ValueError("tenant mismatch")

    if strict and item_dto.quality_status == "rejected":
        raise ValueError("artifact rejected by definition of done checks")

    content_hash = item_dto.content_hash

    logger.info(
        "importer_started",
        extra={
            "trace_id": trace_id or "",
            "tenant_id": tenant_id,
            "content_hash": content_hash,
            "dry_run": bool(dry_run),
        },
    )

    if dry_run:
        logger.info(
            "importer_done",
            extra={
                "trace_id": trace_id or "",
                "tenant_id": tenant_id,
                "content_hash": content_hash,
                "action": "plan",
                "dry_run": True,
            },
        )
        return "planned"

    engine = _ensure_engine(engine)

    parsed_item_id, action, inserted_chunks = _upsert_parsed_item_with_chunks(
        engine,
        item_dto,
        chunk_dtos,
        upsert=upsert,
        replace_chunks=replace_chunks,
    )

    logger.info(
        "importer_done",
        extra={
            "trace_id": trace_id or "",
            "tenant_id": tenant_id,
            "content_hash": content_hash,
            "parsed_item_id": parsed_item_id,
            "inserted_chunks": inserted_chunks,
            "action": action,
            "dry_run": False,
            "quality_status": item_dto.quality_status,
            "confidence": float(item_dto.confidence),
        },
    )

    return parsed_item_id


__all__ = ["run_importer"]
