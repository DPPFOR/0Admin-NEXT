from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, Tuple
from urllib.parse import urlparse

import httpx

from backend.core.config import settings


@dataclass
class PublishResult:
    ok: bool
    status_code: int
    error: str | None = None


class StdoutTransport:
    name = "stdout"

    def publish(self, tenant_id: str, event_type: str, payload_json: str, trace_id: str | None = None) -> PublishResult:
        # Print JSON line for audit; avoid raw payload logs externally (we log only minimal audit line)
        print(json.dumps({
            "tenant_id": tenant_id,
            "event_type": event_type,
            "trace_id": trace_id,
            "transport": self.name,
        }))
        return PublishResult(ok=True, status_code=0)


class WebhookTransport:
    name = "webhook"

    def __init__(self) -> None:
        self.url = settings.WEBHOOK_URL
        self.timeout = httpx.Timeout(connect=settings.WEBHOOK_TIMEOUT_MS / 1000.0, read=settings.WEBHOOK_TIMEOUT_MS / 1000.0)
        self.success_codes = self._parse_success_codes(settings.WEBHOOK_SUCCESS_CODES)
        self.headers = self._sanitize_headers(self._parse_headers(settings.WEBHOOK_HEADERS_ALLOWLIST))
        self.client = httpx.Client(timeout=self.timeout, verify=True, follow_redirects=False)
        self.domain_allow = [d.strip().lower() for d in (settings.WEBHOOK_DOMAIN_ALLOWLIST or "").split(",") if d.strip()]

    @staticmethod
    def _parse_success_codes(spec: str) -> set[int]:
        result: set[int] = set()
        for token in (spec or "").split(","):
            token = token.strip()
            if not token:
                continue
            if "-" in token:
                a, b = token.split("-", 1)
                try:
                    lo, hi = int(a), int(b)
                    for c in range(lo, hi + 1):
                        result.add(c)
                except ValueError:
                    continue
            else:
                try:
                    result.add(int(token))
                except ValueError:
                    continue
        if not result:
            result = set(range(200, 300))
        return result

    @staticmethod
    def _parse_headers(csv: str) -> Dict[str, str]:
        hdrs: Dict[str, str] = {}
        for pair in (csv or "").split(","):
            pair = pair.strip()
            if not pair:
                continue
            if "=" in pair:
                k, v = pair.split("=", 1)
                hdrs[k.strip()] = v.strip()
        return hdrs

    def _host_allowed(self, host: str) -> bool:
        if not self.domain_allow:
            return True
        host_l = (host or "").lower()
        for d in self.domain_allow:
            if host_l == d or host_l.endswith("." + d):
                return True
        return False

    @staticmethod
    def _sanitize_headers(h: Dict[str, str]) -> Dict[str, str]:
        forbidden = {"authorization", "cookie", "set-cookie"}
        return {k: v for k, v in h.items() if k.lower() not in forbidden}

    def publish(self, tenant_id: str, event_type: str, payload_json: str, trace_id: str | None = None) -> PublishResult:
        # Validate URL
        p = urlparse(self.url)
        if p.scheme.lower() != "https":
            return PublishResult(ok=False, status_code=0, error="unsupported_scheme")
        if not self._host_allowed(p.hostname or ""):
            return PublishResult(ok=False, status_code=0, error="forbidden_address")
        try:
            resp = self.client.post(self.url, headers=self.headers, content=payload_json.encode("utf-8"))
            ok = resp.status_code in self.success_codes
            return PublishResult(ok=ok, status_code=resp.status_code, error=None if ok else f"http_{resp.status_code}")
        except httpx.TimeoutException:
            return PublishResult(ok=False, status_code=0, error="timeout")
        except Exception as e:
            return PublishResult(ok=False, status_code=0, error=str(e))
