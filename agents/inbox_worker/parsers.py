import json
import re

InvoicePatterns = {
    "invoice_no": re.compile(
        r"\b(Rechnungsnummer|Invoice(?:\s*No\.)?)[:\s]*([A-Z0-9\-/]{4,})", re.I
    ),
    "amount": re.compile(
        r"\b(Betrag|Amount)[:\s]*([0-9]{1,3}(?:[.,][0-9]{3})*(?:[.,][0-9]{2})?)\b"
    ),
    "due_date": re.compile(
        r"\b(Fälligkeit|Due\s*Date)[:\s]*([0-9]{2,4}[./-][0-9]{1,2}[./-][0-9]{2,4})\b", re.I
    ),
}


def _decode_text(data: bytes) -> str:
    try:
        return data.decode("utf-8", errors="ignore")
    except Exception:
        return ""


def parse_text_like(data: bytes) -> dict:
    text = _decode_text(data)
    result = {"doc_type": "unknown"}

    m = InvoicePatterns["invoice_no"].search(text)
    if m:
        result["invoice_no"] = m.group(2)
    m = InvoicePatterns["amount"].search(text)
    if m:
        result["amount"] = m.group(2)
    m = InvoicePatterns["due_date"].search(text)
    if m:
        result["due_date"] = m.group(2)

    return result


def parse_pdf(data: bytes) -> dict:
    # naive text extraction: many PDFs include text as ASCII; otherwise unknown
    result = parse_text_like(data)
    result.setdefault("doc_type", "pdf")
    result["doc_type"] = "pdf"
    return result


def parse_image(data: bytes, kind: str) -> dict:
    # No OCR in v1; fallback unknown fields
    return {"doc_type": kind}


def parse_csv(data: bytes) -> dict:
    text = _decode_text(data)
    lines = text.splitlines()
    header = lines[0].split(",") if lines else []
    result = {"doc_type": "csv", "meta": {"header": header[:10]}}
    # attempt simple field extraction from header or first rows
    text_result = parse_text_like(data)
    result.update({k: v for k, v in text_result.items() if k != "doc_type"})
    return result


def parse_json_doc(data: bytes) -> dict:
    try:
        obj = json.loads(data.decode("utf-8", errors="ignore"))
    except Exception:
        return {"doc_type": "json"}
    res = {"doc_type": "json"}
    for key in ("invoice", "invoice_no", "invoiceId", "invoice_id"):
        if key in obj and isinstance(obj[key], (str, int)):
            res["invoice_no"] = str(obj[key])
            break
    for key in ("amount", "total", "sum"):
        if key in obj:
            res["amount"] = str(obj[key])
            break
    for key in ("due_date", "dueDate"):
        if key in obj:
            res["due_date"] = str(obj[key])
            break
    return res


def parse_xml(data: bytes) -> dict:
    try:
        import xml.etree.ElementTree as ET

        root = ET.fromstring(data)
    except Exception:
        return {"doc_type": "xml"}
    ns = ""
    res = {"doc_type": "xml"}
    # naive search
    for tag in ("invoice", "invoice_no", "InvoiceNo", "InvoiceID"):
        el = root.find(f".//{tag}")
        if el is not None and el.text:
            res["invoice_no"] = el.text.strip()
            break
    for tag in ("amount", "total", "Amount"):
        el = root.find(f".//{tag}")
        if el is not None and el.text:
            res["amount"] = el.text.strip()
            break
    for tag in ("due_date", "DueDate"):
        el = root.find(f".//{tag}")
        if el is not None and el.text:
            res["due_date"] = el.text.strip()
            break
    return res
