# Health & Readiness

## App
- `GET /health/ready` — 200 OK bei erfolgreichem DB-Ping, Response enthält `status`, `version`, `db`.
- Leichtgewichtiger Check; ohne Exception-Details (PII-sicher).

## Runner (Publisher/Worker)
- Liveness via Log-Heartbeat: bei erfolgreichem Publish/Parse eine JSON-Logzeile (`published`/`parsed`) mit `tenant_id`, `event_type|doc_type`, `duration_ms`.
- Optional: Heartbeat-Datei (`/var/run/0admin/{publisher,worker}.last`) extern schreiben/prüfen.
- Exit-Codes: `run_forever(service_mode=False)` liefert 0 bei Idle, 1 bei Config-/Laufzeitfehler.
