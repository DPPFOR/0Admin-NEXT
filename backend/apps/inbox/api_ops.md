# Ops API v1 — DLQ/Replay, Outbox, Metrics

Endpoints (ADMIN only)
- GET `/api/v1/ops/dlq` — List dead letters (optional tenant filter)
- POST `/api/v1/ops/dlq/replay` — Replay DLQ (default `dry_run=true`), optional `ids`, `limit`
- GET `/api/v1/ops/outbox` — Aggregate outbox status counts (optional tenant)
- GET `/api/v1/ops/metrics` — JSON metrics snapshot

Headers
- `Authorization: Bearer <token>` — must be in `ADMIN_TOKENS` (CSV)
- `X-Tenant: <uuid>` — optional filter for DLQ/Outbox

Safety
- Replay is dry-run by default; only with `dry_run=false` are events re-enqueued. Audit logs are emitted.
- PII-free: returns only technical metadata; no payload bodies, filenames, or URIs.

Observability
- Logs: `trace_id`, `tenant_id|*`, `actor_role=admin`, `endpoint`, `duration_ms`, `selected`, `committed`.
- Metrics: `ops_replay_attempts_total`, `ops_replay_committed_total`, `ops_duration_ms` histogram.
