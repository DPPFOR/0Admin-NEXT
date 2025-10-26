# Ops Tasks — DLQ/Replay & Status

Zweck: Administrative API-Aufgaben für Dead-Letter-Handling, Outbox-Status und Metriken.

Auth
- ADMIN-Only: `Authorization: Bearer <token>` muss in `ADMIN_TOKENS` konfiguriert sein.
- Optionaler Tenant-Filter via `X-Tenant`.

Endpoints
- `GET /api/v1/ops/dlq`: Dead-Letter-Items listen (id, tenant_id, event_type, reason, created_at); optional Filter auf Tenant.
- `POST /api/v1/ops/dlq/replay`: DLQ-Replay (dry-run default). Body: `{ids?:[], dry_run?:true, limit?:50}`
  - Dry-Run: keine Änderungen; Response enthält `selected`.
  - Commit (`dry_run=false`): Events werden erneut in `event_outbox` enqueued (`status=pending`); DLQ-Items gelöscht.
- `GET /api/v1/ops/outbox`: Aggregation `status -> count` (optional Tenant).
- `GET /api/v1/ops/metrics`: JSON-Metriken (in-process Snapshot), ADMIN only.

Observability
- Logs enthalten: `actor_role=admin`, `tenant_id|*`, `endpoint`, `duration_ms`, `selected`, `committed`.
- Metriken: `ops_replay_attempts_total`, `ops_replay_committed_total`, `ops_duration_ms`.

Sicherheit & PII
- Keine Rohpayloads, Dateinamen oder URIs im Response/Logs.
- Cursor/HMAC nur für Read-APIs (siehe api_read.md).
