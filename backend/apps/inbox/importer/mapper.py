from __future__ import annotations

from typing import Any, Dict, List, Tuple

try:
    from .dto import ParsedItemDTO, ParsedItemChunkDTO  # type: ignore
    from .validators import parse_amount, parse_iso_date  # type: ignore
except Exception:
    import importlib.util as _iu, os as _os
    import sys as _sys

    base_dir = _os.path.dirname(__file__)

    def _load(name: str):
        spec = _iu.spec_from_file_location(name, _os.path.join(base_dir, f"{name}.py"))
        mod = _iu.module_from_spec(spec)  # type: ignore[arg-type]
        assert spec and spec.loader
        _sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod

    dto_mod = _load("dto")
    validators_mod = _load("validators")
    ParsedItemDTO = dto_mod.ParsedItemDTO
    ParsedItemChunkDTO = dto_mod.ParsedItemChunkDTO
    parse_amount = validators_mod.parse_amount
    parse_iso_date = validators_mod.parse_iso_date


def artifact_to_dtos(flow: Dict[str, Any]) -> Tuple[ParsedItemDTO, List[ParsedItemChunkDTO]]:
    tenant_id = flow.get("tenant_id", "")
    content_hash = flow.get("fingerprints", {}).get("content_hash", "")
    pipeline = flow.get("pipeline", [])

    doc_type = flow.get("doc_type") or "unknown"
    if doc_type == "unknown" and isinstance(pipeline, list):
        for step in pipeline:
            if isinstance(step, str) and step:
                doc_type = step.split(".", 1)[0]
                break

    amount = parse_amount(flow.get("amount"))
    invoice_no = flow.get("invoice_no")
    due_date = parse_iso_date(flow.get("due_date"))

    quality = flow.get("quality", {}) if isinstance(flow.get("quality"), dict) else {}
    issues = quality.get("issues") if isinstance(quality.get("issues"), list) else []
    quality_flags: List[str] = [str(flag) for flag in issues]
    if not quality.get("valid", True):
        if "invalid" not in quality_flags:
            quality_flags.append("invalid")

    # Compact payload: include selected keys
    payload = {
        "pipeline": pipeline,
        "mime": flow.get("mime"),
        "extracted": flow.get("extracted", {}),
        "quality": flow.get("quality", {}),
        "pii": flow.get("pii", {}),
        "flags": flow.get("flags", {}),
    }

    item = ParsedItemDTO(
        tenant_id=tenant_id,
        content_hash=content_hash,
        doc_type=doc_type,
        payload=payload,
        amount=amount,
        invoice_no=invoice_no,
        due_date=due_date,
        quality_flags=quality_flags,
    )

    chunks: List[ParsedItemChunkDTO] = []
    tables = flow.get("extracted", {}).get("tables", [])
    if isinstance(tables, list):
        seq = 1
        for t in tables:
            if isinstance(t, dict):
                chunks.append(
                    ParsedItemChunkDTO(parsed_item_id="", seq=seq, kind="table", payload=t)
                )
                seq += 1
    return item, chunks
