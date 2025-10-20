from __future__ import annotations

import json
import socket
from pathlib import Path
from uuid import UUID

import anyio
import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from backend.mcp_server.policy import EgressGuard


WORKSPACE = Path(__file__).resolve().parents[2]
TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
TRACE_ID = "offline-smoke-trace"


PDF_SAMPLE_TEXT = """\
Invoice Number: INV-42
Description        Quantity    Price
Widget A           2           10.00
Widget B           1           4.50
Total              3           14.50
"""


@pytest.fixture(scope="session")
def sample_pdf_path() -> str:
    target_dir = WORKSPACE / "artifacts" / "tests" / "mcp"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / "sample_invoice.pdf"
    target_file.write_text(PDF_SAMPLE_TEXT, encoding="utf-8")
    return str(target_file.relative_to(WORKSPACE))


def _server_parameters() -> StdioServerParameters:
    python_bin = WORKSPACE / ".venv" / "bin" / "python"
    return StdioServerParameters(
        command=str(python_bin),
        args=["-m", "backend.mcp_server"],
        env={
            "PYTHONPATH": str(WORKSPACE),
            "POLICY_FILE": str(WORKSPACE / "ops" / "mcp" / "policies" / "default-policy.yaml"),
            "ARTIFACTS_DIR": str(WORKSPACE / "artifacts" / "mcp"),
            "LOG_LEVEL": "INFO",
        },
        cwd=WORKSPACE,
    )


@pytest.mark.anyio
async def test_mcp_tools_run_offline(sample_pdf_path: str) -> None:
    pdf_path = sample_pdf_path
    async with stdio_client(_server_parameters()) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            initialize = await session.initialize()
            assert initialize.serverInfo.name == "0admin-local"

            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            assert {"pdf_text_extract", "pdf_table_extract", "security_pii_redact"} <= names

            pdf_text_result = await session.call_tool(
                "pdf_text_extract",
                {
                    "tenant_id": str(TENANT_ID),
                    "trace_id": TRACE_ID,
                    "path": pdf_path,
                },
            )
            assert pdf_text_result.structuredContent is not None
            text_payload = pdf_text_result.structuredContent
            assert text_payload["char_count"] > 0
            assert "artifact_path" in text_payload
            artifact = WORKSPACE / text_payload["artifact_path"]
            assert artifact.exists()
            stored = json.loads(artifact.read_text(encoding="utf-8"))
            assert stored["checksum_sha256"] == text_payload["checksum_sha256"]

            pdf_table_result = await session.call_tool(
                "pdf_table_extract",
                {
                    "tenant_id": str(TENANT_ID),
                    "trace_id": TRACE_ID,
                    "path": pdf_path,
                },
            )
            tables = pdf_table_result.structuredContent["tables"]
            assert isinstance(tables, list)
            if tables:
                assert "row_count" in tables[0]
                assert isinstance(tables[0]["row_count"], int)
                assert tables[0]["row_count"] >= 0

            pii_result = await session.call_tool(
                "security_pii_redact",
                {
                    "tenant_id": str(TENANT_ID),
                    "trace_id": TRACE_ID,
                    "text": "Contact us via demo@example.com or +49 30 1234567",
                    "policy": "default",
                },
            )
            redaction = pii_result.structuredContent
            assert "[REDACTED_EMAIL]" in redaction["redacted_text"]
            assert any(d["category"] == "email" for d in redaction["detections"])


def test_egress_guard_blocks_network() -> None:
    guard = EgressGuard(allow_unix_socket=False)
    guard.install()
    try:
        with pytest.raises(PermissionError):
            socket.create_connection(("example.com", 80), timeout=0.1)
    finally:
        guard.restore()
