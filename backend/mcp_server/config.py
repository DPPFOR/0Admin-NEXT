"""Configuration loader for the 0Admin MCP stdio server."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from pydantic import BaseModel, Field, field_validator


class ToolTimeouts(BaseModel):
    """Timeout configuration per tool (seconds)."""

    default: float = Field(default=60.0, ge=0)
    pdf_text_extract: Optional[float] = Field(default=None, ge=0)
    pdf_table_extract: Optional[float] = Field(default=None, ge=0)
    security_pii_redact: Optional[float] = Field(default=None, ge=0)


class ServerConfig(BaseModel):
    """Resolved server configuration with environment-aware defaults."""

    workspace_root: Path = Field(default_factory=lambda: Path.cwd())
    artifacts_dir: Path = Field(default_factory=lambda: Path("artifacts") / "mcp")
    policy_file: Path = Field(default_factory=lambda: Path("ops") / "mcp" / "policies" / "default-policy.yaml")
    log_level: str = Field(default="INFO")
    allow_unix_socket: bool = Field(default=False)
    timeouts: ToolTimeouts = Field(default_factory=ToolTimeouts)

    @field_validator("log_level")
    @classmethod
    def _normalize_level(cls, value: str) -> str:
        up = value.upper()
        if up not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            return "INFO"
        return up

    @field_validator("artifacts_dir", "policy_file")
    @classmethod
    def _resolve_path(cls, value: Path, info) -> Path:  # type: ignore[override]
        # Field validator has access to raw data through info.data
        workspace = info.data.get("workspace_root", Path.cwd())
        return (workspace / value).resolve()

    @classmethod
    def load(cls, *, base_dir: Path | None = None, config_path: Path | None = None) -> "ServerConfig":
        """Load configuration from YAML file + environment overrides."""

        base = base_dir or Path.cwd()
        config_file = config_path or (base / "mcp.config.yaml")
        if not config_file.is_absolute():
            config_file = (base / config_file).resolve()
        raw: Dict[str, Any] = {}

        if config_file.exists():
            try:
                parsed = yaml.safe_load(config_file.read_text(encoding="utf-8"))
                if isinstance(parsed, dict):
                    raw = parsed
            except Exception:
                raw = {}

        env_overrides: Dict[str, Any] = {}
        from os import getenv

        if artifacts := getenv("ARTIFACTS_DIR"):
            env_overrides["artifacts_dir"] = artifacts
        if policy := getenv("POLICY_FILE"):
            env_overrides["policy_file"] = policy
        if lvl := getenv("LOG_LEVEL"):
            env_overrides["log_level"] = lvl
        if allow_unix := getenv("ALLOW_UNIX_SOCKET"):
            env_overrides["allow_unix_socket"] = allow_unix.lower() in {"1", "true", "yes"}

        merged = {**raw, **env_overrides}
        merged["workspace_root"] = base.resolve()
        # Ensure nested timeouts dict is pydantic-friendly
        timeouts_cfg: Dict[str, Any] = merged.get("timeouts", {}) or {}
        merged["timeouts"] = timeouts_cfg

        return cls.model_validate(merged)

    def ensure_artifact_directory(self) -> Path:
        """Create artifact directory if missing and return its absolute path."""
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        return self.artifacts_dir
