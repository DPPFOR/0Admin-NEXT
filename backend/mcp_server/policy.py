"""Policy loading and egress guard enforcement."""

from __future__ import annotations

import socket
from collections.abc import Iterable
from dataclasses import dataclass
from http.client import HTTPConnection, HTTPSConnection
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Policy:
    """Parsed policy values relevant for the MCP server."""

    workspace_root: Path
    allow_unix_socket: bool
    filesystem_allowlist: list[Path]


def _read_policy(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return {}


def load_policy(policy_path: Path, *, workspace_root: Path) -> Policy:
    """Load policy file and normalise relative allowlist entries."""
    data = _read_policy(policy_path)
    egress = data.get("egress", {}) if isinstance(data.get("egress"), dict) else {}
    allow_unix_socket = bool(egress.get("allow_unix_socket", False))

    allow_entries: Iterable[str] = egress.get("filesystem_allowlist", []) or []
    normalised: list[Path] = []
    for entry in allow_entries:
        try:
            p = Path(entry)
        except TypeError:
            continue
        resolved = (workspace_root / p).resolve()
        if resolved.is_relative_to(workspace_root):
            normalised.append(resolved)
    if not normalised:
        # Default to allowing the artifacts directory inside workspace
        normalised.append((workspace_root / "artifacts").resolve())

    return Policy(
        workspace_root=workspace_root,
        allow_unix_socket=allow_unix_socket,
        filesystem_allowlist=normalised,
    )


class EgressGuard:
    """Simple runtime patches to prevent outbound network calls."""

    def __init__(self, *, allow_unix_socket: bool) -> None:
        self.allow_unix_socket = allow_unix_socket
        self._installed = False
        self._orig_socket_class = None
        self._orig_create_connection = None
        self._orig_http_connect = None
        self._orig_https_connect = None

    def install(self) -> None:
        if self._installed:
            return

        self._patch_socket()
        self._patch_http_client()
        self._installed = True

    def restore(self) -> None:
        if not self._installed:
            return
        if self._orig_socket_class is not None:
            socket.socket = self._orig_socket_class  # type: ignore[assignment]
        if self._orig_create_connection is not None:
            socket.create_connection = self._orig_create_connection  # type: ignore[assignment]
        if self._orig_http_connect is not None:
            HTTPConnection.connect = self._orig_http_connect  # type: ignore[assignment]
        if self._orig_https_connect is not None:
            HTTPSConnection.connect = self._orig_https_connect  # type: ignore[assignment]
        self._installed = False

    def _patch_socket(self) -> None:
        original_socket = socket.socket
        original_create_connection = socket.create_connection
        guard = self

        class GuardedSocket(original_socket):  # type: ignore
            def connect(self, address):
                if isinstance(address, str):
                    if guard.allow_unix_socket:
                        return super().connect(address)
                    raise PermissionError("Egress denied: UNIX sockets disabled by policy")
                raise PermissionError("Egress denied by policy")

        def guarded_create_connection(*args, **kwargs):
            raise PermissionError("Egress denied by policy")

        socket.socket = GuardedSocket  # type: ignore[assignment]
        socket.create_connection = guarded_create_connection  # type: ignore[assignment]
        self._orig_socket_class = original_socket
        self._orig_create_connection = original_create_connection

    def _patch_http_client(self) -> None:
        original_http = HTTPConnection.connect
        original_https = HTTPSConnection.connect

        def _deny(self):  # type: ignore[override]
            raise PermissionError("Egress denied by policy")

        HTTPConnection.connect = _deny  # type: ignore[assignment]
        HTTPSConnection.connect = _deny  # type: ignore[assignment]
        self._orig_http_connect = original_http
        self._orig_https_connect = original_https


def ensure_path_allowed(*, path: Path, policy: Policy) -> Path:
    """Validate that a path stays inside the workspace and allowed directories."""
    resolved = (
        (policy.workspace_root / path).resolve() if not path.is_absolute() else path.resolve()
    )
    if not resolved.is_relative_to(policy.workspace_root):
        raise PermissionError("Path escapes workspace boundaries")

    if not any(resolved.is_relative_to(allowed) for allowed in policy.filesystem_allowlist):
        raise PermissionError("Path not allowed by filesystem policy")

    return resolved
