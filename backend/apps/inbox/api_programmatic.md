# Programmatic API v1 — Remote URL Ingest

Endpoint: POST `/api/v1/inbox/items`

Headers
- `Authorization: Bearer <token>` (required; whitelist via `AUTH_SERVICE_TOKENS`)
- `X-Tenant: <uuid>` (required)
- `Idempotency-Key: <string ≤128>` (optional)

Body (JSON)
```json
{
  "remote_url": "https://...",
  "source": "api",
  "meta_json": "{...}"
}
```

Security (SSRF protection)
- HTTPS-only; other schemes rejected with 400 `unsupported_scheme`.
- TLS is strictly verified (cert verification on, SNI enabled; no `verify=false` path).
- DNS/IP checks before fetch (and after redirects): reject private/loopback/link-local/CGNAT/multicast addresses with 403 `forbidden_address`.
- Redirect limit: `INGEST_REDIRECT_LIMIT` (default 3); above limit → 400 `redirect_limit`.
- Timeouts: connect/read via `INGEST_TIMEOUT_CONNECT_MS`/`INGEST_TIMEOUT_READ_MS`; timeouts map to 5xx `remote_timeout`.
- Content-Length precheck and hard cap: `MAX_UPLOAD_MB`; exceeding → 400 `size_limit`.
- Optional allowlist/denylist by domain suffix: `INGEST_URL_ALLOWLIST`/`INGEST_URL_DENYLIST` (CSV); violations → 403 `forbidden_address`.
- Hostname handling: IDNA/Punycode normalization is applied for policy checks; `localhost.` (with trailing dot) and IP literals (IPv4/IPv6) are recognized.
- No header propagation to remote: the service does not forward incoming Authorization/Cookies. Redirect targets are re-validated (host/port/proto) on every hop.

Validation
- MIME detection is server-side (magic/heuristic) and must match allowlist (`MIME_ALLOWLIST`), else 400 `unsupported_mime`.
- SHA-256 hash over raw bytes.

Deduplication & Idempotency
- DB guard: `UNIQUE(tenant_id, content_hash)`; duplicates return 200 with `duplicate=true` and original result.
- `Idempotency-Key` + `event_type='InboxItemValidated'` dedups the outbox event via UNIQUE `(tenant_id, idempotency_key, event_type)`.

Persistence & Status
- Only `uri + content_hash` stored, no blobs.
- Status: `received → validated` after checks.
- Storage: `file://` only (sb:// not supported in v1; returns `io_error`).

Eventing
- Emits `InboxItemValidated` with `schema_version="1.0"` and payload: `inbox_item_id, content_hash, uri, source="api", filename (if derivable), mime`.

Observability
- Logs: start/end with `ingest_source="remote_url"`, size/mime, dedupe/idempotency paths, event emit (no raw payloads/filenames).
- Metrics: `inbox_received_total++`, `inbox_validated_total++` on success, `dedupe_hits_total++`. Fetch duration logged as `fetch_duration_ms`.

Errors (standardized)
- 400 `unsupported_scheme`
- 400 `size_limit`
- 400 `unsupported_mime`
- 403 `forbidden_address`
- 400 `redirect_limit`
- 5xx `remote_timeout` / `io_error`
- 409 `hash_duplicate` (only for non-idempotent flow; default behavior is 200 duplicate=true)
- 401/403 `unauthorized`
