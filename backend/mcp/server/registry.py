"""Static tool registry for MCP Fabric (read-only, local-only).

Exports a side-effect-free list of tools with IDs and versions.
"""

from __future__ import annotations

TOOLS: list[dict[str, str]] = [
    {"id": "ops.health_check", "version": "1.0.0"},
    {"id": "ops.outbox_status", "version": "1.0.0"},
    {"id": "ops.dlq_list", "version": "1.0.0"},
    {"id": "qa.run_smoke", "version": "1.0.0"},
    {"id": "etl.inbox_extract", "version": "1.0.0"},
]

def list_tools() -> list[dict[str, str]]:
    return TOOLS.copy()

