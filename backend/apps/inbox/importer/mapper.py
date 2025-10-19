from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Tuple

try:
    from .dto import ParsedItemDTO, ParsedItemChunkDTO  # type: ignore
    from .validators import (  # type: ignore
        parse_amount,
        parse_iso_date,
        validate_invoice_amount,
        validate_invoice_due_date,
        validate_invoice_no,
        validate_table_shape,
        compute_confidence,
        decide_quality_status,
        Rule,
        RuleList,
    )
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
    validate_invoice_amount = validators_mod.validate_invoice_amount
    validate_invoice_due_date = validators_mod.validate_invoice_due_date
    validate_invoice_no = validators_mod.validate_invoice_no
    validate_table_shape = validators_mod.validate_table_shape
    compute_confidence = validators_mod.compute_confidence
    decide_quality_status = validators_mod.decide_quality_status
    Rule = validators_mod.Rule
    RuleList = validators_mod.RuleList


def _make_rule(code: str, message: str, *, level: str = "error") -> Rule:
    return {"code": code, "level": level, "message": message}


def artifact_to_dtos(flow: Dict[str, Any], *, enforce_invoice: bool = True) -> Tuple[ParsedItemDTO, List[ParsedItemChunkDTO]]:
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

    rules: RuleList = []

    amount_rules = validate_invoice_amount(amount)
    due_date_rules = validate_invoice_due_date(due_date)
    invoice_rules = validate_invoice_no(invoice_no if isinstance(invoice_no, str) else invoice_no)
    rules.extend(amount_rules)
    rules.extend(due_date_rules)
    rules.extend(invoice_rules)

    tables = flow.get("extracted", {}).get("tables", [])
    table_rules: RuleList = []
    table_ok = False
    primary_table: Dict[str, Any] | None = None
    if isinstance(tables, list):
        for candidate in tables:
            if isinstance(candidate, dict):
                primary_table = candidate
                break
    if primary_table is not None:
        table_rules = validate_table_shape(primary_table)
        rules.extend(table_rules)
        table_ok = not any(rule["level"] == "error" for rule in table_rules)
    else:
        missing_table_rule = _make_rule("invoice.table.missing", "Invoice table is required")
        rules.append(missing_table_rule)

    required_ok = not any(rule["level"] == "error" for rule in (amount_rules + due_date_rules + invoice_rules))
    amount_valid = amount is not None and not any(rule["code"] == "invoice.amount.invalid" for rule in amount_rules)
    due_date_plausible = due_date is not None and not any(
        rule["code"] == "invoice.due_date.implausible" for rule in due_date_rules
    )
    plausibility_ok = amount_valid and due_date_plausible

    quality = flow.get("quality", {}) if isinstance(flow.get("quality"), dict) else {}
    issues = quality.get("issues") if isinstance(quality.get("issues"), list) else []
    quality_flags: List[str] = [str(flag) for flag in issues]
    if not quality.get("valid", True):
        if "invalid" not in quality_flags:
            quality_flags.append("invalid")

    flags = flow.get("flags", {}) if isinstance(flow.get("flags"), dict) else {}
    has_ocr_warning = any(
        isinstance(flag, str) and flag.lower() == "ocr_warning" for flag in quality_flags
    ) or bool(flags.get("ocr_warning"))

    mime = flow.get("mime", "")
    mime_lower = mime.lower() if isinstance(mime, str) else ""
    pipeline_source_tokens = [step.split(".", 1)[0].lower() for step in pipeline if isinstance(step, str)]
    source_keywords = ("pdf", "office", "word", "excel", "powerpoint")
    mime_keyword_hit = any(keyword in mime_lower for keyword in source_keywords)
    pipeline_keyword_hit = any(
        any(keyword in token for keyword in source_keywords) for token in pipeline_source_tokens
    )
    source_keyword_hit = mime_keyword_hit or pipeline_keyword_hit
    source_ok = source_keyword_hit and not has_ocr_warning

    confidence_score = compute_confidence(
        {
            "required_ok": required_ok,
            "table_ok": table_ok,
            "plausibility_ok": plausibility_ok,
            "source_ok": source_ok,
        }
    )
    confidence = Decimal(confidence_score).quantize(Decimal("0.01"))
    quality_status = decide_quality_status(required_ok, confidence_score)
    doctype = "invoice" if enforce_invoice and required_ok else "unknown"

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
        doctype=doctype,
        quality_status=quality_status,
        confidence=confidence,
        rules=rules,
    )

    chunks: List[ParsedItemChunkDTO] = []
    if isinstance(tables, list):
        seq = 1
        for t in tables:
            if isinstance(t, dict):
                chunks.append(
                    ParsedItemChunkDTO(parsed_item_id="", seq=seq, kind="table", payload=t)
                )
                seq += 1
    return item, chunks
