# Operational Hardening (24/7-Betrieb)

Ziel: Stabiler Dauerbetrieb von Publisher & Inbox-Worker, Backpressure-Steuerung, Health/Readiness, Minimal-Alerting — GitHub Free kompatibel.

## A1 – Runner-Betriebsmodus
- Service-Mode (24/7):
  - Publisher: `python -c "from agents.outbox_publisher.runner import run_forever; run_forever(service_mode=True)"`
  - Worker: `python -c "from agents.inbox_worker.runner import run_forever; run_forever(service_mode=True)"`
  - Signale: `SIGTERM|SIGINT` → graceful Stop (≤ 10 s empfohlen), Loop beendet.
  - Backpressure: `*_POLL_INTERVAL_MS`, `*_BATCH_SIZE` (draining: bei Arbeit sofort weiter; bei Idle schlafen).
- Timer-Mode (Intervall):
  - Publisher/Worker: `run_forever(service_mode=False)` → Exit 0 bei Idle-Batch (Timer kann Ende erkennen), Exit 1 bei Config-/Laufzeitfehler.

Systemd-Snippets (Textbeispiele)
- Service (`/etc/systemd/system/outbox-publisher.service` analog für Worker):
  ```ini
  [Unit]
  Description=0Admin Outbox Publisher
  After=network.target

  [Service]
  Type=simple
  ExecStart=/usr/bin/python -c "from agents.outbox_publisher.runner import run_forever; run_forever(service_mode=True)"
  Restart=on-failure
  RestartSec=5
  LimitNOFILE=65536
  EnvironmentFile=/etc/0admin/env

  [Install]
  WantedBy=multi-user.target
  ```
- Timer (Oneshot, z. B. alle 1 min): `outbox-publisher@.service` ruft `run_forever(service_mode=False)` auf; Timer steuert Intervall.

Exit-Codes
- 0: Normaler Stop (Signal) oder Timer-Idle.
- 1: Fataler Config-Fehler (z. B. fehlende `WEBHOOK_URL`, `DATABASE_URL`) oder nicht abgefangener Laufzeitfehler.

## A2 – Health/Readiness
- App-Readiness: `GET /health/ready` liefert 200 mit DB-Ping (leichtgewichtig; Version inkl.).
- Runner-Liveness: Heartbeat-Strategie (ohne Zusatzlibs):
  - Im Log pro erfolgreichem Durchlauf `parsed|published`-Eintrag (enthält Dauer/ids).
  - Optional: „last_success_ts“ in lokaler Datei `/var/run/0admin/{publisher,worker}.last` (per externem Watcher geschrieben/ausgewertet).
- Eskalation: keine `published`-/`parsed`-Events innerhalb X Minuten → Alarm (siehe A5).

## A5 – Minimal-Alerting (ohne APM)
- Lag-/Fehlerschwellen (V1):
  - Warnung: `publisher_lag_ms > 300000` (≥ 5 Minuten)
  - Alarm: `dlq_size > 0`
  - Warnung: `parse_failures_total` Δ > 10 pro 5 Minuten
- Check-Mechanik: kleiner CLI-Checker (außerhalb Repo) liest Metrik-Snapshot (JSON von `/api/v1/ops/metrics`) und `dlq`-Größe; Exit 1 bei Überschreitung.
- Versand: via bestehendem Publisher-Webhook möglich (separater Job), kein Logging von Secrets/Payload.
- Maßnahmen: Backpressure anpassen, Services neu starten, DLQ via Ops-API gezielt replayen.

## A6 – Security-Notizen (Brücke zu U9)
- Secrets ausschließlich via Umgebungsvariablen/Secret-Store; keine Klartext-.env in CI-Logs.
- Token-Rotation (Service/Admin) vierteljährlich; nur gehashte Tokens in Auditfeldern.
- Webhook-Header-Allowlist nutzen; niemals Payload-Inhalte loggen.

## A7 – GitHub Free Gate
- Manuelle Freigabegrundlage: README-Badges (CI, Smokes, Coverage), plus folgende Checks:
  - CI-Build grün (Lint, mypy, Tests+Coverage ≥80 %). 
  - Smoke-Matrix grün; `artifacts/egress-violations.json` leer.
  - Nightly Alembic Roundtrip grün.
- Nach Deploy: `alembic current==head`, Services laufen (Logs: Heartbeat < X min), Metriken im Zielbereich, DLQ leer.
- Rollback: letzte grüne Revision + DB-Dump (Vortag) gemäß Backup-Runbook.
