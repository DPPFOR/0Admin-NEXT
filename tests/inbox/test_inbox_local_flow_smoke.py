from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_flow_runner():
    spec = importlib.util.spec_from_file_location(
        "inbox_local_flow",
        "backend/apps/inbox/orchestration/inbox_local_flow.py",
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    assert spec and spec.loader
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod.run_inbox_local_flow


def test_flow_pdf_happy_path(tmp_path):
    run_inbox_local_flow = _load_flow_runner()
    out = run_inbox_local_flow(
        tenant_id="00000000-0000-0000-0000-000000000001",
        path="artifacts/inbox/samples/pdf/sample.pdf",
        enable_ocr=True,
        enable_browser=False,
    )
    assert Path(out).exists()
    data = Path(out).read_text(encoding="utf-8")
    assert "pdf.text_extract" in data and "data_quality.tables.validate" in data


def test_flow_archive_then_pdf(tmp_path):
    run_inbox_local_flow = _load_flow_runner()
    out = run_inbox_local_flow(
        tenant_id="00000000-0000-0000-0000-000000000001",
        path="artifacts/inbox/samples/archive/sample.zip",
    )
    txt = Path(out).read_text(encoding="utf-8")
    assert "archive.unpack" in txt


def test_flow_unknown_mime_degrades():
    run_inbox_local_flow = _load_flow_runner()
    out = run_inbox_local_flow(
        tenant_id="00000000-0000-0000-0000-000000000001",
        path="artifacts/inbox/samples/images/sample.png",
    )
    txt = Path(out).read_text(encoding="utf-8")
    assert "images.ocr" in txt
