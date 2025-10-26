from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Tuple, Optional

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
        payment_DoD,
        other_DoD,
        non_empty_str,
        table_shape_ok,
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
    payment_DoD = validators_mod.payment_DoD
    other_DoD = validators_mod.other_DoD
    non_empty_str = validators_mod.non_empty_str
    table_shape_ok = validators_mod.table_shape_ok


def _make_rule(code: str, message: str, *, level: str = "error") -> Rule:
    return {"code": code, "level": level, "message": message}


def _collect_tables(extracted: Dict[str, Any]) -> List[Dict[str, Any]]:
    tables = extracted.get("tables")
    result: List[Dict[str, Any]] = []
    if isinstance(tables, list):
        for table in tables:
            if isinstance(table, dict):
                result.append(table)
    return result


def _collect_kv(extracted: Dict[str, Any]) -> List[Dict[str, Any]]:
    kv_entries = extracted.get("kv")
    result: List[Dict[str, Any]] = []
    if isinstance(kv_entries, list):
        for entry in kv_entries:
            if isinstance(entry, dict):
                result.append(
                    {
                        "key": entry.get("key"),
                        "value": entry.get("value"),
                    }
                )
    return result


def _quality_flags(flow: Dict[str, Any]) -> List[str]:
    quality = flow.get("quality")
    if not isinstance(quality, dict):
        return []
    issues = quality.get("issues")
    flags = [str(flag) for flag in issues] if isinstance(issues, list) else []
    if not quality.get("valid", True) and "invalid" not in flags:
        flags.append("invalid")
    return flags


def _base_payload(flow: Dict[str, Any]) -> Dict[str, Any]:
    extracted_src = flow.get("extracted")
    extracted_payload = dict(extracted_src) if isinstance(extracted_src, dict) else {}
    return {
        "pipeline": flow.get("pipeline", []),
        "mime": flow.get("mime"),
        "extracted": extracted_payload,
        "quality": flow.get("quality", {}),
        "pii": flow.get("pii", {}),
        "flags": flow.get("flags", {}),
    }


def _build_chunks(
    tables: List[Dict[str, Any]],
    kv_entries: List[Dict[str, Any]],
) -> List[ParsedItemChunkDTO]:
    chunks: List[ParsedItemChunkDTO] = []
    seq = 1
    for table in tables:
        chunks.append(ParsedItemChunkDTO(parsed_item_id="", seq=seq, kind="table", payload=table))
        seq += 1
    if kv_entries:
        chunks.append(
            ParsedItemChunkDTO(parsed_item_id="", seq=seq, kind="kv", payload={"entries": kv_entries})
        )
    return chunks


def _pipeline_tokens(pipeline: Any) -> List[str]:
    tokens: List[str] = []
    if isinstance(pipeline, list):
        for step in pipeline:
            if isinstance(step, str) and step:
                tokens.append(step.lower())
    return tokens


def _should_classify_payment(
    flow: Dict[str, Any],
    pipeline_tokens: List[str],
    kv_entries: List[Dict[str, Any]],
    payment_block: Dict[str, Any],
) -> bool:
    doc_type = flow.get("doc_type")
    if isinstance(doc_type, str) and "payment" in doc_type.lower():
        return True

    filename = flow.get("fingerprints", {}).get("source_name")
    hints: List[str] = []
    if isinstance(filename, str):
        hints.append(filename.lower())
    hints.extend(pipeline_tokens)
    for entry in kv_entries:
        key = entry.get("key")
        if isinstance(key, str):
            hints.append(key.lower())

    payment_keywords = ("payment", "iban", "bic", "bank", "sepa", "transfer")
    if any(any(keyword in hint for keyword in payment_keywords) for hint in hints):
        return True

    if isinstance(payment_block, dict) and any(payment_block.values()):
        return True

    return False


def _normalize_currency(currency: Optional[str]) -> Optional[str]:
    if not currency:
        return None
    candidate = non_empty_str(currency)
    if not candidate:
        return None
    return candidate.upper()


def _safe_parse_amount(raw_amount: Any) -> Tuple[Optional[Decimal], RuleList]:
    if raw_amount in (None, ""):
        return None, []
    try:
        return parse_amount(str(raw_amount)), []
    except ValueError:
        return None, [_make_rule("payment.amount.parse_error", "Unable to parse payment amount")]


