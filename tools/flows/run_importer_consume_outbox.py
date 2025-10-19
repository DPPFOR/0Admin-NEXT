#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import importlib.util as _iu
from pathlib import Path as _Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sqlalchemy import MetaData, Table, Column, String, Text, DateTime, select, update, delete
from sqlalchemy.engine import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql import func

_spec = _iu.spec_from_file_location(
    "importer_worker", str(_Path("backend/apps/inbox/importer/worker.py"))
)
_mod = _iu.module_from_spec(_spec)  # type: ignore[arg-type]
assert _spec and _spec.loader
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
run_importer = _mod.run_importer

from backend.core.config import settings  # noqa: E402
from backend.mcp.server.observability import get_logger  # noqa: E402


def _event_outbox_table(metadata: MetaData) -> Table:
    return Table(
        "event_outbox",
        metadata,
        Column("id", String, primary_key=True),
        Column("tenant_id", String, nullable=False),
        Column("event_type", String, nullable=False),
        Column("schema_version", String, nullable=False),
        Column("idempotency_key", String),
        Column("trace_id", String),
        Column("payload_json", Text, nullable=False),
        Column("status", String),
        Column("created_at", DateTime(timezone=True), server_default=func.now()),
        extend_existing=True,
    )


def main() -> int:
    logger = get_logger("importer-consumer")
    try:
        engine = create_engine(settings.database_url, future=True)
    except SQLAlchemyError as exc:
        print(str(exc), file=sys.stderr)
        return 3
    metadata = MetaData()
    event_outbox = _event_outbox_table(metadata)

    try:
        with engine.begin() as conn:
            row = conn.execute(
                select(
                    event_outbox.c.id,
                    event_outbox.c.tenant_id,
                    event_outbox.c.trace_id,
                    event_outbox.c.payload_json,
                )
                .where(event_outbox.c.event_type == "InboxItemAnalysisReady")
                .where(event_outbox.c.schema_version == "1.0")
                .order_by(event_outbox.c.created_at.asc())
                .limit(1)
            ).fetchone()
    except SQLAlchemyError as exc:
        print(str(exc), file=sys.stderr)
        return 3

    if not row:
        print("no-event")
        return 0

    payload = json.loads(row.payload_json)
    artifact_path = payload.get("mcp_artifact_path")
    if not artifact_path:
        logger.warning("importer_consumer_missing_artifact", extra={"event_id": row.id})
        return 2

    tenant_id = payload.get("tenant_id") or row.tenant_id
    trace_id = payload.get("trace_id") or row.trace_id

    try:
        parsed_item_id = run_importer(
            tenant_id=tenant_id,
            artifact_path=artifact_path,
            trace_id=trace_id,
            dry_run=False,
            upsert=True,
            replace_chunks=False,
            engine=engine,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except SQLAlchemyError as exc:
        print(str(exc), file=sys.stderr)
        return 3

    try:
        with engine.begin() as conn:
            try:
                conn.execute(
                    update(event_outbox)
                    .where(event_outbox.c.id == row.id)
                    .values(status="processed")
                )
            except SQLAlchemyError:
                conn.execute(delete(event_outbox).where(event_outbox.c.id == row.id))
    except SQLAlchemyError as exc:
        print(str(exc), file=sys.stderr)
        return 3

    logger.info(
        "importer_consumer_processed",
        extra={
            "event_id": row.id,
            "tenant_id": tenant_id,
            "parsed_item_id": parsed_item_id,
        },
    )
    print(parsed_item_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
