from __future__ import annotations

from typing import Any


def _valid_path(p: str) -> bool:
    return p.startswith("artifacts/inbox/") and ".." not in p and not p.startswith("/")


class PdfOCRExtractAdapter:
    @staticmethod
    def describe() -> str:
        return "OCR plan for scanned PDFs (dry run)"

    @staticmethod
    def plan(path: str, tenant_id: str | None = None, dry_run: bool = True) -> dict[str, Any]:
        if not isinstance(path, str) or not _valid_path(path):
            raise ValueError("VALIDATION: invalid path")
        plan = {"steps": [{"op": "ocr", "src": path, "engine": "tesseract"}]}
        return {"plan": plan, "ts": "2025-01-01T00:00:00Z"}
