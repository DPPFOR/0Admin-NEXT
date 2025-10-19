from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
import importlib.util as _iu
from pathlib import Path


def _load_worker():
    spec = _iu.spec_from_file_location(
        "worker", "backend/apps/inbox/importer/worker.py"
    )
    mod = _iu.module_from_spec(spec)  # type: ignore[arg-type]
    assert spec and spec.loader
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_importer_idempotent_skip(monkeypatch):
    mod = _load_worker()
    artifact_path = "artifacts/inbox_local/samples/sample_result.json"
    data = json.loads(open(artifact_path, "r", encoding="utf-8").read())
    tenant_id = data["tenant_id"]

    def fake(engine, item, chunks, *, upsert, replace_chunks):
        assert upsert is False
        return "pid-1", "skip", 0

    monkeypatch.setattr(mod, "_upsert_parsed_item_with_chunks", fake)
    res = mod.run_importer(tenant_id=tenant_id, artifact_path=artifact_path, upsert=False, engine=object())
    assert res == "pid-1"


def test_importer_idempotent_insert(monkeypatch):
    mod = _load_worker()
    artifact_path = "artifacts/inbox_local/samples/sample_result.json"
    data = json.loads(open(artifact_path, "r", encoding="utf-8").read())
    tenant_id = data["tenant_id"]

    def fake(engine, item, chunks, *, upsert, replace_chunks):
        assert upsert is True
        return "pid-new", "insert", len(chunks)

    monkeypatch.setattr(mod, "_upsert_parsed_item_with_chunks", fake)
    res = mod.run_importer(tenant_id=tenant_id, artifact_path=artifact_path, upsert=True, engine=object())
    assert res == "pid-new"


def test_importer_numeric_and_date_binding(monkeypatch, tmp_path: Path):
    mod = _load_worker()
    artifact = {
        "tenant_id": "00000000-0000-0000-0000-000000000001",
        "trace_id": "trace-xyz",
        "fingerprints": {"content_hash": "abc123"},
        "pipeline": ["pdf.text_extract"],
        "extracted": {"tables": []},
        "quality": {"valid": True, "issues": []},
        "pii": {"steps": []},
        "flags": {},
        "amount": "123.45",
        "invoice_no": "INV-999",
        "due_date": "2025-10-19",
    }
    artifact_path = Path("artifacts/inbox_local/test_amount_import.json")
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")

    calls = []

    def fake(engine, item, chunks, *, upsert, replace_chunks):
        calls.append((upsert, replace_chunks))
        assert item.amount == Decimal("123.45")
        assert item.invoice_no == "INV-999"
        assert item.due_date == date(2025, 10, 19)
        action = "insert" if len(calls) == 1 else "update"
        return "pid-date", action, len(chunks)

    monkeypatch.setattr(mod, "_upsert_parsed_item_with_chunks", fake)

    try:
        res1 = mod.run_importer(
            tenant_id=artifact["tenant_id"],
            artifact_path=str(artifact_path),
            engine=object(),
        )
        assert res1 == "pid-date"

        res2 = mod.run_importer(
            tenant_id=artifact["tenant_id"],
            artifact_path=str(artifact_path),
            engine=object(),
        )
        assert res2 == "pid-date"
    finally:
        if artifact_path.exists():
            artifact_path.unlink()
