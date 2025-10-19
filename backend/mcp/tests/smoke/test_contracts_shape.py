from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator


SCHEMA_URL = "https://json-schema.org/draft/2020-12/schema"
ALLOWED_ERRORS = {"VALIDATION", "NOT_FOUND", "UPSTREAM", "POLICY_DENIED", "RETRYABLE_IO"}
ALLOWED_REFS = {"#/$defs/uuid", "#/$defs/base64", "#/$defs/rfc3339", "#/$defs/iso_duration"}


def load_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def test_all_contracts_schemas_and_changelogs_present():
    base = Path("backend/mcp/contracts")
    assert base.exists(), "contracts base missing"
    found = 0
    for tool_dir in base.iterdir():
        if not tool_dir.is_dir():
            continue
        for ver_dir in tool_dir.iterdir():
            if not ver_dir.is_dir():
                continue
            version = ver_dir.name
            # semver strict
            assert version.count(".") == 2 and all(part.isdigit() for part in version.split(".")), f"bad semver: {version}"
            input_p = ver_dir / "input.json"
            output_p = ver_dir / "output.json"
            errors_p = ver_dir / "errors.json"
            changelog_p = ver_dir / "CHANGELOG.md"
            for p in (input_p, output_p, errors_p):
                data = load_json(p)
                assert data.get("$schema") == SCHEMA_URL
                Draft202012Validator.check_schema(data)
                # $id and title consistency
                expected_id = f"urn:0admin:mcp:{tool_dir.name}:{version}:{p.stem}"
                assert data.get("$id") == expected_id
                expected_title = f"{tool_dir.name} {p.stem} {version}"
                assert data.get("title") == expected_title
            assert changelog_p.exists(), f"missing changelog for {tool_dir.name} {version}"
            first = changelog_p.read_text(encoding="utf-8").splitlines()[0].strip()
            assert first == f"{version} – initial"
            found += 1
    # 5 tools
    assert found == 5, f"expected 5 tools, found {found}"


def test_specific_field_rules():
    base = Path("backend/mcp/contracts")
    for tool_dir in base.iterdir():
        for ver_dir in tool_dir.iterdir():
            input_s = load_json(ver_dir / "input.json")
            output_s = load_json(ver_dir / "output.json")
            errors_s = load_json(ver_dir / "errors.json")

            # Errors subset of allowed
            enum_vals = set(errors_s.get("properties", {}).get("code", {}).get("enum", []))
            assert enum_vals, f"errors enum empty for {tool_dir.name}"
            assert enum_vals.issubset(ALLOWED_ERRORS)

            # $defs usage and errors subset
            for doc in (input_s, output_s):
                props = doc.get("properties", {})
                if not isinstance(props, dict):
                    continue
                if "tenant_id" in props:
                    assert props["tenant_id"] == {"$ref": "#/$defs/uuid"}
                if "ts" in props:
                    assert props["ts"] == {"$ref": "#/$defs/rfc3339"}
                if "window" in props:
                    assert props["window"] == {"$ref": "#/$defs/iso_duration"}
                if "cursor" in props:
                    assert props["cursor"] == {"$ref": "#/$defs/base64"}
                if "next_cursor" in props:
                    assert props["next_cursor"] == {"$ref": "#/$defs/base64"}

            # Base64 cursors and limit range
            if tool_dir.name == "ops.dlq_list":
                props_in = input_s.get("properties", {})
                assert props_in.get("limit", {}).get("minimum") == 1
                assert props_in.get("limit", {}).get("maximum") == 1000

            # QA selection whitelist
            if tool_dir.name == "qa.run_smoke":
                expected = ["upload","programmatic","worker","mail","read_ops","publisher"]
                got = input_s.get("properties", {}).get("selection", {}).get("enum")
                assert got == expected

            # ensure only allowed $refs are used
            def _walk_refs(node):
                if isinstance(node, dict):
                    if "$ref" in node:
                        assert node["$ref"] in ALLOWED_REFS
                    for v in node.values():
                        _walk_refs(v)
                elif isinstance(node, list):
                    for it in node:
                        _walk_refs(it)

            _walk_refs(input_s)
            _walk_refs(output_s)
