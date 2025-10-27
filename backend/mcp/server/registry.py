"""Static tool registry for MCP Fabric (read-only, local-only).

Exports a side-effect-free list of tools with IDs and versions.
"""

from __future__ import annotations

TOOLS: list[dict[str, str]] = [
    # Existing ops/qa/etl
    {"id": "ops.health_check", "version": "1.0.0"},
    {"id": "ops.outbox_status", "version": "1.0.0"},
    {"id": "ops.dlq_list", "version": "1.0.0"},
    {"id": "qa.run_smoke", "version": "1.0.0"},
    {"id": "etl.inbox_extract", "version": "1.0.0"},
    # New domain tools (12)
    {"id": "archive.unpack", "version": "1.0.0"},
    {"id": "data_quality.tables.validate", "version": "1.0.0"},
    {"id": "detect.mime", "version": "1.0.0"},
    {"id": "email.gmail.fetch", "version": "1.0.0"},
    {"id": "email.outlook.fetch", "version": "1.0.0"},
    {"id": "images.ocr", "version": "1.0.0"},
    {"id": "office.excel.normalize", "version": "1.0.0"},
    {"id": "office.powerpoint.normalize", "version": "1.0.0"},
    {"id": "office.word.normalize", "version": "1.0.0"},
    {"id": "pdf.ocr_extract", "version": "1.0.0"},
    {"id": "pdf.tables_extract", "version": "1.0.0"},
    {"id": "pdf.text_extract", "version": "1.0.0"},
    {"id": "security.pii.redact", "version": "1.0.0"},
]


def list_tools() -> list[dict[str, str]]:
    # Return tools sorted by id for deterministic outputs
    return sorted(TOOLS, key=lambda t: t["id"]).copy()
