from __future__ import annotations

from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from backend.mcp.server.adapters.images.ocr import ImagesOCRAdapter


def _schema(path: str):
    import json

    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_images_ocr_positive():
    schema = _schema("backend/mcp/contracts/images.ocr/1.0.0/output.json")
    out = ImagesOCRAdapter.plan(path="artifacts/inbox/samples/images/sample.png", dry_run=True)
    Draft202012Validator(schema).validate(out)


def test_images_ocr_negative():
    with pytest.raises(ValueError):
        ImagesOCRAdapter.plan(path="/etc/passwd", dry_run=True)