def _safe_parse_date(raw_date: Any) -> Tuple[Optional[date], RuleList]:
    if raw_date in (None, ""):
        return None, []
    if isinstance(raw_date, date):
        return raw_date, []
    try:
        return parse_iso_date(str(raw_date)), []
    except ValueError:
        return None, [_make_rule("payment.date.parse_error", "Unable to parse payment date")]


def _map_payment(
    flow: Dict[str, Any],
    *,
    tenant_id: str,
    content_hash: str,
    doc_type: str,
    tables: List[Dict[str, Any]],
    kv_entries: List[Dict[str, Any]],
    flags: Dict[str, Any],
    mvr_preview: bool,
    mvr_score: Optional[Decimal],
) -> Tuple[ParsedItemDTO, List[ParsedItemChunkDTO]]:
    extracted = flow.get("extracted")
    payment_block = {}
    if isinstance(extracted, dict):
        candidate = extracted.get("payment")
        if isinstance(candidate, dict):
            payment_block = dict(candidate)

    amount_raw = payment_block.get("amount") if payment_block else flow.get("amount")
    currency_raw = payment_block.get("currency") if payment_block else flow.get("currency")
    date_raw = payment_block.get("payment_date") if payment_block else flow.get("payment_date")
    counterparty_raw = payment_block.get("counterparty") if payment_block else flow.get("counterparty")

    amount, amount_rules = _safe_parse_amount(amount_raw)
    payment_date, date_rules = _safe_parse_date(date_raw)
    currency_norm = _normalize_currency(currency_raw)
    counterparty_norm = non_empty_str(counterparty_raw)

    confidence, dod_rules, quality_status = payment_DoD(
        amount=amount,
        currency=currency_norm,
        payment_date=payment_date,
        counterparty=counterparty_norm,
    )

    rules: RuleList = amount_rules + date_rules + dod_rules

    payload = _base_payload(flow)
    extracted_payload = payload.setdefault("extracted", {})
    payment_payload = dict(payment_block)
    payment_payload.setdefault("amount", str(amount) if amount is not None else None)
    payment_payload["currency"] = currency_norm
    payment_payload["payment_date"] = payment_date.isoformat() if payment_date else None
    payment_payload["counterparty"] = counterparty_norm
    extracted_payload["payment"] = payment_payload

    quality_flags = _quality_flags(flow)

    chunks = _build_chunks(tables, kv_entries)

    item = ParsedItemDTO(
        tenant_id=tenant_id,
        content_hash=content_hash,
        doc_type=doc_type or "payment",
        payload=payload,
        amount=amount,
        invoice_no=None,
        due_date=payment_date,
        quality_flags=quality_flags,
        doctype="payment",
        quality_status=quality_status,
        confidence=confidence,
        rules=rules,
        flags=flags,
        mvr_preview=mvr_preview,
        mvr_score=mvr_score,
    )

    return item, chunks


def _map_other(
    flow: Dict[str, Any],
    *,
    tenant_id: str,
    content_hash: str,
    doc_type: str,
    tables: List[Dict[str, Any]],
    kv_entries: List[Dict[str, Any]],
    flags: Dict[str, Any],
    mvr_preview: bool,
    mvr_score: Optional[Decimal],
) -> Tuple[ParsedItemDTO, List[ParsedItemChunkDTO]]:
    payload = _base_payload(flow)
    confidence, dod_rules, quality_status = other_DoD(kv_entries=kv_entries, tables=tables)
    quality_flags = _quality_flags(flow)
    chunks = _build_chunks(tables, kv_entries)

    item = ParsedItemDTO(
        tenant_id=tenant_id,
        content_hash=content_hash,
        doc_type=doc_type or "other",
        payload=payload,
        amount=None,
        invoice_no=None,
        due_date=None,
        quality_flags=quality_flags,
        doctype="other",
        quality_status=quality_status,
        confidence=confidence,
        rules=dod_rules,
        flags=flags,
        mvr_preview=mvr_preview,
        mvr_score=mvr_score,
    )

    return item, chunks


