from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from backend.apps.inbox.importer.worker import run_importer
from backend.apps.inbox.orchestration.inbox_local_flow import run_inbox_local_flow
from backend.apps.inbox.read_model.query import fetch_tenant_summary
from backend.core.config import settings

RUN_DB_TESTS = os.getenv("RUN_DB_TESTS") == "1"
DB_URL = os.getenv("INBOX_DB_URL") or os.getenv("DATABASE_URL")
TENANT = "00000000-0000-0000-0000-000000000001"


pytestmark = pytest.mark.skipif(
    not RUN_DB_TESTS or not DB_URL,
    reason="Set RUN_DB_TESTS=1 and DATABASE_URL/INBOX_DB_URL for flag marker tests.",
)


def _ensure_database_ready(engine: sa.engine.Engine) -> None:
    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "ops/alembic")
    cfg.set_main_option("sqlalchemy.url", DB_URL)
    command.upgrade(cfg, "head")
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE inbox_parsed.parsed_item_chunks CASCADE"))
        conn.execute(text("TRUNCATE inbox_parsed.parsed_items CASCADE"))


def test_flow_flags_roundtrip():
    engine = sa.create_engine(DB_URL, future=True)
    _ensure_database_ready(engine)
    settings.database_url = DB_URL

    artifacts_root = Path("artifacts/inbox")
    artifacts_root.mkdir(parents=True, exist_ok=True)

    source_name = f"flags-{uuid4().hex}.pdf"
    source_path = artifacts_root / source_name
    source_path.write_bytes(b"%PDF-1.4\\n% flag test\\n")

    out_path = run_inbox_local_flow(
        tenant_id=TENANT,
        path=str(source_path),
        trace_id="trace-flags",
        enable_ocr=True,
        enable_browser=False,
        enable_table_boost=True,
        mvr_preview=True,
    )

    with open(out_path, encoding="utf-8") as fh:
        artifact = json.load(fh)

    assert artifact["flags"]["enable_ocr"] is True
    assert artifact["flags"]["enable_table_boost"] is True
    assert artifact["flags"]["mvr_preview"] is True

    parsed_id = run_importer(
        tenant_id=TENANT,
        artifact_path=out_path,
        engine=engine,
        enforce_invoice=False,
        enforce_payment=True,
        enforce_other=True,
        replace_chunks=True,
    )

    with engine.begin() as conn:
        row = (
            conn.execute(
                text(
                    """
                SELECT content_hash, flags, mvr_preview, mvr_score
                FROM inbox_parsed.parsed_items
                WHERE id = :id
                """
                ),
                {"id": parsed_id},
            )
            .mappings()
            .first()
        )

    assert row is not None
    assert row["flags"].get("enable_table_boost") is True
    assert row["mvr_preview"] is True
    assert str(row["mvr_score"]) in {"0", "0.00"}

    summary = fetch_tenant_summary(TENANT)
    assert summary is not None
    assert summary.cnt_items >= 1
    assert summary.cnt_mvr_preview >= 1

    # Clean up generated files
    try:
        Path(out_path).unlink(missing_ok=True)
    finally:
        source_path.unlink(missing_ok=True)
