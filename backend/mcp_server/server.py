"""Stdio MCP server exposing local tooling to VS Code."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import anyio
from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from .config import ServerConfig
from .logging import configure_logging
from .policy import EgressGuard, load_policy
from .registry import execute_tool, list_tools

SERVER_NAME = "0admin-local"
SERVER_VERSION = "1.0.0"
INSTRUCTIONS = "0Admin local MCP tools (read-only)."


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="0Admin MCP stdio server")
    parser.add_argument(
        "--config", help="Optional path to mcp.config.yaml", default="mcp.config.yaml"
    )
    parser.add_argument("--version", action="store_true", help="Print server version and exit")
    return parser.parse_args(argv)


def _resolve_timeout(config: ServerConfig, tool_name: str) -> float:
    timeouts = config.timeouts
    specific = getattr(timeouts, tool_name, None)
    if specific is not None:
        return float(specific)
    return float(timeouts.default)


async def _run_server(config: ServerConfig) -> None:
    server = Server(name=SERVER_NAME, version=SERVER_VERSION, instructions=INSTRUCTIONS)
    tools_cache = list_tools()
    policy = load_policy(config.policy_file, workspace_root=config.workspace_root)
    guard = EgressGuard(allow_unix_socket=config.allow_unix_socket or policy.allow_unix_socket)
    guard.install()

    @server.list_tools()
    async def _handle_list_tools(_req: types.ListToolsRequest | None = None):
        return types.ListToolsResult(tools=tools_cache)

    @server.call_tool()
    async def _handle_call_tool(tool_name: str, arguments: dict[str, Any]):
        from functools import partial

        try:
            func = partial(execute_tool, tool_name, arguments, config=config, policy=policy)
            result = await anyio.to_thread.run_sync(func)
        except Exception as exc:
            raise ValueError(f"Tool {tool_name} failed: {exc}") from exc
        return result

    init_options = server.create_initialization_options()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            init_options,
            raise_exceptions=True,
        )


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    if args.version:
        print(f"{SERVER_NAME} {SERVER_VERSION}")
        return

    config_path = Path(args.config) if args.config else None
    config = ServerConfig.load(base_dir=Path.cwd(), config_path=config_path)
    logger = configure_logging(config.log_level)
    logger.info(
        "server.startup",
        extra={
            "event": {
                "workspace_root": str(config.workspace_root),
                "artifacts_dir": str(config.artifacts_dir),
                "policy_file": str(config.policy_file),
            }
        },
    )

    try:
        anyio.run(_run_server, config)
    except KeyboardInterrupt:
        return
    except Exception as exc:  # pragma: no cover - propagate error to stderr for CLI
        print(f"Server failed: {exc}", file=sys.stderr)
        raise
