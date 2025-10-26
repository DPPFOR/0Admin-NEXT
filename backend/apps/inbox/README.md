# Inbox

Das Inbox-Modul verwaltet eingehende Dokumente und deren Verarbeitung.

## MCP Integration (Read-Only Shadow Analysis)

- Beim Statuswechsel „validated“ wird ein lokaler MCP-Schattenlauf gestartet (read-only), der ein Artefakt unter `artifacts/inbox_local/{ISO8601UTC}_{SHA256}_result.json` schreibt.
- Logs (PII-frei) über Observability-Logger: `mcp_shadow_analysis_start` und `mcp_shadow_analysis_done` (nur Artefaktpfad, keine Dateinamen/URIs).
- Optionales Flag `MCP_SHADOW_EMIT_ANALYSIS_EVENT=true` emittiert ein Outbox-Info-Event `InboxItemAnalysisReady` (schema_version "1.0").
- Siehe auch: docs/inbox/orchestration.md

## Importer-Worker (Write-Pfad)

- Liest lokale MCP-Artefakte (`artifacts/inbox_local/*_result.json`) und schreibt `inbox_parsed.parsed_items` (+ optional `parsed_item_chunks`).
- Idempotent per `(tenant_id, content_hash)`; Flags `--dry-run`, `--no-upsert`, `--replace-chunks`.
- CLI/Tasks: `run_importer_from_artifact.py`, `run_importer_consume_outbox.py`, VS Code Tasks („Importer: from artifact“, „Importer: consume outbox“, „DB: apply migration“).
- Details, Migration & Tests: siehe `docs/inbox/importer.md`.

## Read Model (Agent)

- Read-only Views & Queries für Agenten/Tools (Flock „whiteduck“).
- DTOs + SQLAlchemy-Queries sowie CLI unter `tools/flows/query_read_model.py`.
- Dokumentation & Sicherheits-Hinweise: `docs/inbox/read_model.md`.
- API-Endpunkte siehe `docs/inbox/read_api.md`.

## Flock Enablement (read-only)

- Read-API + Client-Dokumentation: `docs/inbox/flock_enablement.md`.
- Beispiel-Playbooks und VS Code Tasks unter `tools/flock/`.
