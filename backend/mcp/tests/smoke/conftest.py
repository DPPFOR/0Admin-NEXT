from __future__ import annotations

import os
import sys
import datetime as _datetime

# Ensure project root on sys.path for importing 'backend'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")))

import pytest


@pytest.fixture(autouse=True)
def freeze_datetime(monkeypatch):
    # Forbid datetime.now/utcnow to enforce determinism
    class _Frozen(_datetime.datetime):
        @classmethod
        def now(cls, tz=None):  # pragma: no cover - guard only
            raise AssertionError("datetime.now is forbidden in tests")

        @classmethod
        def utcnow(cls):  # pragma: no cover - guard only
            raise AssertionError("datetime.utcnow is forbidden in tests")

    monkeypatch.setattr(_datetime, "datetime", _Frozen)
