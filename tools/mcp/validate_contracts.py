#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

# Ensure project root on sys.path for direct script execution
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from jsonschema import Draft202012Validator

JSONValue = dict[str, "JSONValue"] | list["JSONValue"] | str | int | float | bool | None

SCHEMA_URL = "https://json-schema.org/draft/2020-12/schema"
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
ALLOWED_REFS = {"#/$defs/uuid", "#/$defs/base64", "#/$defs/rfc3339", "#/$defs/iso_duration"}
UUID_PATTERN = (
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)
WINDOW_RE = (
    r"^(P(?=.+)(?:\d+W|\d+D(?:T(?:\d+H)?(?:\d+M)?(?:\d+S)?)?|T(?:\d+H)?(?:\d+M)?(?:\d+S)?))$"
)
BASE64_RE = r"^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$"
ALLOWED_ERRORS = {"VALIDATION", "NOT_FOUND", "UPSTREAM", "POLICY_DENIED", "RETRYABLE_IO"}


def rule(rule_id: str, path: Path, pointer: str, expected: str, actual: str) -> str:
    return f"[{rule_id}] {path}:{pointer} expected={expected} actual={actual}"


def load_json(p: Path) -> JSONValue:
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def validate_schema_doc(
    path: Path, data: dict[str, Any], version: str, tool_id: str, problems: list[str]
) -> None:
    # 1) Draft 2020-12
    if data.get("$schema") != SCHEMA_URL:
        problems.append(
            rule("GOV_ID_CONSISTENCY", path, "/$schema", SCHEMA_URL, str(data.get("$schema")))
        )

    # 2) Title may contain version; if present, enforce equality
    title = data.get("title")
    if isinstance(title, str):
        expected_title = f"{tool_id} {path.stem} {version}"
        if title != expected_title:
            problems.append(rule("GOV_ID_CONSISTENCY", path, "/title", expected_title, title))

    # 3) Basic draft validation compiles
    try:
        Draft202012Validator.check_schema(data)
    except Exception as e:
        problems.append(
            rule("GOV_ID_CONSISTENCY", path, "/", "valid Draft 2020-12", f"invalid: {e}")
        )

    # 4) $id matches convention urn:0admin:mcp:<tool_id>:<version>:<type>
    expected_id = f"urn:0admin:mcp:{tool_id}:{version}:{path.stem}"
    if data.get("$id") != expected_id:
        problems.append(rule("GOV_ID_CONSISTENCY", path, "/$id", expected_id, str(data.get("$id"))))

    # 5) $ref usage policy – only allowed refs
    def _walk_refs(node: JSONValue, ptr: str = "") -> None:
        if isinstance(node, dict):
            if "$ref" in node:
                refv = node["$ref"]
                if refv not in ALLOWED_REFS:
                    problems.append(
                        rule("GOV_DEFS_USAGE", path, f"{ptr}/$ref", " one of #/$defs/*", str(refv))
                    )
            for k, v in node.items():
                _walk_refs(v, ptr + "/" + k)
        elif isinstance(node, list):
            for i, it in enumerate(node):
                _walk_refs(it, ptr + f"/{i}")

    _walk_refs(data)


def walk_contracts(root: Path) -> list[tuple[str, str, Path, Path, Path]]:
    results: list[tuple[str, str, Path, Path, Path]] = []
    for tool_dir in sorted((root).iterdir()):
        if not tool_dir.is_dir():
            continue
        for ver_dir in sorted(tool_dir.iterdir()):
            if not ver_dir.is_dir():
                continue
            version = ver_dir.name
            if not SEMVER_RE.match(version):
                continue
            input_p = ver_dir / "input.json"
            output_p = ver_dir / "output.json"
            errors_p = ver_dir / "errors.json"
            if input_p.exists() and output_p.exists() and errors_p.exists():
                results.append((tool_dir.name, version, input_p, output_p, errors_p))
    return results


