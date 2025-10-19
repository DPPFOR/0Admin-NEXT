import hashlib
import io
from typing import Optional


def sha256_hex(data: bytes) -> str:
    """Compute SHA-256 hex lowercase of raw bytes."""
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def detect_mime(data: bytes) -> Optional[str]:
    """Server-side MIME detection based on magic numbers/content heuristics.

    Allowlist includes:
    - application/pdf
    - image/png
    - image/jpeg
    - text/csv
    - application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
    - application/json
    - application/xml
    """
    # PDF
    if data.startswith(b"%PDF-"):
        return "application/pdf"

    # PNG
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"

    # JPEG (SOI marker) with common JFIF/Exif headers
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"

    # XLSX (ZIP with [Content_Types].xml)
    if data[:4] == b"PK\x03\x04" and b"[Content_Types].xml" in data[:4096]:
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    # JSON (first non-ws char is { or [)
    stripped = data.lstrip()
    if stripped[:1] in (b"{", b"["):
        # naive JSON heuristic; further validation omitted
        return "application/json"

    # XML (common prefixes: <?xml or <tag)
    if stripped.startswith(b"<?xml") or stripped.startswith(b"<"):
        return "application/xml"

    # CSV (simple heuristic: ASCII, contains commas and newlines)
    try:
        text_prefix = stripped[:1024].decode("utf-8")
        if "," in text_prefix and "\n" in text_prefix:
            return "text/csv"
    except UnicodeDecodeError:
        pass

    return None


def extension_for_mime(mime: str) -> str:
    """Return a suitable file extension (with dot) for a given MIME type."""
    mapping = {
        "application/pdf": ".pdf",
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "text/csv": ".csv",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
        "application/json": ".json",
        "application/xml": ".xml",
    }
    return mapping.get(mime, "")

