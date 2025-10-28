# Upload API v1 — Inbox Items

Endpoint: POST `/api/v1/inbox/items/upload`

Headers
- `Authorization: Bearer <token>` (required)
- `X-Tenant: <uuid>` (required)
- `Idempotency-Key: <string ≤128>` (optional)

Auth
- Minimal service-token validation: if env `AUTH_SERVICE_TOKENS` (CSV) is set, the Bearer token must be in that whitelist; otherwise, only header shape is validated (internal mode).

Content-Type
- `multipart/form-data`

Form fields
- `file` (required): file content
- `source` (optional, string ≤64): custom source label (default: `upload`)
- `filename` (optional): override filename for metadata/response
- `meta_json` (optional): JSON string for future use (ignored in v1)

Validation
- Size limit: `MAX_UPLOAD_MB` (env, default 25 MB)
- MIME allowlist (server-side detection):
  - `application/pdf`
  - `image/png`
  - `image/jpeg`
  - `text/csv`
  - `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
  - `application/json`
  - `application/xml`
- Hash: SHA-256 over raw bytes (hex lowercase, 64 chars)
 - Uncertain/unknown formats fall back to `unsupported_mime` (file extension is ignored)

Deduplication & Idempotency
- Unique constraint: `UNIQUE(tenant_id, content_hash)`
- Duplicate upload: 200 with `duplicate=true` and first result
- `Idempotency-Key`: passed to outbox and used to guard event duplication

Persistence & Status
- Storage: only URI + hash in DB; no blobs in Postgres
- Storage URI schemes: `sb://<bucket>/<key>` or `file:///<abs/path>`
- Status: `received` → validated (technical checks)

Eventing
- After validation: outbox event `InboxItemValidated` with fields:
  - `event_type`, `schema_version`, `tenant_id`, `trace_id`, `idempotency_key` (if provided)
  - `payload`: `inbox_item_id`, `content_hash`, `uri`, `source`, `filename`, `mime`
- Idempotency guard: `UNIQUE (tenant_id, idempotency_key, event_type)`
 - `schema_version` is set to `1.0`

Observability
- Logs (JSON): upload start/end, duplicate hit, validation errors, event emit (metadata only)
- Metrics:
  - `inbox_received_total++`
  - `inbox_validated_total++` on success
  - `dedupe_hits_total++` on duplicates
  - `ingest_duration_ms` histogram (start → before response)

Responses
- 200 OK
```json
{
  "id": "<uuid>",
  "status": "validated",
  "tenant_id": "<uuid>",
  "content_hash": "<sha256-hex>",
  "uri": "sb://...|file://...",
  "source": "upload|<custom>",
  "filename": "<name>",
  "mime": "<detected>",
  "duplicate": false
}
```

Errors (standardized)
- 400 `unsupported_mime`
- 400 `size_limit`
- 401/403 `unauthorized` (missing/invalid auth or X-Tenant)
- 409 `hash_duplicate` (only if Idempotency-Key not used; v1 returns 200 duplicate=true)
- 5xx `io_error` (storage/DB/unexpected)

Notes
- Server enforces MIME detection (file extension ignored)
- No raw payloads in logs (hash/IDs/URIs only)
 - Storage backends: v1 supports only `file://`; `sb://` is not supported and will return `io_error`
 - URI scheme (file backend): `file:///<base>/<tenant>/<HH>/<sha256><ext>`
