from __future__ import annotations

from backend.mcp.server import registry
from tools.mcp import list_tools as cli


def test_registry_has_five_tools():
    tools = sorted(registry.list_tools(), key=lambda t: t["id"])
    assert len(tools) == 5
    expected_ids = [
        "etl.inbox_extract",
        "ops.dlq_list",
        "ops.health_check",
        "ops.outbox_status",
        "qa.run_smoke",
    ]
    assert [t["id"] for t in tools] == expected_ids
    assert all(t["version"] == "1.0.0" for t in tools)


def test_cli_list_tools_matches_registry(capsys):
    exit_code = cli.main()
    assert exit_code == 0
    out = capsys.readouterr().out.strip().splitlines()
    expected = [f"{t['id']}@{t['version']}" for t in sorted(registry.list_tools(), key=lambda x: x["id"])]
    assert out == expected

