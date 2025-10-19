from __future__ import annotations

import os
import json
import importlib.util as _iu

import pytest
from sqlalchemy import create_engine, text


RUN_DB_TESTS = os.getenv("RUN_DB_TESTS") == "1"
DB_URL = os.getenv("INBOX_DB_URL")


@pytest.mark.skipif(not RUN_DB_TESTS or not DB_URL, reason="requires RUN_DB_TESTS=1 and INBOX_DB_URL")
def test_importer_db_roundtrip(tmp_path):
    spec = _iu.spec_from_file_location("worker", "backend/apps/inbox/importer/worker.py")
    mod = _iu.module_from_spec(spec)  # type: ignore[arg-type]
    assert spec and spec.loader
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    run_importer = mod.run_importer

    engine = create_engine(DB_URL, future=True)

    # ensure schema exists
    sql_path = "ops/alembic/versions/20251019_inbox_parsed.sql"
    sql_text = open(sql_path, "r", encoding="utf-8").read()
    with engine.begin() as conn:
        for statement in [s.strip() for s in sql_text.split(";") if s.strip()]:
            conn.execute(text(statement))
        conn.execute(text("TRUNCATE inbox_parsed.parsed_item_chunks CASCADE"))
        conn.execute(text("TRUNCATE inbox_parsed.parsed_items CASCADE"))

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
                "SELECT doc_type, quality_flags, payload FROM inbox_parsed.parsed_items WHERE id=:id"
            ),
            {"id": parsed_id},
        ).fetchone()
        assert row is not None
        assert row.doc_type == "pdf"
        assert isinstance(row.quality_flags, list)

        chunk_count = conn.execute(
            text("SELECT COUNT(*) FROM inbox_parsed.parsed_item_chunks WHERE parsed_item_id=:id"),
            {"id": parsed_id},
        ).scalar_one()
        assert chunk_count >= 1
