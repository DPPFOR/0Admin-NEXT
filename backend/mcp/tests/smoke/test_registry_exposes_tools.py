from __future__ import annotations

from backend.mcp.server import registry
from tools.mcp import list_tools as cli


def test_registry_contains_expected_domain_tools():
    tools = registry.list_tools()
    ids = [t["id"] for t in tools]
    expected = {
        "archive.unpack",
        "data_quality.tables.validate",
        "detect.mime",
        "email.gmail.fetch",
        "email.outlook.fetch",
        "images.ocr",
        "office.excel.normalize",
        "office.powerpoint.normalize",
        "office.word.normalize",
        "pdf.ocr_extract",
        "pdf.tables_extract",
        "pdf.text_extract",
    }
    assert expected.issubset(set(ids))
    assert all(t["version"] == "1.0.0" for t in tools)


def test_cli_list_tools_matches_registry_flat(capsys):
    exit_code = cli.main([])
    assert exit_code == 0
    out = capsys.readouterr().out.strip().splitlines()
    expected = [f"{t['id']}@{t['version']}" for t in registry.list_tools()]
    assert out == expected


def test_cli_tree_and_json_outputs(capsys):
    # tree
    assert cli.main(["--tree"]) == 0
    tree_out = capsys.readouterr().out.strip().splitlines()
    assert any(line.startswith("office (") for line in tree_out)
    # json flat
    assert cli.main(["--json"]) == 0
    flat_json = capsys.readouterr().out
    assert '"tools"' in flat_json
    # json tree
    assert cli.main(["--tree", "--json"]) == 0
    tree_json = capsys.readouterr().out
    assert '"groups"' in tree_json
