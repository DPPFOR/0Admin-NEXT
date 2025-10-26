#!/usr/bin/env python3
"""Debug the MCP tool execution directly."""

import sys
from pathlib import Path

# Add to path
sys.path.insert(0, str(Path.cwd()))

from backend.mcp_server.config import ServerConfig
from backend.mcp_server.policy import load_policy
from backend.mcp_server.registry import execute_tool

def main():
    workspace = Path.cwd()
    config = ServerConfig.load(base_dir=workspace)
    policy = load_policy(config.policy_file, workspace_root=config.workspace_root)

    # Test file
    test_file = workspace / "artifacts/tests/mcp/sample_invoice.pdf"
    if not test_file.exists():
        print(f"Test file {test_file} does not exist")
        return

    try:
        result = execute_tool(
            "pdf_text_extract",
            {
                "tenant_id": "00000000-0000-0000-0000-000000000001",
                "trace_id": "debug-trace",
                "path": "artifacts/tests/mcp/sample_invoice.pdf",  # relative path as in test
            },
            config=config,
            policy=policy
        )
        print("SUCCESS:")
        import json
        print(json.dumps(result, indent=2))
    except Exception as e:
        print("ERROR:", e)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
