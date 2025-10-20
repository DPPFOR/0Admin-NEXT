# VS Code MCP 1.105 Migration

This guide describes how to run the new local MCP stdio server (`backend.mcp_server`) with VS Code 1.105 and how it integrates with the existing 0Admin multi-tenant setup.

## Prerequisites

- Python 3.12 inside the project `.venv`
- Updated `.vscode/settings.json` with the `mcpServers.0admin-local` entry
- Optional: policy overrides in `ops/mcp/policies/default-policy.yaml`

## Starting the Server

VS Code launches the server automatically via the `mcpServers` configuration:

```json
"mcpServers": {
  "0admin-local": {
    "command": "python",
    "args": ["-m", "backend.mcp_server"],
    "env": {
      "POLICY_FILE": "ops/mcp/policies/default-policy.yaml",
      "ARTIFACTS_DIR": "artifacts",
      "LOG_LEVEL": "INFO"
    },
    "transport": "stdio",
    "cwd": "${workspaceFolder}"
  }
}
```

To start the server manually use the VS Code task **MCP: Start (stdio)** or run `python -m backend.mcp_server`.

## Available Tools

| Tool | Description | Inputs (required) | Output artifact |
| --- | --- | --- | --- |
| `pdf_text_extract` | Extracts deterministic text from local PDFs. | `tenant_id`, `trace_id`, `path`, optional `ocr_hint`. | `artifacts/pdf_text_extract/<tenant>/<trace>/text.json` |
| `pdf_table_extract` | Detects tabular layouts from the PDF text layer. | `tenant_id`, `trace_id`, `path`, optional `table_boost`. | `artifacts/pdf_table_extract/<tenant>/<trace>/tables.json` |
| `security_pii_redact` | Masks email & phone PII in text using regex rules. | `tenant_id`, `trace_id`, `text`, optional `policy`. | `artifacts/security_pii_redact/<tenant>/<trace>/redaction.json` |

All tools require the tenant context (`tenant_id`, `trace_id`) and persist JSON-safe outputs under the configured artifacts directory.

## Multi-Tenant & Logging

- Each tool enforces the tenant context and logs structured JSON with `tenant_id`, `trace_id`, `tool`, `duration_ms`, and status.
- Logs are emitted via stdout in JSON format and are visible in the VS Code MCP panel or the integrated terminal.

## Egress Policy

- `ops/mcp/policies/default-policy.yaml` enforces `deny_all` network egress. Only local filesystem access under `artifacts`, `docs`, and `tests` is allowed.
- The `POLICY_FILE` environment variable can point to alternative policies; `ALLOW_UNIX_SOCKET=1` permits Unix domain sockets if required.
- The `EgressGuard` test in `tests/mcp/test_mcp_server_offline.py` validates the guard for offline environments.

## Smoke Tests

- Run **MCP: Smokes (offline)** task or execute `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q tests/mcp/test_mcp_server_offline.py`.
- Tests start the server via stdio, invoke each tool, validate JSON schemas, ensure deterministic artifacts, and confirm egress blocking.

## Flock Integration

Flock agents remain read-only consumers of the Read-API/Views. The MCP server provides local tooling only; it does not expose write paths or interact with the database.
