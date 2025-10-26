from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import tools.flows.flock_samples as flock_samples


def _mock_response(payload: dict):
    class _Response:
        def __init__(self, data: dict):
            self._data = json.dumps(data).encode("utf-8")

        def read(self) -> bytes:
            return self._data

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    return _Response(payload)


@pytest.fixture(autouse=True)
def restore_urlopen(monkeypatch):
    def _urlopen(request, timeout=0):
        raise AssertionError("urlopen must be stubbed")

    monkeypatch.setattr(flock_samples.urllib.request, "urlopen", _urlopen)


def test_fetch_invoices_builds_url(monkeypatch):
    recorded = SimpleNamespace(url=None)

    def _fake_urlopen(request, timeout=0):
        recorded.url = request.full_url
        return _mock_response({"data": ["ok"]})

    monkeypatch.setattr(flock_samples.urllib.request, "urlopen", _fake_urlopen)

    result = flock_samples.fetch_invoices(
        "00000000-0000-0000-0000-000000000001", base_url="http://api.local"
    )
    assert recorded.url == (
        "http://api.local/inbox/read/invoices?tenant=00000000-0000-0000-0000-000000000001&limit=5&offset=0"
    )
    assert result == {"data": ["ok"]}


def test_fetch_review_queue(monkeypatch):
    called = {}

    def _fake_urlopen(request, timeout=0):
        called["url"] = request.full_url
        return _mock_response({"items": []})

    monkeypatch.setattr(flock_samples.urllib.request, "urlopen", _fake_urlopen)
    data = flock_samples.fetch_review_queue(
        "00000000-0000-0000-0000-000000000001", base_url="http://api.local"
    )
    assert "review" in called["url"]
    assert data == {"items": []}


def test_main_invokes_fetch(monkeypatch, capsys):
    monkeypatch.setattr(
        flock_samples, "fetch_invoices", lambda tenant, base_url="": {"foo": "bar"}
    )
    monkeypatch.setattr(
        flock_samples, "fetch_review_queue", lambda tenant, base_url="": {"baz": "qux"}
    )
    exit_code = flock_samples.main(
        ["--tenant", "00000000-0000-0000-0000-000000000001", "--base-url", "http://api.local", "--what", "both"]
    )
    captured = capsys.readouterr().out
    assert exit_code == 0
    assert "invoices" in captured
    assert "review" in captured
