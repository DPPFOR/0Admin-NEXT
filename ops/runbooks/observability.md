# Observability Runbook

## U3-P1b Smoke

- App start (local example, no secrets):
  - `uvicorn backend.app:app --host 0.0.0.0 --port 8000`
  - ENV: `DATABASE_URL`, `AUTH_SERVICE_TOKENS`, `STORAGE_BACKEND=file`, `STORAGE_BASE_URI=file:///var/0admin/uploads`, `MAX_UPLOAD_MB` (default 25)
- Endpoint under test:
  - `POST /api/v1/inbox/items/upload`
- Automated tests:
  - Run: `pytest -q tests/smoke -W error`
  - JUnit (optional): `pytest -q tests/smoke --junitxml artifacts/u3-p1b-smoke.xml`
  - JSON artifact: `artifacts/u3-p1b-smoke.json` (written by smoke test)
  - Prerequisite: Alembic state must be at `head` (tests fail fast otherwise)
- Expected signals:
  - Logs include `trace_id`, `tenant_id`; no PII (no filenames/raw payloads)
  - Metrics counters increase: `inbox_received_total`, `inbox_validated_total`, `dedupe_hits_total`; latency histogram `ingest_duration_ms`
- Notes:
  - Storage writes are atomic (temp → fsync → move)
  - `sb://` storage backend is not supported in v1
  - Programmatic ingest logs use `ingest_source="remote_url"`
