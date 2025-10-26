from __future__ import annotations

import os
import json
import importlib.util as _iu

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text


RUN_DB_TESTS = os.getenv("RUN_DB_TESTS") == "1"
DB_URL = os.getenv("INBOX_DB_URL") or os.getenv("DATABASE_URL")


def _ensure_database_ready(engine) -> None:
    cfg = Config("alembic.ini")
    cfg.set_main_option("script_location", "ops/alembic")
    cfg.set_main_option("sqlalchemy.url", DB_URL)
    command.upgrade(cfg, "head")

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE inbox_parsed.parsed_item_chunks CASCADE"))
        conn.execute(text("TRUNCATE inbox_parsed.parsed_items CASCADE"))


@pytest.mark.skipif(not RUN_DB_TESTS or not DB_URL, reason="requires RUN_DB_TESTS=1 and INBOX_DB_URL")
def test_importer_db_roundtrip(tmp_path):
    spec = _iu.spec_from_file_location("worker", "backend/apps/inbox/importer/worker.py")
    mod = _iu.module_from_spec(spec)  # type: ignore[arg-type]
    assert spec and spec.loader
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    run_importer = mod.run_importer

    engine = create_engine(DB_URL, future=True)
    _ensure_database_ready(engine)

    artifact_path = "artifacts/inbox_local/samples/sample_result.json"
    data = json.loads(open(artifact_path, "r", encoding="utf-8").read())

    parsed_id = run_importer(
        tenant_id=data["tenant_id"],
        artifact_path=artifact_path,
        engine=create_engine(DB_URL, future=True),
        replace_chunks=True,
    )

    with engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT doc_type, doctype, quality_flags, payload, flags, mvr_preview, mvr_score "
                "FROM inbox_parsed.parsed_items WHERE id=:id"
            ),
            {"id": parsed_id},
        ).fetchone()
        assert row is not None
        assert row.doctype == "other"
        assert isinstance(row.quality_flags, list)
        assert row.payload.get("extracted")
        assert isinstance(row.flags, dict)
        assert row.mvr_preview in (True, False)

        chunk_count = conn.execute(
            text("SELECT COUNT(*) FROM inbox_parsed.parsed_item_chunks WHERE parsed_item_id=:id"),
            {"id": parsed_id},
        ).scalar_one()
        assert chunk_count >= 1
