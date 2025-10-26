"""MCP tool registry and execution helpers."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple
from uuid import UUID

from mcp import types
from pydantic import BaseModel, Field, ValidationError, field_validator

from .config import ServerConfig
from .logging import tool_log_context
from .policy import Policy, ensure_path_allowed


def _safe_component(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", value)
    return safe[:64] if len(safe) > 64 else safe


def _workspace_relative(path: Path, workspace_root: Path) -> str:
    try:
        return str(path.relative_to(workspace_root))
    except ValueError:
        return str(path)


class TenantContext(BaseModel):
    tenant_id: UUID
    trace_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")


class PdfTextExtractInput(TenantContext):
    path: str = Field(min_length=1)
    ocr_hint: bool = Field(default=False)

    @field_validator("path")
    @classmethod
    def _validate_path(cls, value: str) -> str:
        candidate = value.strip()
        if not candidate.startswith("artifacts/"):
            raise ValueError("paths must start with artifacts/")
        if ".." in candidate.split("/"):
            raise ValueError("path traversal not permitted")
        return candidate


class PdfTextExtractOutput(BaseModel):
    tenant_id: UUID
    trace_id: str
    source_path: str
    text_preview: str
    char_count: int
    checksum_sha256: str
    artifact_path: str


class PdfTableExtractInput(TenantContext):
    path: str = Field(min_length=1)
    table_boost: bool = Field(default=False)

    @field_validator("path")
    @classmethod
    def _validate_path(cls, value: str) -> str:
        candidate = value.strip()
        if not candidate.startswith("artifacts/"):
            raise ValueError("paths must start with artifacts/")
        if ".." in candidate.split("/"):
            raise ValueError("path traversal not permitted")
        return candidate


class ExtractedTable(BaseModel):
    index: int
    row_count: int
    headers: List[str]
    rows: List[List[str]]


class PdfTableExtractOutput(BaseModel):
    tenant_id: UUID
    trace_id: str
    source_path: str
    tables: List[ExtractedTable]
    artifact_path: str


class SecurityPIIRedactInput(TenantContext):
    text: str = Field(min_length=1)
    policy: str = Field(default="default", max_length=32)


class Detection(BaseModel):
    category: str
    start: int
    end: int
    original_length: int


class SecurityPIIRedactOutput(BaseModel):
    tenant_id: UUID
    trace_id: str
    policy: str
    redacted_text: str
    detections: List[Detection]
    artifact_path: str


ExtractorFn = Callable[[dict, ServerConfig, Policy], dict]


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    handler: ExtractorFn


def _extract_pdf_text(source: Path) -> str:
    if not source.exists():
        raise FileNotFoundError(f"File not found: {source}")
    if source.stat().st_size == 0:
        return ""

    try:
        proc = subprocess.run(
            ["pdftotext", str(source), "-"],
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0 and proc.stdout:
            return proc.stdout.strip()
    except FileNotFoundError:
        pass

    raw = source.read_bytes()
    extracted = raw.decode("latin-1", errors="ignore")
    printable = "".join(ch if ch.isprintable() else " " for ch in extracted)
    return re.sub(r"\s+", " ", printable).strip()


def _persist_artifact(config: ServerConfig, tool: str, tenant_id: str, trace_id: str, suffix: str, data: dict) -> Path:
    base = config.ensure_artifact_directory() / tool / _safe_component(tenant_id) / _safe_component(trace_id)
    base.mkdir(parents=True, exist_ok=True)
    target = base / suffix
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def _extract_tables_from_text(text: str) -> List[List[List[str]]]:
    tables: List[List[List[str]]] = []
    current: List[List[str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            if current:
                tables.append(current)
                current = []
            continue
        cells = [cell.strip() for cell in re.split(r"[,\t]| {2,}", stripped) if cell.strip()]
        if len(cells) >= 2:
            current.append(cells)
        else:
            if current:
                tables.append(current)
                current = []
    if current:
        tables.append(current)
    return tables


EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"\b\+?[0-9][0-9\s\-]{6,}[0-9]\b")


def _redact_text(text: str) -> Tuple[str, List[Detection]]:
    detections: List[Detection] = []

    def email_repl(match: re.Match[str]) -> str:
        detections.append(
            Detection(
                category="email",
                start=match.start(),
                end=match.end(),
                original_length=len(match.group(0)),
            )
        )
        return "[REDACTED_EMAIL]"

    def phone_repl(match: re.Match[str]) -> str:
        detections.append(
            Detection(
                category="phone",
                start=match.start(),
                end=match.end(),
                original_length=len(match.group(0)),
            )
        )
        return "[REDACTED_PHONE]"

    intermediate = EMAIL_RE.sub(email_repl, text)
    final_text = PHONE_RE.sub(phone_repl, intermediate)
    return final_text, detections


def _pdf_text_handler(payload: dict, config: ServerConfig, policy: Policy) -> dict:
    args = PdfTextExtractInput.model_validate(payload)
    source = ensure_path_allowed(path=Path(args.path), policy=policy)
    text = _extract_pdf_text(source)
    checksum = sha256(text.encode("utf-8")).hexdigest()
    preview = text[:240]
    output_dict = PdfTextExtractOutput(
        tenant_id=args.tenant_id,
        trace_id=args.trace_id,
        source_path=str(source),
        text_preview=preview,
        char_count=len(text),
        checksum_sha256=checksum,
        artifact_path="",
    ).model_dump(mode="json")

    artifact_data = {"text": text, **output_dict}
    artifact_path = _persist_artifact(
        config,
        "pdf_text_extract",
        str(args.tenant_id),
        args.trace_id,
        "text.json",
        artifact_data,
    )
    output_dict["artifact_path"] = _workspace_relative(artifact_path, config.workspace_root)
    return PdfTextExtractOutput.model_validate(output_dict).model_dump(mode="json")


def _pdf_table_handler(payload: dict, config: ServerConfig, policy: Policy) -> dict:
    args = PdfTableExtractInput.model_validate(payload)
    source = ensure_path_allowed(path=Path(args.path), policy=policy)
    text = _extract_pdf_text(source)
    tables_raw = _extract_tables_from_text(text)
    tables: List[ExtractedTable] = []
    for index, table_rows in enumerate(tables_raw):
        if not table_rows:
            continue
        headers = table_rows[0]
        rows = table_rows[1:] if len(table_rows) > 1 else []
        tables.append(
            ExtractedTable(
                index=index,
                headers=headers,
                rows=rows,
                row_count=len(rows),
            )
        )
    output = PdfTableExtractOutput(
        tenant_id=args.tenant_id,
        trace_id=args.trace_id,
        source_path=str(source),
        tables=tables,
        artifact_path="",
    )
    artifact_path = _persist_artifact(
        config,
        "pdf_table_extract",
        str(args.tenant_id),
        args.trace_id,
        "tables.json",
        output.model_dump(mode="json"),
    )
    data = output.model_dump(mode="json")
    data["artifact_path"] = _workspace_relative(artifact_path, config.workspace_root)
    return PdfTableExtractOutput.model_validate(data).model_dump(mode="json")


def _security_pii_handler(payload: dict, config: ServerConfig, policy: Policy) -> dict:
    args = SecurityPIIRedactInput.model_validate(payload)
    redacted_text, detections = _redact_text(args.text)
    output = SecurityPIIRedactOutput(
        tenant_id=args.tenant_id,
        trace_id=args.trace_id,
        policy=args.policy,
        redacted_text=redacted_text,
        detections=detections,
        artifact_path="",
    )
    artifact_path = _persist_artifact(
        config,
        "security_pii_redact",
        str(args.tenant_id),
        args.trace_id,
        "redaction.json",
        output.model_dump(mode="json"),
    )
    data = output.model_dump(mode="json")
    data["artifact_path"] = _workspace_relative(artifact_path, config.workspace_root)
    return SecurityPIIRedactOutput.model_validate(data).model_dump(mode="json")


REGISTRY: Dict[str, ToolDefinition] = {
    "pdf_text_extract": ToolDefinition(
        name="pdf_text_extract",
        description="Extract plain text from a PDF using local tooling (no OCR).",
        input_model=PdfTextExtractInput,
        output_model=PdfTextExtractOutput,
        handler=_pdf_text_handler,
    ),
    "pdf_table_extract": ToolDefinition(
        name="pdf_table_extract",
        description="Detect simple tabular structures in a PDF text layer.",
        input_model=PdfTableExtractInput,
        output_model=PdfTableExtractOutput,
        handler=_pdf_table_handler,
    ),
    "security_pii_redact": ToolDefinition(
        name="security_pii_redact",
        description="Redact PII (email & phone numbers) from text using deterministic regexes.",
        input_model=SecurityPIIRedactInput,
        output_model=SecurityPIIRedactOutput,
        handler=_security_pii_handler,
    ),
}


def list_tools() -> List[types.Tool]:
    """Return tool definitions as MCP protocol objects."""
    tools: List[types.Tool] = []
    for tool in REGISTRY.values():
        tools.append(
            types.Tool(
                name=tool.name,
                description=tool.description,
                inputSchema=tool.input_model.model_json_schema(),
                outputSchema=tool.output_model.model_json_schema(),
            )
        )
    return tools


def execute_tool(name: str, arguments: dict, *, config: ServerConfig, policy: Policy) -> dict:
    """Execute a tool by name and return JSON-serialisable output."""
    if name not in REGISTRY:
        raise ValueError(f"Unknown tool: {name}")
    tool = REGISTRY[name]

    try:
        validated_args = tool.input_model.model_validate(arguments).model_dump(mode="python")
    except ValidationError as exc:
        raise ValueError(f"Input validation failed: {exc}") from exc

    tenant_id = str(validated_args["tenant_id"])
    trace_id = validated_args["trace_id"]

    with tool_log_context(tool=name, tenant_id=tenant_id, trace_id=trace_id):
        result = tool.handler(validated_args, config, policy)
    try:
        return tool.output_model.model_validate(result).model_dump(mode="json")
    except ValidationError as exc:
        raise ValueError(f"Output validation failed: {exc}") from exc
