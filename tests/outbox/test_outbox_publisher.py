from __future__ import annotations

from uuid import UUID

import pytest

from backend.core.outbox import publisher


def test_enqueue_event_returns_uuid(monkeypatch):
    class DummyConnection:
        def __init__(self):
            self.statements = []

        def execute(self, statement):
            self.statements.append(statement)

    class DummyContext:
        def __init__(self, conn):
            self.conn = conn

        def __enter__(self):
            return self.conn

        def __exit__(self, exc_type, exc, tb):
            return False

    class DummyEngine:
        def __init__(self):
            self.conn = DummyConnection()

        def begin(self):
            return DummyContext(self.conn)

    dummy_engine = DummyEngine()
    publisher._get_engine.cache_clear()
    monkeypatch.setattr(publisher.sa, "create_engine", lambda *args, **kwargs: dummy_engine)

    event_id = publisher.enqueue_event("InboxItemAnalysisReady", {"example": "payload"})

    assert isinstance(event_id, UUID)
    assert dummy_engine.conn.statements, "expected outbox insert to execute"


def test_enqueue_event_requires_json_serializable_payload():
    with pytest.raises(ValueError):
        publisher.enqueue_event("InboxItemAnalysisReady", {"bad": object()})
