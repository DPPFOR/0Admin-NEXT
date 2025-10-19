# 0Admin-NEXT
![CI](https://github.com/${GITHUB_REPOSITORY:-owner/repo}/actions/workflows/ci.yml/badge.svg) ![Smokes](https://github.com/${GITHUB_REPOSITORY:-owner/repo}/actions/workflows/smoke.yml/badge.svg)
![Coverage](https://img.shields.io/badge/coverage-%3E%3D80%25-brightgreen)
Vernetzte Automationsplattform für KMU-Handwerksbetriebe

## 🎯 Zweck

0Admin-NEXT ist die Backend- und Agentenbasis der SaaS-Lösung **0Admin**.
Das System automatisiert wiederkehrende Büro- und Verwaltungsprozesse in Handwerksbetrieben – von Kommunikation bis Rechnungsabwicklung – und bildet die Grundlage für zukünftige Module und Integrationen.

## 🧭 Leitprinzipien

* **README-first:** Jeder Ordner beginnt mit einer eigenen README.md, die Aufbau, Zweck und Arbeitsweise beschreibt.
* **Standalone-Prompts:** Alle Coding-Prompts sind kontextfrei, 1:1 ausführbar und enthalten sämtliche Entscheidungen innerhalb des Prompts.
* **pip-only, Python 3.12:** Keine alternativen Toolchains oder Buildsysteme.
* **Flock 0.5.3:** Standard-Framework für ereignisgesteuerte Agenten.
* **Lokal-First-Entwicklung:** Arbeiten in VS Code, Deploy per `scp` auf Server.
* **Meta-Ebene vor Umsetzung:** Erst Struktur und Architektur klären, dann „Go“ zur Realisierung.

## 👀 Observability Minimal

JSON-basierte Logs, Health-Endpunkte und in-process Metriken für Go-live-Bereitschaft ohne externe APMs.

### JSON-Logging (Pflichtfelder)
Jeder Log-Eintrag enthält mandatorisch:
- `trace_id`: UUID v4 (generiert falls fehlend)
- `tenant_id`: Tenant-Kontext (fallback "unknown")
- `level`: Log-Level (error/warn/info/debug)
- `msg`: Log-Nachricht
- `ts_utc`: ISO 8601 UTC-Zeitstempel
- `request_id`: optional (nur bei HTTP-Requests)

**Beispiel-Ausgabe:**
```json
{"trace_id":"12345678-1234-5678-9012-123456789012","tenant_id":"company_a","level":"info","msg":"Processing inbox item","ts_utc":"2025-10-18T10:30:00Z"}
```

### Health-Endpunkte
- `GET /health/ready`: `{status:"OK", version:"x.y.z", db:"OK"}`
- Leichter DB-Ping, Version aus `pyproject.toml`

### Metriken (in-process)
Counters + Histogram für Inbox-Monitoring:
- `inbox_received_total`: empfangen Items
- `inbox_validated_total`: validierte Items
- `dedupe_hits_total`: Duplikat-Hits
- `ingest_duration_ms`: Verarbeitungszeiten

**Schalter:** `ENABLE_METRICS=true/false` (Default: true)

Upload-Endpoint: siehe api_upload.md. Der Endpoint erhöht die Inbox-Counter (`inbox_received_total`, `inbox_validated_total`) und `dedupe_hits_total` bei Duplikaten; Latenzen fließen in `ingest_duration_ms`.

Programmatic Endpoint (Remote-URL): siehe backend/apps/inbox/api_programmatic.md. Sicherheitsknöpfe über ENV: `INGEST_TIMEOUT_CONNECT_MS`, `INGEST_TIMEOUT_READ_MS`, `INGEST_REDIRECT_LIMIT`, `INGEST_URL_ALLOWLIST`, `INGEST_URL_DENYLIST`. TLS-Verifikation ist strikt aktiviert (SNI, Cert-Check), keine Weitergabe eingehender Header an Remote.

## Read/Ops Endpoints (v1)
- Read-API: siehe backend/apps/inbox/api_read.md (Keyset-Paging mit HMAC-Cursor; `X-Tenant` Pflicht; Payload-Whitelist ohne PII/URIs).
- Ops-API (ADMIN only): siehe backend/apps/inbox/api_ops.md (`ADMIN_TOKENS` als CSV setzen). Endpunkte für DLQ/Replay, Outbox-Status und Metriken.
- ENV-Hinweise: `READ_MAX_LIMIT` (Server-Cap), `CURSOR_HMAC_KEY` (Pflicht für Prod, starker Secret-Wert), `ADMIN_TOKENS` (CSV von Rollen-Tokens).

### ENV-Steuerung
- `LOG_LEVEL=INFO|WARNING|ERROR|DEBUG`
- `ENABLE_METRICS=true|false`

### Grenzen
- Keine externe Metric-Pipelines (Prometheus/APM)
- Prozess-lokale Metriken nur
- Logs ausschließlich Console (kein File)
- Health ohne exception-details

## Roadmap 

Übersicht Inhalte, Packete und Terminschiene [](/docs/roadmap.md)


## ⚙️ Coding-Agenten (Cursor & GitHub Copilot Coding-Agent)

Diese drei Unterlagen definieren das Verhalten, die Regeln und den Arbeitsstil aller KI-basierten Coding-Agents in 0Admin-NEXT.
Sie sind verbindlich zu lesen und stehen unter Schreibverbot (nur Änderung durch den Architekten).

Policy [Policy](/.cursor/rules/Coding-Agent-Policy.mdc)
 — feste Compliance- und Architektur-Schicht
Agents [Agents](/.cursor/rules/agents.mdc)
 — operative Arbeitslogik und Prompt-Methodik
Issue-Template [Issue-Template](/.cursor/rules/Issue-Template_für_GitHub_Copilot_Coding-Agent.mdc)
 — standardisierter Task-Input für Copilot / Codex / Cursor
Event / Outbox Policy
- verbindliche Regel für Eventing & DLQ [](/.cursor/rules/Event-Outbox-Policy-Ereignisrichtlinie.mdc)
Weitere Hintergrundinformationen und Zusammenhänge findest du in der begleitenden
README unter [README](/docs/coding-agents/README.md)

## 🧩 Agent-Hand-off (Meta)

Die folgenden Ankerpunkte verbinden alle Coding-Agenten (Cursor & Copilot) mit den gültigen Meta-Richtlinien.  
Sie sichern konsistente Übergaben zwischen Architektur- und Umsetzungsebene.

### Aktiver Meilenstein
- **Jetzt:** Baseline-PR – Migration „initial“ (Schema, Trigger, Policies)  
- **Danach:** Schema V1 Inbox (inbox_items, parsed_items, chunks)

### Verbindliche .mdc-Dateien
- [.cursor/rules/Coding-Agent-Policy.mdc](/.cursor/rules/Coding-Agent-Policy.mdc) – Apply: Always  
- [docs/meta-rules.md](/docs/meta-rules.md) – Architekturprinzipien  
- [docs/event_outbox_policy.md](/.cursor/rules/Event-Outbox-Policy-Ereignisrichtlinie.mdc) – Eventing & DLQ-Mechanik 


## 🧱 Architektur-Überblick

```
backend/     → Geschäftslogik & Core-Services  
agents/      → Flock-basierte Orchestrierung (Mail, Kalender, Reports, Scheduler)  
frontend/    → Benutzeroberfläche (React + Tailwind + Vite)  
tools/       → CLI-Hilfsprogramme, Prompt-Standards  
docs/        → Produkt- und Prozessdokumentation  
tests/       → Integration- & End-to-End-Tests  
ops/         → CI, Systemd-Units, Deployment-Skripte  
data/        → Beispieldaten & Seeds
```

### Kernmodule

* **Inbox (Mail & Drop-Pipelines)** – zentrale Erfassung externer Eingänge
* **Angebots- & Rechnungserstellung** – Vorlagen, Nummernkreise, PDF-Layouts
* **E-Rechnung (ZUGFeRD / XRechnung)** – valide E-Rechnungsprofile
* **Mahnwesen** – automatische Mahnläufe, Eskalationsstufen, Kommunikationsadapter
* **BankFin** – Kontoabgleich und Buchungslogik
* **RAG-Wissen** – Trainings- und Wissenskomponente für interne Nutzung

## 📂 Navigations-Index

### Event / Outbox Policy
- [Event / Outbox Policy](docs/event_outbox_policy.md)


### Backend

* [](backend/README.md)
* [](backend/apps/mahnwesen/specification.md)
* [](backend/core/specification.md)

### Agents

* [](agents/README.md)
* [](agents/mahnwesen/specification.md)

### Tests

* [](tests/README.md)

### Ops / CI

* [](ops/ci/README.md)

### Tools

* [](tools/agent_safety_header.md)

## ⚙️ Arbeitsweise

1. Entwicklung ausschließlich lokal in VS Code.
2. Keine Änderungen direkt auf Servern, außer Notfall.
3. Vor jeder Umsetzung Meta-Ebene definieren und absegnen.
4. Änderungen dokumentieren, commit + push auf `main`.
5. CI-Checks (pytest, lint, migrations) sind verbindlich.

## 🔐 Policies

* Python 3.12 + pip only
* Flock 0.5.3 (fixe Version)
* Keine Strukturänderungen ohne Meta-Freigabe
* Pinned Dependencies in `requirements.txt`
* Ziel: stabiles, erweiterbares Produkt-Backend für reale Kundenbetriebe

Das Projekt nutzt zwei Anforderungsdateien:

- `requirements.txt` – Laufzeitabhängigkeiten für den produktiven Betrieb  
- `requirements-dev.txt` – Entwicklungs- und Testabhängigkeiten für lokale Umgebung und CI  

Installation:
- source .venv/bin/activate
- pip install -r requirements.txt -r requirements-dev.txt
Die Trennung sorgt dafür, dass Produktionssysteme nur minimale, sichere Pakete laden.
## Quality Gates
- CI Quality Gate (build): Lint (ruff inkl. Security S), Typecheck (mypy), Tests mit Coverage (Domain/Parsing ≥80%).
- Smoke-Matrix: Upload, Programmatic, Mail, Worker, Publisher, Read/Ops.
- Nightly Alembic Roundtrip (downgrade→upgrade) als Pflicht-Check.
- Egress-Sentinel blockiert unbeabsichtigte Netzaufrufe in Tests; Report `artifacts/egress-violations.json`.

## Ops-Checklist (GitHub Free)
- Vor Merge: CI-Build grün, Smoke-Matrix grün, Coverage ≥80 %, Egress-Report leer.
- Nach Deploy: `alembic current==head`; Publisher/Worker Services laufen (Logs: Heartbeat < X min); Metriken im Ziel; DLQ leer.
- Backups/Retention: Nightly `pg_dump` mit 7-Tage-Retention (siehe ops/runbooks/backup_restore.md); Storage-Rotation per Report+Commit (ops/runbooks/storage_rotation.md).
- Health/Readiness: siehe backend/core/observability/health_readiness.md; Publ./Worker `run_forever` (Signals: SIGTERM/SIGINT → graceful).
- Mini-Console (Read-Only): siehe frontend/console/README.md und ops/runbooks/console.md (Deployment/Proxy-Header)
- Ops-API-Runbook: siehe ops/runbooks/ops_tasks.md (DLQ/Replay, Outbox-Status, Metriken)

## Security & Data Protection (v1)
- ENV-only Secrets (GitHub Secrets/Server), nie in Logs/Artefakten. `CURSOR_HMAC_KEY` (>=32B) Pflicht in Prod.
- Admin vs. Service Tokens getrennt; Ops-APIs ADMIN-only; Audit-Logs mit `actor_token_hash` (HMAC), nie Klartext-Token.
- PII-Minimierung: keine Dateinamen/URIs/Raw-Bodies in Logs/Events/Read-Responses (Whitelist).
- Publisher/Webhook: HTTPS only, TLS verify, keine Redirects; Header-Allowlist strikt; optional Domain-Allowlist.

## MCP Fabric (Read-Only v1, lokal)

- Zweck: Lokales, importierbares MCP-Fabric (Registry, Policies, Security, Adapter-Stubs) ohne Server/Worker.
- Ausführung (VS Code Tasks):
  - MCP Contracts validieren: `python tools/mcp/validate_contracts.py`
  - MCP Smokes ausführen: `pytest -q backend/mcp/tests/smoke`
- Pfade:
  - Contracts: `backend/mcp/contracts`
  - Server/Registry/Adapter: `backend/mcp/server`
  - Policies/Runbooks: `ops/mcp`
  - CLIs: `tools/mcp`
- Doku: siehe [Architecture](docs/mcp/architecture.md), [Contracts](docs/mcp/contracts.md), [Policies](docs/mcp/policies.md), [Security](docs/mcp/security.md), [Migration](docs/mcp/migration.md)
- Runbooks: [Rollout](ops/mcp/runbooks/rollout.md), [Rotation](ops/mcp/runbooks/rotation.md), [Alerts](ops/mcp/runbooks/alerts.md), [Tenants](ops/runbooks/tenants.md)

### Policy-Fingerprint (lokal prüfen)
- Der Validator gibt einen SHA-256 Fingerprint der Policy aus.
- Lokal prüfen: `python tools/mcp/validate_contracts.py` → Zeile beginnt mit `[POLICY_SHA_FINGERPRINT]`.

- CI Security: gitleaks + pip-audit Reports (siehe ops/runbooks/security.md).
 - Dual-Key-Rotation: siehe ops/runbooks/secrets.md (`CURSOR_HMAC_KEY` + `CURSOR_HMAC_KEY_PREVIOUS`, 90 Tage Umschaltfenster, Rollback-Hinweise).

## Tenant-Policy v1
- Pflicht-Header `X-Tenant` (UUID) in allen APIs; nur Tenants aus der Allowlist erlaubt (ENV/Datei).
- Fehlercodes: `tenant_missing` (401), `tenant_malformed` (401), `tenant_unknown` (403).
- Ops: `GET /api/v1/ops/tenants` → Quelle/Version/Anzahl/Liste (UUIDs). Details: ops/runbooks/tenants.md

## Staging-Playbook & Deploy-Gates
- Staging-Setup: siehe `.env.staging.example` und ops/runbooks/staging_playbook.md.
- CI-Workflow: `.github/workflows/staging-deploy.yml` (manueller Dispatch, Gates: Smokes, Alembic-Offline-SQL, Security-Scan, Egress-Sentinel).
- Rollout auf Host: systemd-Units für Worker/Publisher (service-/timer-mode), `EnvironmentFile=/etc/zero-admin/staging.env`; Health/Ready prüfen; Console Overview kontrollieren.

Hinweise Mail-Connectoren
- Optionaler Auto-DI-Schalter (`MAIL_CONNECTOR_AUTO=1`): wählt IMAP/Graph nur bei vollständigen Credentials automatisch; ansonsten bleibt der DI/Stub-Pfad aktiv. Egress-frei in Tests (Mocks).