def main() -> int:
    base = Path("backend/mcp/contracts")
    problems: list[str] = []

    if not base.exists():
        print(rule("GOV_ID_CONSISTENCY", base, "/", "exists", "missing"), file=sys.stderr)
        return 1

    for tool, version, input_p, output_p, errors_p in walk_contracts(base):
        # Basic per-file checks
        for p in (input_p, output_p, errors_p):
            try:
                data = load_json(p)
            except Exception as e:
                problems.append(rule("GOV_ID_CONSISTENCY", p, "/", "valid JSON", f"error: {e}"))
                continue
            if not isinstance(data, dict):
                problems.append(rule("GOV_ID_CONSISTENCY", p, "/", "object", type(data).__name__))
                continue
            validate_schema_doc(p, data, version, tool, problems)

        # Detailed content checks
        input_s = load_json(input_p)
        output_s = load_json(output_p)
        errors_s = load_json(errors_p)

        # Errors: ensure enum codes subset of allowed
        try:
            enum_vals: set[str] = set()
            if isinstance(errors_s, dict):
                properties = errors_s.get("properties")
                if isinstance(properties, dict):
                    code_def = properties.get("code")
                    if isinstance(code_def, dict):
                        raw_enum = code_def.get("enum", [])
                        if isinstance(raw_enum, list):
                            enum_vals = {str(item) for item in raw_enum}
            if not enum_vals:
                problems.append(
                    rule(
                        "GOV_ID_CONSISTENCY",
                        errors_p,
                        "/properties/code/enum",
                        "non-empty",
                        "empty",
                    )
                )
            if not enum_vals.issubset(ALLOWED_ERRORS):
                problems.append(
                    rule(
                        "GOV_ID_CONSISTENCY",
                        errors_p,
                        "/properties/code/enum",
                        f"subset of {sorted(ALLOWED_ERRORS)}",
                        str(sorted(enum_vals)),
                    )
                )
        except Exception as e:
            problems.append(
                rule(
                    "GOV_ID_CONSISTENCY",
                    errors_p,
                    "/properties/code/enum",
                    f"subset of {sorted(ALLOWED_ERRORS)}",
                    f"malformed: {e}",
                )
            )

        # UUID fields
        for pth, doc in ((input_p, input_s), (output_p, output_s)):
            props = doc.get("properties", {}) if isinstance(doc, dict) else {}
            if not isinstance(props, dict):
                continue
            for k, v in props.items():
                if k == "tenant_id" and isinstance(v, dict) and v.get("$ref") != "#/$defs/uuid":
                    problems.append(
                        rule(
                            "GOV_DEFS_USAGE",
                            pth,
                            "/properties/tenant_id",
                            '{"$ref": "#/$defs/uuid"}',
                            json.dumps(v),
                        )
                    )
                if (
                    k in {"cursor", "next_cursor"}
                    and isinstance(v, dict)
                    and v.get("$ref") != "#/$defs/base64"
                ):
                    problems.append(
                        rule(
                            "GOV_DEFS_USAGE",
                            pth,
                            f"/properties/{k}",
                            '{"$ref": "#/$defs/base64"}',
                            json.dumps(v),
                        )
                    )
                if (
                    k == "window"
                    and isinstance(v, dict)
                    and v.get("$ref") != "#/$defs/iso_duration"
                ):
                    problems.append(
                        rule(
                            "GOV_DEFS_USAGE",
                            pth,
                            "/properties/window",
                            '{"$ref": "#/$defs/iso_duration"}',
                            json.dumps(v),
                        )
                    )
                if (
                    k == "limit"
                    and isinstance(v, dict)
                    and (v.get("minimum") != 1 or v.get("maximum") != 1000)
                ):
                    problems.append(
                        rule(
                            "GOV_ID_CONSISTENCY",
                            pth,
                            "/properties/limit",
                            "min=1,max=1000",
                            json.dumps(v),
                        )
                    )
                if k == "ts" and isinstance(v, dict) and v.get("$ref") != "#/$defs/rfc3339":
                    problems.append(
                        rule(
                            "GOV_DEFS_USAGE",
                            pth,
                            "/properties/ts",
                            '{"$ref": "#/$defs/rfc3339"}',
                            json.dumps(v),
                        )
                    )

        # PATH_GUARDS for inputs: path/paths must restrict to artifacts/inbox and forbid '..'
        in_props = input_s.get("properties", {}) if isinstance(input_s, dict) else {}
        if isinstance(in_props, dict):
            path_def = in_props.get("path")
            if isinstance(path_def, dict):
                patt = path_def.get("pattern")
                expected_prefix = "artifacts/inbox/"
                if not isinstance(patt, str) or expected_prefix not in patt:
                    problems.append(
                        rule(
                            "PATH_GUARDS",
                            input_p,
                            "/properties/path/pattern",
                            f"contains '{expected_prefix}'",
                            str(patt),
                        )
                    )
                if isinstance(patt, str) and (".." not in patt and "\\.\\." not in patt):
                    problems.append(
                        rule(
                            "PATH_GUARDS",
                            input_p,
                            "/properties/path/pattern",
                            "forbid '..'",
                            str(patt),
                        )
                    )
            paths_def = in_props.get("paths")
            if isinstance(paths_def, dict):
                items = paths_def.get("items", {})
                patt = items.get("pattern") if isinstance(items, dict) else None
                expected_prefix = "artifacts/inbox/"
                if not isinstance(patt, str) or expected_prefix not in patt:
                    problems.append(
                        rule(
                            "PATH_GUARDS",
                            input_p,
                            "/properties/paths/items/pattern",
                            f"contains '{expected_prefix}'",
                            str(patt),
                        )
                    )
                if isinstance(patt, str) and (".." not in patt and "\\.\\." not in patt):
                    problems.append(
                        rule(
                            "PATH_GUARDS",
                            input_p,
                            "/properties/paths/items/pattern",
                            "forbid '..'",
                            str(patt),
                        )
                    )

        # qa.run_smoke selection whitelist
        if tool == "qa.run_smoke":
            selection_values: list[str] = []
            if isinstance(input_s, dict):
                props = input_s.get("properties")
                if isinstance(props, dict):
                    selection = props.get("selection")
                    if isinstance(selection, dict):
                        raw_enum = selection.get("enum", [])
                        if isinstance(raw_enum, list):
                            selection_values = [str(item) for item in raw_enum]
            expected = ["upload", "programmatic", "worker", "mail", "read_ops", "publisher"]
            if selection_values != expected:
                problems.append(
                    rule(
                        "GOV_ID_CONSISTENCY",
                        input_p,
                        "/properties/selection/enum",
                        json.dumps(expected),
                        json.dumps(selection_values),
                    )
                )

        # CHANGELOG presence and first line
        changelog_p = input_p.parent / "CHANGELOG.md"
        if not changelog_p.exists():
            problems.append(rule("CHANGELOG_DATE_FORMAT", changelog_p, "/", "exists", "missing"))
        else:
            try:
                lines = changelog_p.read_text(encoding="utf-8").splitlines()
                first = (lines[0] if lines else "").strip()
                if first != f"{version} – initial":
                    problems.append(
                        rule(
                            "CHANGELOG_DATE_FORMAT",
                            changelog_p,
                            "/0",
                            f"{version} – initial",
                            first,
                        )
                    )
                second = (lines[1] if len(lines) > 1 else "").strip()
                if not re.match(r"^\d{4}-\d{2}-\d{2}$", second):
                    problems.append(
                        rule("CHANGELOG_DATE_FORMAT", changelog_p, "/1", "YYYY-MM-DD", second)
                    )
            except Exception as e:
                problems.append(
                    rule("CHANGELOG_DATE_FORMAT", changelog_p, "/", "readable", f"error: {e}")
                )

        # Validate schemas (compile)
        for p in (input_p, output_p, errors_p):
            try:
                Draft202012Validator.check_schema(load_json(p))
            except Exception as e:
                problems.append(
                    rule("GOV_ID_CONSISTENCY", p, "/", "valid Draft 2020-12", f"invalid: {e}")
                )

    # README link checks (Policies/Runbooks/Docs)
    readme = Path("README.md")
    if readme.exists():
        text = readme.read_text(encoding="utf-8")
        md_links = re.findall(r"\[[^\]]+\]\(([^)]+)\)", text)

        def _eligible(p: str) -> bool:
            return (
                p.startswith("docs/mcp/")
                or p.startswith("ops/mcp/")
                or p.startswith("ops/runbooks/")
            )

        for link in filter(_eligible, md_links):
            if not Path(link).exists():
                problems.append(rule("DOC_LINKS_EXIST", readme, "/links", "existing path", link))

    # Policy fingerprint (SHA256)
    default_policy = Path("ops/mcp/policies/default-policy.yaml")
    if default_policy.exists() and default_policy.read_text(encoding="utf-8").strip():
        content = default_policy.read_text(encoding="utf-8").encode("utf-8")
    else:
        content = b"dry_run_default:true\nallowed_tools:[ops.health_check]\n"
    fingerprint = hashlib.sha256(content).hexdigest()
    print(f"[POLICY_SHA_FINGERPRINT] {default_policy}: {fingerprint}")

    # Optional: Playwright postinstall warning (non-blocking)
    try:
        import importlib

        browsers_installed = False
        # simple heuristics: env path or default cache
        env_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
        candidates = []
        if env_path:
            candidates.append(Path(env_path))
        home = Path.home()
        candidates.append(home / ".cache" / "ms-playwright")
        for c in candidates:
            try:
                if c.exists() and any(child.is_dir() for child in c.iterdir()):
                    browsers_installed = True
                    break
            except Exception as exc:
                logging.debug("Playwright browser directory probe failed for %s: %s", c, exc)
                continue
        # If playwright not importable, skip; if importable but no browsers, warn
        importlib.import_module("playwright.sync_api")
        if not browsers_installed:
            print(
                "[POSTINSTALL_PLAYWRIGHT] README.md:/mcp postinstall expected=browsers installed actual=missing",
                file=sys.stderr,
            )
    except Exception as exc:
        # playwright unavailable or other import issue: no-op, do not fail
        logging.debug("Playwright postinstall check skipped: %s", exc)

    if problems:
        for message in problems:
            print(message, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
