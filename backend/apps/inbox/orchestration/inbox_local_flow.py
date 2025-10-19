from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from backend.mcp.server import app as mcp_app


FROZEN_TS = "2025-01-01T00:00:00Z"


def _valid_path(p: str) -> bool:
    return isinstance(p, str) and p.startswith("artifacts/inbox/") and ".." not in p and not p.startswith("/")


def _policy_fingerprint() -> str:
    policy_path = os.path.join("ops", "mcp", "policies", "default-policy.yaml")
    if os.path.exists(policy_path) and open(policy_path, "r", encoding="utf-8").read().strip():
        content = open(policy_path, "r", encoding="utf-8").read().encode("utf-8")
    else:
        content = b"dry_run_default:true\nallowed_tools:[ops.health_check]\n"
    return hashlib.sha256(content).hexdigest()


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _ext(path: str) -> str:
    return os.path.splitext(path)[1].lower()


def _classify_tool_for_path(path: str, enable_ocr: bool) -> Tuple[str, List[str]]:
    e = _ext(path)
    pipeline: List[str] = []
    if e in {".zip", ".7z"}:
        pipeline.append("archive.unpack")
    if e in {".docx"}:
        pipeline.append("office.word.normalize")
    elif e in {".pptx"}:
        pipeline.append("office.powerpoint.normalize")
    elif e in {".xlsx", ".xlsb"}:
        pipeline.append("office.excel.normalize")
    elif e in {".png", ".jpg", ".jpeg"}:
        pipeline.append("images.ocr")
    elif e in {".pdf"}:
        pipeline.append("pdf.text_extract")
        if enable_ocr:
            pipeline.append("pdf.ocr_extract")
        pipeline.append("pdf.tables_extract")
    # downstream common steps
    pipeline.append("data_quality.tables.validate")
    pipeline.append("security.pii.redact")
    return ("application/octet-stream", pipeline)


def _call_adapter(tool_id: str, **kwargs: Any) -> Dict[str, Any]:
    cls = mcp_app.get_adapter_factory(tool_id)
    if cls is None:
        raise ValueError(f"adapter not found: {tool_id}")
    if hasattr(cls, "plan"):
        return cls.plan(**kwargs)  # type: ignore[attr-defined]
    raise ValueError(f"adapter has no plan(): {tool_id}")


def run_inbox_local_flow(
    *,
    tenant_id: str,
    path: str,
    trace_id: Optional[str] = None,
    enable_ocr: bool = False,
    enable_browser: bool = False,
) -> str:
    if not _valid_path(path):
        raise ValueError("VALIDATION: invalid path")

    # Detect MIME (stub)
    detect = _call_adapter("detect.mime", paths=[path], tenant_id=tenant_id, dry_run=True)
    mime, pipeline = _classify_tool_for_path(path, enable_ocr=enable_ocr)

    executed: List[str] = ["detect.mime"]
    extracted: Dict[str, Any] = {}

    # Optional unpack
    if pipeline and pipeline[0] == "archive.unpack":
        _ = _call_adapter("archive.unpack", path=path, tenant_id=tenant_id, dry_run=True)
        executed.append("archive.unpack")

    # Route by pipeline
    for step in pipeline:
        if step == "office.word.normalize":
            out = _call_adapter(step, path=path, tenant_id=tenant_id, dry_run=True)
            executed.append(step)
            extracted.setdefault("artifacts", out.get("report", {}).get("artifacts", []))
        elif step == "office.powerpoint.normalize":
            out = _call_adapter(step, path=path, tenant_id=tenant_id, dry_run=True)
            executed.append(step)
        elif step == "office.excel.normalize":
            out = _call_adapter(step, path=path, tenant_id=tenant_id, dry_run=True)
            executed.append(step)
            extracted.setdefault("sheets", out.get("report", {}).get("sheets", []))
        elif step == "images.ocr":
            out = _call_adapter(step, path=path, tenant_id=tenant_id, dry_run=True)
            executed.append(step)
            extracted.setdefault("image_text", out.get("report", {}).get("text", ""))
        elif step == "pdf.text_extract":
            out = _call_adapter(step, path=path, tenant_id=tenant_id, dry_run=True)
            executed.append(step)
            extracted.setdefault("text_bytes", out.get("report", {}).get("text_bytes", 0))
        elif step == "pdf.ocr_extract":
            out = _call_adapter(step, path=path, tenant_id=tenant_id, dry_run=True)
            executed.append(step)
            extracted.setdefault("ocr", {"planned": True})
        elif step == "pdf.tables_extract":
            out = _call_adapter(step, path=path, tenant_id=tenant_id, dry_run=True)
            executed.append(step)
            extracted.setdefault("tables", out.get("report", {}).get("tables", []))
        elif step == "data_quality.tables.validate":
            dq = _call_adapter(step, paths=[path], tenant_id=tenant_id, dry_run=True)
            executed.append(step)
            quality = dq.get("report", {})
        elif step == "security.pii.redact":
            pii = _call_adapter(step, paths=[path], tenant_id=tenant_id, dry_run=True)
            executed.append(step)
            pii_plan = pii.get("plan", {})
        else:
            # unknown step
            continue

    flow_result: Dict[str, Any] = {
        "tenant_id": tenant_id,
        "trace_id": trace_id,
        "source_path": path,
        "ts": FROZEN_TS,
        "mime": mime,
        "pipeline": executed,
        "extracted": extracted,
        "quality": quality if 'quality' in locals() else {"valid": True, "issues": []},
        "pii": pii_plan if 'pii_plan' in locals() else {"steps": []},
        "fingerprints": {"content_hash": _sha256_hex(path)},
        "policy_fingerprint": _policy_fingerprint(),
        "flags": {"enable_ocr": enable_ocr, "enable_browser": enable_browser},
    }

    # Persist to artifacts
    out_dir = os.path.join("artifacts", "inbox_local")
    os.makedirs(out_dir, exist_ok=True)
    out_name = f"{FROZEN_TS}_{flow_result['fingerprints']['content_hash']}_result.json"
    out_path = os.path.join(out_dir, out_name)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(flow_result, f, ensure_ascii=False, indent=2)
    return out_path

