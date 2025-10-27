from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import parse as urlparse

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.clients.flock_reader.client import (
    FlockClientError,
    FlockClientResponseError,
    FlockReadClient,
)

TENANT = "11111111-1111-1111-1111-111111111111"


class FakeResponse:
    def __init__(self, status: int, payload: Any):
        self.status = status
        self._payload = payload

    def read(self) -> bytes:
        if isinstance(self._payload, bytes):
            return self._payload
        return json.dumps(self._payload).encode("utf-8")

    def getcode(self) -> int:
        return self.status

    def close(self) -> None:
        return None


def _make_http_error(url: str, status: int, payload: str) -> urlerror.HTTPError:
    return urlerror.HTTPError(
        url=url,
        code=status,
        msg=f"http_{status}",
        hdrs=None,
        fp=io.BytesIO(payload.encode("utf-8")),
    )


def test_get_invoices_builds_query_and_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["headers"] = {key.lower(): value for key, value in request.header_items()}
        return FakeResponse(200, {"items": []})

    monkeypatch.setattr("backend.clients.flock_reader.client.urlrequest.urlopen", fake_urlopen)
    client = FlockReadClient(base_url="http://localhost:9000")

    result = client.get_invoices(
        TENANT,
        limit=25,
        offset=5,
        min_conf=80,
        status="accepted",
    )

    assert result["items"] == []
    parsed = urlparse.urlparse(captured["url"])
    assert parsed.path == "/inbox/read/invoices"
    query = urlparse.parse_qs(parsed.query)
    assert query == {"limit": ["25"], "offset": ["5"], "min_conf": ["80"], "status": ["accepted"]}
    assert captured["headers"]["x-tenant-id"] == TENANT
    assert captured["headers"]["accept"] == "application/json"


def test_invalid_tenant_raises_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FlockReadClient()
    with pytest.raises(ValueError):
        client.get_review_queue("not-a-uuid")


def test_retry_on_500(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = []

    def fake_urlopen(request, timeout=None):
        attempts.append(1)
        if len(attempts) < 3:
            raise _make_http_error(request.full_url, 500, "server_sleep")
        return FakeResponse(
            200,
            {
                "items": [
                    {"id": "x", "tenant_id": TENANT, "content_hash": "abc"},
                ],
                "total": 1,
                "limit": 50,
                "offset": 0,
            },
        )

    monkeypatch.setattr("backend.clients.flock_reader.client.urlrequest.urlopen", fake_urlopen)
    monkeypatch.setattr("backend.clients.flock_reader.client.time.sleep", lambda *_: None)

    client = FlockReadClient(max_retries=3)
    result = client.get_invoices(TENANT)

    assert len(attempts) == 3
    assert isinstance(result["items"], list)


def test_raises_on_404(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request, timeout=None):
        raise _make_http_error(request.full_url, 404, "not-found")

    monkeypatch.setattr("backend.clients.flock_reader.client.urlrequest.urlopen", fake_urlopen)

    client = FlockReadClient()
    with pytest.raises(FlockClientResponseError) as exc:
        client.get_summary(TENANT)

    assert exc.value.status_code == 404
    assert exc.value.response_body == b"not-found"


def test_summary_requires_object(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request, timeout=None):
        return FakeResponse(200, [])

    monkeypatch.setattr("backend.clients.flock_reader.client.urlrequest.urlopen", fake_urlopen)
    client = FlockReadClient()

    with pytest.raises(FlockClientError):
        client.get_summary(TENANT)


def test_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request, timeout=None):
        return FakeResponse(200, b"not-json")

    monkeypatch.setattr("backend.clients.flock_reader.client.urlrequest.urlopen", fake_urlopen)
    client = FlockReadClient()

    with pytest.raises(FlockClientError):
        client.get_payments(TENANT)


def test_limit_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FlockReadClient()

    with pytest.raises(ValueError):
        client.get_invoices(TENANT, limit=101)
