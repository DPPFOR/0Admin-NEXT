"""Policy loader for MCP Fabric.

Reads YAML from ops/mcp/policies/*.yaml.
Fail-safe defaults when files are missing or empty:
- dry_run_default: true
- allowed_tools: ["ops.health_check"]
- quotas: parsed if present; no enforcement
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - yaml usually present in many repos; not required at runtime
    yaml = None  # type: ignore


DEFAULTS = {
    "dry_run_default": True,
    "allowed_tools": ["ops.health_check"],
    "quotas": {},
}


@dataclass(frozen=True)
class Policy:
    dry_run_default: bool
    allowed_tools: list[str]
    quotas: dict[str, Any]


def _read_yaml(path: str) -> dict[str, Any] | None:
    if not path or not os.path.exists(path):
        return None
    try:
        content = open(path, encoding="utf-8").read()
    except FileNotFoundError:
        return None
    if not content.strip():
        return None
    if yaml is None:
        # If PyYAML is not present, treat as opaque parse failure and fall back to defaults.
        return None
    try:
        data = yaml.safe_load(content)
        if not isinstance(data, dict):
            return None
        return data
    except Exception:
        return None


def load_policy(base_dir: str | None = None) -> Policy:
    base = base_dir or os.path.join("ops", "mcp", "policies")
    default_path = os.path.join(base, "default-policy.yaml")
    quotas_path = os.path.join(base, "quotas.example.yaml")

    cfg = _read_yaml(default_path) or {}
    quotas = _read_yaml(quotas_path) or {}

    dry_run_default = bool(cfg.get("dry_run_default", DEFAULTS["dry_run_default"]))
    allowed_tools = cfg.get("allowed_tools", DEFAULTS["allowed_tools"]) or []
    if not isinstance(allowed_tools, list):
        allowed_tools = []
    allowed_tools = [str(t) for t in allowed_tools]

    quotas_parsed = quotas if isinstance(quotas, dict) else {}

    return Policy(
        dry_run_default=dry_run_default,
        allowed_tools=allowed_tools or DEFAULTS["allowed_tools"],
        quotas=quotas_parsed,
    )
