#!/usr/bin/env python3
from __future__ import annotations

import os
import sys

# Ensure project root on sys.path for direct script execution
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.mcp.server import registry


def get_lines() -> list[str]:
    tools = registry.list_tools()
    # Stable order by id
    tools_sorted = sorted(tools, key=lambda t: t["id"])
    return [f"{t['id']}@{t['version']}" for t in tools_sorted]


def main() -> int:
    for line in get_lines():
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