def _map_invoice(
    flow: Dict[str, Any],
    *,
    tenant_id: str,
    content_hash: str,
    doc_type: str,
    pipeline: List[str],
    tables: List[Dict[str, Any]],
    kv_entries: List[Dict[str, Any]],
    enforce_invoice: bool,
    flags: Dict[str, Any],
    mvr_preview: bool,
    mvr_score: Optional[Decimal],
) -> Tuple[ParsedItemDTO, List[ParsedItemChunkDTO], Dict[str, Any]]:
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

    table_rules: RuleList = []
    table_ok = False
    primary_table: Dict[str, Any] | None = tables[0] if tables else None
    if primary_table is not None:
        table_rules = validate_table_shape(primary_table)
        rules.extend(table_rules)
        table_ok = not any(rule["level"] == "error" for rule in table_rules)
    else:
        rules.append(_make_rule("invoice.table.missing", "Invoice table is required"))

    required_ok = not any(rule["level"] == "error" for rule in (amount_rules + due_date_rules + invoice_rules))
    amount_valid = amount is not None and not any(rule["code"] == "invoice.amount.invalid" for rule in amount_rules)
    due_date_plausible = due_date is not None and not any(
        rule["code"] == "invoice.due_date.implausible" for rule in due_date_rules
    )
    plausibility_ok = amount_valid and due_date_plausible

    quality_flags = _quality_flags(flow)

    has_ocr_warning = any(
        isinstance(flag, str) and flag.lower() == "ocr_warning" for flag in quality_flags
    ) or bool(flags.get("ocr_warning"))

    mime = flow.get("mime", "")
    mime_lower = mime.lower() if isinstance(mime, str) else ""
    source_keywords = ("pdf", "office", "word", "excel", "powerpoint")
    mime_keyword_hit = any(keyword in mime_lower for keyword in source_keywords)
    pipeline_keyword_hit = any(any(keyword in token for keyword in source_keywords) for token in pipeline)
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

    payload = _base_payload(flow)

    chunks = _build_chunks(tables, kv_entries)

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
        flags=flags,
        mvr_preview=mvr_preview,
        mvr_score=mvr_score,
    )

    ctx = {
        "doctype": doctype,
        "required_ok": required_ok,
        "structured": bool(tables),
        "quality_status": quality_status,
    }
    return item, chunks, ctx


def artifact_to_dtos(
    flow: Dict[str, Any],
    *,
    enforce_invoice: bool = True,
    enforce_payment: bool = True,
    enforce_other: bool = True,
) -> Tuple[ParsedItemDTO, List[ParsedItemChunkDTO]]:
    tenant_id = flow.get("tenant_id", "")
    content_hash = flow.get("fingerprints", {}).get("content_hash", "")
    pipeline = flow.get("pipeline", [])
    pipeline_tokens = _pipeline_tokens(pipeline)

    raw_doc_type = flow.get("doc_type")
    doc_type = raw_doc_type if isinstance(raw_doc_type, str) and raw_doc_type else "unknown"
    if doc_type == "unknown" and isinstance(pipeline, list):
        for step in pipeline:
            if isinstance(step, str) and step:
                doc_type = step.split(".", 1)[0]
                break

    extracted = flow.get("extracted")
    extracted_dict: Dict[str, Any] = dict(extracted) if isinstance(extracted, dict) else {}
    tables = _collect_tables(extracted_dict)
    kv_entries = _collect_kv(extracted_dict)
    payment_block = extracted_dict.get("payment") if isinstance(extracted_dict.get("payment"), dict) else {}
    flags_map: Dict[str, Any] = dict(flow.get("flags") or {}) if isinstance(flow.get("flags"), dict) else {}
    mvr_preview_flag = bool(flags_map.get("mvr_preview"))
    mvr_score: Optional[Decimal] = Decimal("0.00") if mvr_preview_flag else None

    if enforce_payment and _should_classify_payment(flow, pipeline_tokens, kv_entries, payment_block):
        return _map_payment(
            flow,
            tenant_id=tenant_id,
            content_hash=content_hash,
            doc_type=doc_type or "payment",
            tables=tables,
            kv_entries=kv_entries,
            flags=flags_map,
            mvr_preview=mvr_preview_flag,
            mvr_score=mvr_score,
        )

    item, chunks, ctx = _map_invoice(
        flow,
        tenant_id=tenant_id,
        content_hash=content_hash,
        doc_type=doc_type,
        pipeline=pipeline_tokens,
        tables=tables,
        kv_entries=kv_entries,
        enforce_invoice=enforce_invoice,
        flags=flags_map,
        mvr_preview=mvr_preview_flag,
        mvr_score=mvr_score,
    )

    structured = bool(tables or kv_entries)
    if enforce_other and ctx.get("doctype") != "invoice" and structured:
        return _map_other(
            flow,
            tenant_id=tenant_id,
            content_hash=content_hash,
            doc_type=doc_type,
            tables=tables,
            kv_entries=kv_entries,
            flags=flags_map,
            mvr_preview=mvr_preview_flag,
            mvr_score=mvr_score,
        )

    return item, chunks
