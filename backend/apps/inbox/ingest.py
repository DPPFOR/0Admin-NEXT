import ipaddress
import socket
import time
from urllib.parse import urljoin, urlparse

import httpx
import idna

from backend.core.config import settings

from .utils import detect_mime


class IngestError(Exception):
    code: str
    http_status: int

    def __init__(self, code: str, http_status: int, msg: str = ""):
        super().__init__(msg or code)
        self.code = code
        self.http_status = http_status


def _parse_domains(csv: str) -> list[str]:
    return [d.strip().lower() for d in csv.split(",") if d.strip()]


def _is_forbidden_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
        return (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_multicast
            or addr.is_reserved
            or addr.is_unspecified
        )
    except ValueError:
        return True


def _resolve_host_ips(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
        ips = []
        for family, _, _, _, sockaddr in infos:
            ip = sockaddr[0]
            ips.append(ip)
        return list(sorted(set(ips)))
    except Exception:
        return []


def _normalize_host(host: str) -> str:
    try:
        return idna.encode(host.strip().lower()).decode("ascii")
    except Exception:
        return host.strip().lower()


def _check_host_allowed(host: str) -> None:
    host_lc = _normalize_host(host)
    # Denylist check
    for d in _parse_domains(settings.INGEST_URL_DENYLIST):
        if host_lc == d or host_lc.endswith("." + d):
            raise IngestError("forbidden_address", 403, "Host is denied by policy")

    # Allowlist check
    allow = _parse_domains(settings.INGEST_URL_ALLOWLIST)
    if allow:
        if not any(host_lc == d or host_lc.endswith("." + d) for d in allow):
            raise IngestError("forbidden_address", 403, "Host not in allowlist")

    # DNS resolution and IP classification
    ips = _resolve_host_ips(host_lc)
    if not ips:
        raise IngestError("io_error", 502, "DNS resolution failed")
    for ip in ips:
        if _is_forbidden_ip(ip):
            raise IngestError("forbidden_address", 403, "Resolved to forbidden address")


def ensure_url_allowed(url: str) -> None:
    p = urlparse(url)
    if p.scheme.lower() != "https":
        raise IngestError("unsupported_scheme", 400, "HTTPS required")
    if not p.netloc:
        raise IngestError("io_error", 502, "Malformed URL")
    _check_host_allowed(p.hostname or "")


def _http_fetch(url: str) -> tuple[bytes, str | None]:
    """Fetch remote resource securely with redirects and timeouts.

    Returns: (content_bytes, filename)
    May raise IngestError with codes per spec.
    """
    connect_to = settings.INGEST_TIMEOUT_CONNECT_MS / 1000.0
    read_to = settings.INGEST_TIMEOUT_READ_MS / 1000.0
    redirect_limit = settings.INGEST_REDIRECT_LIMIT

    timeout = httpx.Timeout(connect=connect_to, read=read_to)
    # Enforce certificate verification (verify=True) and default SNI handling
    client = httpx.Client(follow_redirects=False, timeout=timeout, verify=True)

    try:
        redirects = 0
        current = url
        filename = None
        while True:
            ensure_url_allowed(current)
            # HEAD to check Content-Length
            try:
                head = client.head(current)
            except httpx.TimeoutException:
                raise IngestError("remote_timeout", 504, "HEAD timeout")

            cl = head.headers.get("Content-Length")
            if cl:
                try:
                    size = int(cl)
                    if size > settings.MAX_UPLOAD_MB * 1024 * 1024:
                        raise IngestError("size_limit", 400, "Payload exceeds size limit")
                except ValueError:
                    pass

            # GET with hard cap; do not forward incoming headers (no Authorization/Cookies)
            try:
                resp = client.get(current)
            except httpx.TimeoutException:
                raise IngestError("remote_timeout", 504, "GET timeout")

            # Handle redirects manually
            if resp.status_code in (301, 302, 303, 307, 308):
                redirects += 1
                if redirects > redirect_limit:
                    raise IngestError("redirect_limit", 400, "Too many redirects")
                loc = resp.headers.get("Location")
                if not loc:
                    raise IngestError("io_error", 502, "Redirect without Location")
                current = urljoin(current, loc)
                # After redirect, ensure target is allowed (host & IP)
                continue

            if resp.status_code >= 400:
                raise IngestError("io_error", 502, f"Remote error: {resp.status_code}")

            # Infer filename from Content-Disposition or URL path
            cd = resp.headers.get("Content-Disposition")
            if cd and "filename=" in cd:
                try:
                    filename = cd.split("filename=", 1)[1].strip('"')
                except Exception:
                    filename = None
            if not filename:
                path = urlparse(current).path or ""
                filename = path.rsplit("/", 1)[-1] if "/" in path else path

            # Read with cap
            max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
            content = resp.content
            if len(content) > max_bytes:
                raise IngestError("size_limit", 400, "Downloaded payload exceeds size limit")

            return content, filename
    finally:
        try:
            client.close()
        except Exception:
            pass


def fetch_remote(url: str) -> tuple[bytes, str | None, str | None, float]:
    """Fetch remote resource and return content, filename, detected_mime, fetch_duration_ms."""
    t0 = time.time()
    content, filename = _http_fetch(url)
    mime = detect_mime(content)
    duration_ms = (time.time() - t0) * 1000.0
    return content, filename, mime, duration_ms
