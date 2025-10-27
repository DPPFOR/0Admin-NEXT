from backend.core.config import settings

from .parsers import (
    parse_csv,
    parse_image,
    parse_json_doc,
    parse_pdf,
    parse_text_like,
    parse_xml,
)


def route_mime_to_doc_type(mime: str) -> str:
    mapping = {
        "application/pdf": "pdf",
        "image/png": "png",
        "image/jpeg": "jpg",
        "text/csv": "csv",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
        "application/json": "json",
        "application/xml": "xml",
    }
    return mapping.get(mime, "unknown")


def parse_content(mime: str, data: bytes) -> dict:
    if len(data) > settings.PARSER_MAX_BYTES:
        raise ValueError("validation_error: parser max bytes exceeded")
    doc = route_mime_to_doc_type(mime)
    if doc == "pdf":
        return parse_pdf(data)
    if doc in ("png", "jpg"):
        return parse_image(data, doc)
    if doc == "csv":
        return parse_csv(data)
    if doc == "json":
        return parse_json_doc(data)
    if doc == "xml":
        return parse_xml(data)
    # unknown: attempt text parse for heuristics but keep doc_type unknown
    res = parse_text_like(data)
    res["doc_type"] = "unknown"
    return res


def maybe_chunk(text: str) -> tuple[bool, dict[int, str]]:
    threshold = settings.PARSER_CHUNK_THRESHOLD_BYTES
    if not text or len(text.encode("utf-8")) <= threshold:
        return False, {}
    # simple fixed-size chunking by bytes
    encoded = text.encode("utf-8")
    chunks: dict[int, str] = {}
    seq = 1
    for i in range(0, len(encoded), threshold):
        chunk = encoded[i : i + threshold]
        chunks[seq] = chunk.decode("utf-8", errors="ignore")
        seq += 1
    return True, chunks
