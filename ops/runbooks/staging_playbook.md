# Staging-Playbook & Deploy-Gates (Inbox-Fokus) v1

Ziel: Reproduzierbare Staging-Umgebung (ohne PII), validierbare Inbox-E2E, klare Deploy-Gates und Rollback-Pfad.

## ENV/Secrets (Staging)
- Siehe `.env.staging.example` — vollständige Liste aller Schlüssel (keine echten Werte).
- Secrets (GitHub/Host) → Laufzeit: via `EnvironmentFile=/etc/zero-admin/staging.env` in systemd-Units/Timer.
- Secret-Klassen: DB-DSN, `ADMIN_TOKENS`, `AUTH_SERVICE_TOKENS`, `CURSOR_HMAC_KEY` (+ optional `CURSOR_HMAC_KEY_PREVIOUS`), `WEBHOOK_*` (optional), `MAIL_*` (optional).

## DB & Migrations
- Preflight: `alembic current` == `head`; `search_path=zero_admin,public`; Extension `pgcrypto` aktiv.
- Backup-Hook: vor Deploy `pg_dump` (Schema+Data) → Artefakt mit Zeitstempel.
- Readiness: Baseline + schema_v1_inbox vorhanden.

## Deploy-Gates (CI)
- Workflow `.github/workflows/staging-deploy.yml` (manual dispatch):
  1) Smoke-Matrix (upload/programmatic/worker/mail/read_ops/publisher) gegen Staging-DB; egress-frei (nur DB-Zugriff erlaubt).
  2) Alembic Roundtrip (Offline SQL) mit `--sql` (kein Schreibzugriff), Reports als Artefakte.
  3) Security Scan (gitleaks/pip-audit) warn-only, harte Fail bei Secret-Fund.
  4) Egress-Sentinel aktiv (nur DB erlaubt), Artefakt `artifacts/egress-violations.json` leer.

## Rollout (Staging-Host)
- Systemd Units: `inbox_worker.service`, `outbox_publisher.service` (timer-mode oder service-mode, vgl. ops/runbooks/worker_inbox.md und outbox_publisher.md).
- Secrets per `EnvironmentFile=/etc/zero-admin/staging.env`.
- Health/Ready prüfen (`GET /health/ready`), Console Overview (Read-Only) unter Staging-Base-URL prüfen.

## Rollback
- DB: `pg_restore` vom letzten Dump (Scope `zero_admin`), anschließend `alembic stamp head`.
- Artefakte: vorheriger App-Build (console `dist/`), systemd Switch-Back (Restart Services).
- Checks: `alembic current`, Outbox/DLQ leer.

## Data/PII-Sauberkeit
- Staging ohne Kundendaten; synthetische Fixtures (kleine PDFs/JSON).
- Mail-Connectoren aus (oder Dummy); Publisher `stdout`.

## Observability in Staging
- Alerts (handbuchbasiert): `dlq_size>0` → rot, `publisher_lag_ms>5m` → gelb, `parse_failures_total Δ>10/5m` → gelb.
- Console (Read-Only): Header-Policy befolgen (keine Tokens im LocalStorage), `X-Trace-ID` pro Request.

## Checkliste Abnahme
- `.env.staging.example` vollständig; Secrets gesetzt.
- CI-Gates grün (Smoke-Matrix, Roundtrip-SQL, Security, Egress).
- Health/Ready/Console grün; Outbox/DLQ plausibel.
- Backup vor Deploy vorhanden; Rollback-Probe dokumentiert.
