from __future__ import annotations

import json
import os
import time
from contextlib import closing
from typing import Any, Dict, Optional, Type
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest
from uuid import UUID

from .dto import InvoiceDTO, PaymentDTO, ReviewItemDTO, SummaryDTO

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_TIMEOUT = 5.0
DEFAULT_MAX_RETRIES = 3
MAX_LIMIT = 100
VALID_STATUSES = {"accepted", "needs_review", "rejected"}


class FlockClientError(RuntimeError):
    """Raised when the Flock read client cannot complete a request."""


class FlockClientResponseError(FlockClientError):
    """Raised when the Flock read client receives an unexpected HTTP response."""

    def __init__(self, status_code: int, message: str, response_body: Optional[bytes] = None):
        super().__init__(f"http_{status_code}: {message}")
        self.status_code = status_code
        self.response_body = response_body or b""


class FlockReadClient:
    """Synchronous HTTP client for the Flock read-only API."""

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_factor: float = 0.5,
    ) -> None:
        env_base = os.getenv("READ_API_BASE_URL")
        selected_base = base_url or env_base or DEFAULT_BASE_URL
        self.base_url = selected_base.rstrip("/")
        self.timeout = timeout
        self.max_retries = max(1, int(max_retries))
        self.backoff_factor = float(backoff_factor)

    def get_invoices(
        self,
        tenant_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
        min_conf: Optional[int] = None,
        status: Optional[str] = None,
    ) -> Any:
        params = self._build_pagination_params(limit, offset)
        if min_conf is not None:
            if not isinstance(min_conf, int):
                raise ValueError("min_conf must be an integer between 0 and 100")
            if not 0 <= min_conf <= 100:
                raise ValueError("min_conf must be between 0 and 100")
            params["min_conf"] = min_conf
        if status is not None:
            if status not in VALID_STATUSES:
                raise ValueError(f"status must be one of {sorted(VALID_STATUSES)}")
            params["status"] = status
        data = self._request("/inbox/read/invoices", tenant_id, params)
        return self._as_list(data, InvoiceDTO)

    def get_payments(
        self,
        tenant_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
        min_conf: Optional[int] = None,
        status: Optional[str] = None,
    ) -> Any:
        params = self._build_pagination_params(limit, offset)
        if min_conf is not None:
            if not isinstance(min_conf, int):
                raise ValueError("min_conf must be an integer between 0 and 100")
            if not 0 <= min_conf <= 100:
                raise ValueError("min_conf must be between 0 and 100")
            params["min_conf"] = min_conf
        if status is not None:
            if status not in VALID_STATUSES:
                raise ValueError(f"status must be one of {sorted(VALID_STATUSES)}")
            params["status"] = status
        data = self._request("/inbox/read/payments", tenant_id, params)
        return self._as_list(data, PaymentDTO)

    def get_review_queue(
        self,
        tenant_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> Any:
        params = self._build_pagination_params(limit, offset)
        data = self._request("/inbox/read/review", tenant_id, params)
        return self._as_list(data, ReviewItemDTO)

    def get_summary(self, tenant_id: str) -> Any:
        data = self._request("/inbox/read/summary", tenant_id, {})
        if not isinstance(data, dict):
            raise FlockClientError("summary response must be a JSON object")
        return SummaryDTO.from_json(data).to_json()

    def _build_pagination_params(self, limit: int, offset: int) -> Dict[str, int]:
        if not isinstance(limit, int) or not isinstance(offset, int):
            raise ValueError("limit and offset must be integers")
        if limit < 0 or offset < 0:
            raise ValueError("limit and offset must be non-negative")
        if limit > MAX_LIMIT:
            raise ValueError(f"limit must be <= {MAX_LIMIT}")
        return {"limit": limit, "offset": offset}

    def _request(self, path: str, tenant_id: str, params: Dict[str, Any]) -> Any:
        self._validate_tenant(tenant_id)
        url = self._build_url(path, params)
        headers = {
            "Accept": "application/json",
            "X-Tenant-ID": tenant_id,
        }
        request = urlrequest.Request(url, headers=headers, method="GET")
        attempt = 0

        while attempt < self.max_retries:
            try:
                response = urlrequest.urlopen(request, timeout=self.timeout)
            except urlerror.HTTPError as exc:
                body = exc.read() if hasattr(exc, "read") else b""
                if self._should_retry(exc.code) and self._has_attempts_remaining(attempt):
                    self._sleep(attempt)
                    attempt += 1
                    continue
                message = self._derive_error_message(body, exc.reason)
                raise FlockClientResponseError(exc.code, message, body) from None
            except urlerror.URLError as exc:
                raise FlockClientError(str(exc.reason or exc)) from exc

            with closing(response) as resp:
                status_code = getattr(resp, "status", resp.getcode())
                body_bytes = resp.read()
                if status_code >= 400:
                    if self._should_retry(status_code) and self._has_attempts_remaining(attempt):
                        self._sleep(attempt)
                        attempt += 1
                        continue
                    message = self._derive_error_message(body_bytes, None)
                    raise FlockClientResponseError(status_code, message, body_bytes)
                return self._parse_json(body_bytes)

        raise FlockClientError("max retries exceeded")

    def _has_attempts_remaining(self, attempt: int) -> bool:
        return attempt + 1 < self.max_retries

    def _should_retry(self, status_code: Optional[int]) -> bool:
        if status_code is None:
            return False
        if status_code == 429:
            return True
        return status_code >= 500

    def _sleep(self, attempt: int) -> None:
        delay = self.backoff_factor * (2 ** attempt)
        time.sleep(delay)

    def _build_url(self, path: str, params: Dict[str, Any]) -> str:
        base = self.base_url.rstrip("/") + "/"
        path_fragment = path.lstrip("/")
        url = urlparse.urljoin(base, path_fragment)
        query_params = {key: value for key, value in params.items() if value is not None}
        if query_params:
            query = urlparse.urlencode(query_params)
            return f"{url}?{query}"
        return url

    def _parse_json(self, body: bytes) -> Any:
        if not body:
            return None
        try:
            return json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise FlockClientError("invalid JSON response") from exc

    def _as_list(self, payload: Any, dto_type: Type) -> Any:
        if payload is None:
            return {"items": [], "total": 0, "limit": 0, "offset": 0}
        if isinstance(payload, list):
            items = [dto_type.from_json(item).to_json() for item in payload]
            return {"items": items, "total": len(items), "limit": len(items), "offset": 0}
        if not isinstance(payload, dict):
            raise FlockClientError("expected list response")
        items_payload = payload.get("items", [])
        if not isinstance(items_payload, list):
            raise FlockClientError("expected 'items' to be a list")
        converted_items = [dto_type.from_json(item).to_json() for item in items_payload]
        result = {**payload}
        result["items"] = converted_items
        result.setdefault("total", len(converted_items))
        result.setdefault("limit", len(converted_items))
        result.setdefault("offset", 0)
        return result

    def _validate_tenant(self, tenant_id: str) -> None:
        try:
            UUID(str(tenant_id))
        except (ValueError, TypeError) as exc:
            raise ValueError("tenant_id must be a valid UUID string") from exc

    def _derive_error_message(self, body: bytes, reason: Optional[str]) -> str:
        text = body.decode("utf-8", "ignore").strip()
        if text:
            return text
        if isinstance(reason, str) and reason:
            return reason
        return "http_error"
