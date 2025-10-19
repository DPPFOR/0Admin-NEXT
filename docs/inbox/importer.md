Importer-Worker (Write-Pfad)

Schreibt MCP-Artefakte (`artifacts/inbox_local/*_result.json`) in Postgres (`inbox_parsed.parsed_items` + `parsed_item_chunks`).

- Idempotenz via `(tenant_id, content_hash)` – Flags: `--dry-run`, `--no-upsert`, `--replace-chunks`.
- Mapping: Artefakt → kompakte `payload`, `doc_type`, optionale `amount`, `invoice_no`, `due_date`, `quality_flags`.
- `amount` wird als `NUMERIC(18,2)` (Decimal) gebunden, `due_date` als `DATE`; JSON-Felder (`payload`, `quality_flags`) gehen typisiert als JSONB in Postgres.
- Chunks: jede Tabelle (`extracted.tables`) wird als `kind="table"`, `seq` fortlaufend, `payload` JSON gespeichert.
- CLI: `python tools/flows/run_importer_from_artifact.py --tenant <uuid> --artifact artifacts/inbox_local/samples/sample_result.json` (nur ID auf stdout; Exit 0/2/3 je nach Fehlerklasse).
- Tasks: VS Code (`Importer: from artifact (sample)`, `Importer: consume outbox (1)`, `DB: apply migration (local)`).
- Logs (PII-frei): `importer_started` / `importer_done` mit `trace_id`, `tenant_id`, `content_hash`, `parsed_item_id`, `action`.

Outbox-Consumer
- Script: `python tools/flows/run_importer_consume_outbox.py`
- Holt genau 1 `InboxItemAnalysisReady` (schema_version `1.0`) aus `event_outbox`, führt Import durch (`upsert=True`, `replace_chunks=False`), markiert Event `status='processed'` (Fallback: delete).

Migration / Setup
- SQL: `ops/alembic/versions/20251019_inbox_parsed.sql`
  - Schema `inbox_parsed`, Tabellen `parsed_items`, `parsed_item_chunks`, UNIQUE-Keys & Indizes.
  - Apply: `psql "$INBOX_DB_URL" -f ops/alembic/versions/20251019_inbox_parsed.sql`
- DB-URL: setze `INBOX_DB_URL` oder verwende `settings.database_url` (Pydantic Settings).

Tests
- Unit: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q tests/inbox/test_importer_*`
- Optionale E2E (`RUN_DB_TESTS=1`, `INBOX_DB_URL` gesetzt): `tests/inbox/test_importer_db_e2e.py` importiert Sample-Artefakt in echte DB und prüft Daten/Chunks.

Troubleshooting
- Pfad ungültig → ValueError („invalid artifact path“).
- Betrags-/Datumsvalidierung: `amount` → `^\d+(\.\d{1,2})?$`, `due_date` → `YYYY-MM-DD`.
- Schema-/Index-Fehler → sicherstellen, dass Migration ausgeführt wurde.
