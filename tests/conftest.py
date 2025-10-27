import inspect
import json
import os
import socket
import warnings
from pathlib import Path

import httpx
import pytest


VIOLATIONS = []
ARTIFACTS_DIR = Path("artifacts")
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
REPORT = ARTIFACTS_DIR / "egress-violations.json"

warnings.filterwarnings(
    "ignore",
    message="Please use `import python_multipart` instead.",
    category=PendingDeprecationWarning,
)


def _is_allowed_callstack(allowed_paths: list[str]) -> bool:
    for frame in inspect.stack():
        filename = (frame.filename or "").replace("\\", "/")
        for ap in allowed_paths:
            if ap in filename:
                return True
    return False


@pytest.fixture(autouse=True, scope="session")
def egress_guard():
    allowed_client_paths = [
        "/tests/",
        "/backend/apps/inbox/ingest.py",
        "/agents/outbox_publisher/transports.py",
    ]

    # Allow DB host/port as exception
    db_url = os.environ.get("DATABASE_URL", "")
    db_host = None
    db_port = None
    try:
        if "@" in db_url:
            # naive parse
            after_at = db_url.split("@", 1)[1]
            hostport = after_at.split("/", 1)[0]
            if ":" in hostport:
                db_host, port = hostport.split(":", 1)
                db_port = int(port)
            else:
                db_host = hostport
                db_port = 5432
    except Exception:
        pass

    real_getaddrinfo = socket.getaddrinfo
    real_create_connection = socket.create_connection
    real_httpx_init = httpx.Client.__init__

    def guard_getaddrinfo(host, *args, **kwargs):
        if db_host and isinstance(host, str) and host == db_host:
            return real_getaddrinfo(host, *args, **kwargs)
        if _is_allowed_callstack(allowed_client_paths):
            return real_getaddrinfo(host, *args, **kwargs)
        VIOLATIONS.append({"fn": "getaddrinfo", "host": str(host)})
        raise RuntimeError("Egress blocked: getaddrinfo disallowed")

    def guard_create_connection(address, *args, **kwargs):
        host, port = None, None
        try:
            if isinstance(address, tuple):
                host, port = address[0], int(address[1])
        except Exception:
            pass
        if (db_host and host == db_host) or (db_port and port == db_port) or (port == 5432):
            return real_create_connection(address, *args, **kwargs)
        if _is_allowed_callstack(allowed_client_paths):
            return real_create_connection(address, *args, **kwargs)
        VIOLATIONS.append({"fn": "create_connection", "address": str(address)})
        raise RuntimeError("Egress blocked: create_connection disallowed")

    def guard_httpx_init(self, *args, **kwargs):
        if not _is_allowed_callstack(allowed_client_paths):
            VIOLATIONS.append({"fn": "httpx.Client.__init__"})
            raise RuntimeError("Egress blocked: httpx.Client not allowed from this callsite")
        return real_httpx_init(self, *args, **kwargs)

    socket.getaddrinfo = guard_getaddrinfo  # type: ignore[assignment]
    socket.create_connection = guard_create_connection  # type: ignore[assignment]
    httpx.Client.__init__ = guard_httpx_init  # type: ignore[assignment]

    yield

    # Restore
    socket.getaddrinfo = real_getaddrinfo  # type: ignore[assignment]
    socket.create_connection = real_create_connection  # type: ignore[assignment]
    httpx.Client.__init__ = real_httpx_init  # type: ignore[assignment]

    REPORT.write_text(json.dumps(VIOLATIONS, indent=2))
