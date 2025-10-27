from __future__ import annotations

import datetime as _datetime
import os
import sys

import pytest

# Ensure project root on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))


@pytest.fixture(autouse=True)
def freeze_datetime(monkeypatch):
    class _Frozen(_datetime.datetime):
        @classmethod
        def now(cls, tz=None):  # pragma: no cover - guard only
            raise AssertionError("datetime.now is forbidden in tests")

        @classmethod
        def utcnow(cls):  # pragma: no cover - guard only
            raise AssertionError("datetime.utcnow is forbidden in tests")

    monkeypatch.setattr(_datetime, "datetime", _Frozen)


@pytest.fixture(autouse=True)
def block_egress(monkeypatch):
    import asyncio
    import http.client
    import os as _os
    import socket
    import ssl
    import subprocess
    import urllib.request

    _original_socket = socket.socket

    def _guarded_socket(family=socket.AF_INET, type=socket.SOCK_STREAM, proto=0, fileno=None):
        if family == socket.AF_UNIX:
            return _original_socket(family, type, proto, fileno)
        raise RuntimeError("egress blocked")

    def _blocked(*args, **kwargs):  # pragma: no cover - guard
        raise RuntimeError("egress blocked")

    monkeypatch.setattr(socket, "socket", _guarded_socket)
    monkeypatch.setattr(socket, "create_connection", _blocked)
    for name in ("Popen", "call", "check_call", "check_output", "run"):
        monkeypatch.setattr(subprocess, name, _blocked)
    monkeypatch.setattr(_os, "system", _blocked)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _blocked)
    monkeypatch.setattr(urllib.request, "urlopen", _blocked)
    monkeypatch.setattr(http.client, "HTTPConnection", _blocked)
    monkeypatch.setattr(http.client, "HTTPSConnection", _blocked)
    monkeypatch.setattr(ssl, "create_default_context", _blocked)
