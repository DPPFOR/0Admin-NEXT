from __future__ import annotations

import json
import os
import importlib.util as _iu

import pytest
from decimal import Decimal
from sqlalchemy import create_engine, text
from typing import Callable


RUN_DB_TESTS = os.getenv("RUN_DB_TESTS") == "1"
DB_URL = os.getenv("INBOX_DB_URL") or os.getenv("DATABASE_URL")


def _load_worker():
    spec = _iu.spec_from_file_location("worker", "backend/apps/inbox/importer/worker.py")
    mod = _iu.module_from_spec(spec)  # type: ignore[arg-type]
    assert spec and spec.loader
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _ensure_schema_and_tables(conn) -> None:
    conn.execute(text("CREATE SCHEMA IF NOT EXISTS inbox_parsed"))
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS inbox_parsed.parsed_items (
                id UUID PRIMARY KEY,
                tenant_id UUID NOT NULL,
                content_hash TEXT NOT NULL,
                doc_type TEXT,
                doctype TEXT,
                quality_status TEXT,
                confidence NUMERIC(5,2),
                rules JSONB DEFAULT '[]'::jsonb,
                quality_flags JSONB DEFAULT '[]'::jsonb,
                payload JSONB NOT NULL,
                amount NUMERIC(18,2),
                invoice_no TEXT,
                due_date DATE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT (timezone('utc', now())),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT (timezone('utc', now())),
                UNIQUE (tenant_id, content_hash)
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS inbox_parsed.parsed_item_chunks (
                id UUID PRIMARY KEY,
                parsed_item_id UUID NOT NULL REFERENCES inbox_parsed.parsed_items(id) ON DELETE CASCADE,
                idx INTEGER,
                kind TEXT,
                seq INTEGER,
                payload JSONB NOT NULL
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_chunks_item_kind_seq
            ON inbox_parsed.parsed_item_chunks(parsed_item_id, kind, seq)
            """
        )
    )


def _prepare_artifact(path: str, data: dict) -> Callable[[], None]:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    original = None
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            original = fh.read()
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))

    def _restore() -> None:
        if original is None:
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
        else:
            with open(path, "w", encoding="utf-8") as fh_restore:
                fh_restore.write(original)

    return _restore


@pytest.mark.skipif(
    not RUN_DB_TESTS or not DB_URL,
    reason="requires RUN_DB_TESTS=1 and DATABASE_URL/INBOX_DB_URL",
)
def test_invoice_importer_persists_quality():
    mod = _load_worker()
    run_importer = mod.run_importer

    engine = create_engine(DB_URL, future=True)

    with engine.begin() as conn:
        _ensure_schema_and_tables(conn)
        conn.execute(text("TRUNCATE inbox_parsed.parsed_item_chunks CASCADE"))
        conn.execute(text("TRUNCATE inbox_parsed.parsed_items CASCADE"))

    good_path = "artifacts/inbox_local/samples/invoice_good.json"
    bad_path = "artifacts/inbox_local/samples/invoice_bad.json"
    tenant = "00000000-0000-0000-0000-000000000001"

    good_artifact = {
        "tenant_id": tenant,
        "fingerprints": {"content_hash": "invoice-good-0001"},
        "pipeline": ["pdf.text_extract", "pdf.tables_extract"],
        "mime": "application/pdf",
        "doc_type": "unknown",
        "amount": "199.90",
        "invoice_no": "INV-12345",
        "due_date": "2030-01-31",
        "quality": {"valid": True, "issues": []},
        "flags": {"enable_ocr": False},
        "extracted": {
            "tables": [
                {"headers": ["item", "amount"], "rows": [["service", "199.90"]]},
            ]
        },
        "pii": {"steps": []},
    }
    bad_artifact = {
        "tenant_id": tenant,
        "fingerprints": {"content_hash": "invoice-bad-0001"},
        "pipeline": ["images.ocr"],
        "mime": "image/png",
        "doc_type": "unknown",
        "amount": "",
        "invoice_no": "??",
        "due_date": None,
        "quality": {"valid": False, "issues": ["ocr_warning"]},
        "flags": {"ocr_warning": True},
        "extracted": {"tables": []},
        "pii": {"steps": []},
    }

    restore_good = _prepare_artifact(good_path, good_artifact)
    restore_bad = _prepare_artifact(bad_path, bad_artifact)

    try:
        good_id = run_importer(
            tenant_id=tenant,
            artifact_path=good_path,
            engine=engine,
            replace_chunks=True,
        )

        second_good_id = run_importer(
            tenant_id=tenant,
            artifact_path=good_path,
            engine=engine,
            replace_chunks=True,
        )
        assert second_good_id == good_id

        with engine.begin() as conn:
            row = conn.execute(
                text(
                    "SELECT doctype, quality_status, confidence, rules, amount, invoice_no, due_date "
                    "FROM inbox_parsed.parsed_items WHERE id=:id"
                ),
                {"id": good_id},
            ).fetchone()
            assert row is not None
            assert row.doctype == "invoice"
            assert row.quality_status == "accepted"
            assert float(row.confidence) >= 70.0
            assert row.rules == []
            assert Decimal(str(row.amount)) == Decimal("199.90")
            assert row.invoice_no == "INV-12345"
            assert str(row.due_date)

            chunk_count = conn.execute(
                text(
                    "SELECT COUNT(*) FROM inbox_parsed.parsed_item_chunks WHERE parsed_item_id=:id"
                ),
                {"id": good_id},
            ).scalar_one()
            assert chunk_count == 1

        bad_id = run_importer(
            tenant_id=tenant,
            artifact_path=bad_path,
            engine=engine,
            replace_chunks=True,
        )

        with engine.begin() as conn:
            row = conn.execute(
                text(
                    "SELECT doctype, quality_status, confidence, rules, amount, invoice_no, due_date "
                    "FROM inbox_parsed.parsed_items WHERE id=:id"
                ),
                {"id": bad_id},
            ).fetchone()
            assert row is not None
            assert row.doctype == "unknown"
            assert row.quality_status == "rejected"
            assert float(row.confidence) < 50.0
            assert isinstance(row.rules, list) and row.rules
            assert row.amount is None
            assert row.invoice_no == "??"
            assert row.due_date is None
    finally:
        restore_bad()
        restore_good()
