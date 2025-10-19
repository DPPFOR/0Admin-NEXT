#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict

# Ensure project root on sys.path for direct script execution
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.mcp.server import registry


def get_flat() -> list[str]:
    tools = registry.list_tools()
    return [f"{t['id']}@{t['version']}" for t in tools]


def get_tree() -> dict[str, list[str]]:
    groups: dict[str, list[str]] = defaultdict(list)
    for item in get_flat():
        tool_id = item.split("@", 1)[0]
        ns = tool_id.split(".", 1)[0]
        groups[ns].append(item)
    # sort each group
    return {k: sorted(v) for k, v in sorted(groups.items(), key=lambda kv: kv[0])}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="List MCP tools")
    parser.add_argument("--tree", action="store_true", help="Show tree view grouped by namespace")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args(argv)

    flat = get_flat()
    if args.json and args.tree:
        print(json.dumps({"groups": get_tree()}, ensure_ascii=False))
    elif args.json:
        print(json.dumps({"tools": flat}, ensure_ascii=False))
    elif args.tree:
        groups = get_tree()
        for ns, items in groups.items():
            print(f"{ns} ({len(items)})")
            for it in items:
                print(f"  - {it}")
    else:
        for line in flat:
            print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
