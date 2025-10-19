"""MCP Fabric application scaffolding (no HTTP/ASGI).

Provides factories to access registry and adapters. No loops/threads.
"""

from __future__ import annotations

from typing import Any, Callable

from . import registry


def get_tool_registry() -> list[dict[str, str]]:
    return registry.list_tools()


# Adapter factories are optional for local-only v1. We expose a simple lookup to
# maintain a consistent entrypoint without importing any network/DB code.
def get_adapter_factory(tool_id: str) -> Callable[..., Any] | None:
    mapping: dict[str, str] = {
        "ops.health_check": "backend.mcp.server.adapters.inbox_read:HealthCheckAdapter",
        "ops.dlq_list": "backend.mcp.server.adapters.inbox_read:DLQListAdapter",
        "ops.outbox_status": "backend.mcp.server.adapters.ops_status:OutboxStatusAdapter",
        "qa.run_smoke": "backend.mcp.server.adapters.qa_smoke:QASmokeAdapter",
        "etl.inbox_extract": "backend.mcp.server.adapters.etl_inbox_extract:ETLInboxExtractAdapter",
        # New domain tools
        "detect.mime": "backend.mcp.server.adapters.detect.mime:DetectMimeAdapter",
        "archive.unpack": "backend.mcp.server.adapters.archive.unpack:ArchiveUnpackAdapter",
        "email.gmail.fetch": "backend.mcp.server.adapters.email.gmail_fetch:GmailFetchAdapter",
        "email.outlook.fetch": "backend.mcp.server.adapters.email.outlook_fetch:OutlookFetchAdapter",
        "office.word.normalize": "backend.mcp.server.adapters.office.word_normalize:WordNormalizeAdapter",
        "office.powerpoint.normalize": "backend.mcp.server.adapters.office.powerpoint_normalize:PowerPointNormalizeAdapter",
        "office.excel.normalize": "backend.mcp.server.adapters.office.excel_normalize:ExcelNormalizeAdapter",
        "pdf.text_extract": "backend.mcp.server.adapters.pdf.text_extract:PdfTextExtractAdapter",
        "pdf.ocr_extract": "backend.mcp.server.adapters.pdf.ocr_extract:PdfOCRExtractAdapter",
        "pdf.tables_extract": "backend.mcp.server.adapters.pdf.tables_extract:PdfTablesExtractAdapter",
        "images.ocr": "backend.mcp.server.adapters.images.ocr:ImagesOCRAdapter",
        "data_quality.tables.validate": "backend.mcp.server.adapters.data_quality.tables_validate:DataQualityTablesValidateAdapter",
        "security.pii.redact": "backend.mcp.server.adapters.security.pii_redact:SecurityPIIRedactAdapter",
    }
    target = mapping.get(tool_id)
    if not target:
        return None
    module_name, class_name = target.split(":", 1)
    mod = __import__(module_name, fromlist=[class_name])
    klass = getattr(mod, class_name)
    return klass
