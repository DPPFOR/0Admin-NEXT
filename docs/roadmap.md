# docs/roadmap.md
# Roadmap (Go-Live, kein Demo) – Schreibverbot für Nicht-Admins

🧭 Meilenstein 1 – Inbox & Dateneingang

Ziel: Alle Kundendaten (E-Mails, Dateien, Uploads) laufen strukturiert in das System.
Umfang:
- Projektgrundlagen, Repo-Struktur, Policies, Pip-Setup
- Inbox-Pipelines (Mail, Upload, API)
- Chunking & Parsing-Flow (Rechnungserkennung, Metadaten)
- PostgreSQL-Grundlagen + Alembic-Migrationen
- Data-Validierung & Audit-Logs
Ergebnis: Daten aus verschiedenen Quellen landen normalisiert und versioniert in PostgreSQL.
Go-Live-Marker: Alle Artefakte produktionsreif, keine Demo-/Seed-Inhalte.

⚙️ Meilenstein 2 – Core & Event-Driven Basis

Ziel: Das System reagiert auf Ereignisse statt auf direkte Aufrufe.
Umfang:
- Outbox-Pattern & Event-Logik (Atomarität, Retries, Dead-Letters)
- Repository-Pattern & Domain-Modelle
- Flock-Agenten-Grundrollen (Planer, Sender, Payment, SLA)
- Logging + Monitoring-Grundstruktur (Trace-ID, JSON-Logs, Health)
- MS Graph-Integration (E-Mail, Calendar Light)
Ergebnis: Events fließen durch das System, Agenten reagieren asynchron, erste Mahnzyklen laufen.

💼 Meilenstein 3 – Mahnwesen Automation v1

Ziel: Automatische Mahnläufe mit echten Daten und mandantenbezogener Logik.
Umfang:
- Domain-Programm für Reminder (Stufen, Fristen, Kommunikation)
- Flock-Agenten live (Detection, Planer, Benachrichtigung, Payment)
- Multi-Tenant-Fähigkeit (tenant_id, Policies, Templates pro Mandant)
- E-Mail-Versand über Brevo mit Zustellnachweis
- Minimal-Frontend zur Überwachung (Pipeline, Fehler, Eskalationen)
Ergebnis: Ein automatisierter Mahnzyklus läuft End-to-End vom Input bis zum Versand.

🧩 Meilenstein 4 – Ops, Tests & Skalierung
Ziel: Stabilität, Nachvollziehbarkeit, CI/CD-Reife.
Umfang:
- Test-Coverage ≥80 % Domain, Contract-Tests für Events
- Automatisiertes Monitoring, Dead-Letter-Jobs, Alerting
- CI-Checks (Pytest, Lint, Alembic, Coverage)
- Branch-Protection & Required-Status-Checks
- Dokumentation, Templates, Audit- und Retention-Policies
Ergebnis: Produktionsreifes Backend mit laufender Überwachung und Deployment-Sicherheit.
Arbeitsprogramm (strukturgebend, Meta)

Roadmap-Start & Repo-Grundlagen (Root)
 a) Projektstruktur: backend/, agents/, data/, docs/, tools/, tests/, ops/, artifacts/.
 b) Python 3.12; pip-only; Requirements getrennt.
 c) README-first-Regel an jeder Hauptebene.
 d) Coding-Agent-Policy aktiv; Schreibfreigaben nur nach „Go“.
 e) Roadmap ist lebendiges Dokument (nur additiv).

### Freigabestatus (Meta) – Stand 18.10.2025
- **Baseline (initial)** – Meta-freigegeben (siehe docs/meta-rules.md, Abschnitt „Baseline-Scope & Regeln“); technische Migration folgt als nächster Coding-Schritt.
- **Schema V1 Inbox** – Meta-freigegeben (siehe backend/apps/inbox/specification.md, Abschnitt „Schema V1 Inbox“); Umsetzung als Alembic-Revision „schema_v1_inbox“ nach erfolgreicher Baseline.
- Beide Spezifikationen gelten als produktionsrelevant und sind Teil des aktiven Meilensteins „Inbox & Dateneingang“.
- Status: *Ready for Coding Agents* (Cursor & Copilot) mit klarer DoD-Referenz.


Backend-Skelett & Kernprinzipien
 a) Ordnerkonzept: backend/apps, backend/core, backend/common.
 b) Dependency Injection (Constructor), keine Globals.
 c) Unit-of-Work-Konzept (Transaktionsgrenzen) definieren.
 d) Event-Driven-Basis mit Outbox (noch ohne Worker).
 e) Logging-Contract (JSON; trace_id, tenant_id, request_id).

Inbox als primärer Dateneingang
 a) Quellen: E-Mail-Weiterleitung, Drag&Drop, Datei-Upload, API.
 b) Dateitypen: PDF, PNG/JPG, CSV/XLSX, XML/JSON.
 c) Normalisierung: Store+Meta (kein Parsing in diesem Schritt).
 d) Quarantäne/Validierung: Format, Größe, Mandantenmarker optional.
 e) Minimal-Frontend: Upload, Status, Fehleranzeige.

Parsing & Chunking-Pipeline
 a) Dokumentklassifikation (Rechnung, Zahlung, Sonstiges).
 b) Extraktion strukturierter Felder (Rechnungsnummer, Betrag, Fälligkeit).
 c) Chunking-Regeln (Seiten/Abschnitte, Referenzen zu Originalen).
 d) Fehlerfälle markieren; manueller Nacharbeitspfad.
 e) Persistenz von Extraktions-Logs (Audit).

PostgreSQL & Alembic
 a) Baseline „initial“: Schema zero_admin, Extension pgcrypto, zentraler search_path, Trigger-Infrastruktur, Policies.
 b) schema_v1_inbox: inbox_items, parsed_items, optional chunks; Outbox/processed_events.
 c) Alembic-only-Policy; Upgrade/Downgrade-Checkliste.
 d) Test-Fixtures in data/ (keine Demo-/Seed-Daten).
 e) Naming-Konventionen: pk_, fk__referred_, uq__, ix__, ck__.

Datenzugriff & Domänenkontrakte
 a) Repository-Interfaces (Inbox, Events, Reminder).
 b) Application-Commands/Queries (ohne Implementierung).
 c) Domain-Modelle beschreiben (Invoice, Reminder, PaymentEvent).
 d) Idempotency-Keys-Politik definieren.
 e) Transaktions-DoD: Write + Outbox atomar.

Outbox/Eventing-Grundlage
 a) Event-Felder: event_type, schema_version, tenant_id, trace_id, idempotency_key.
 b) Status-States: pending, processing, sent, dead.
 c) Retry-Strategie (Backoff-Stufen).
 d) Dead-Letter-Kriterien textlich festlegen.
 e) Event-Versionierung (SemVer).

Microsoft Graph – minimal
 a) Mail: Versenden für Mahnungen (Tenant-Postfächer oder App-Only).
 b) Calendar: Wiedervorlagen/Follow-ups.
 c) Ablage: OneDrive/SharePoint-Ordnerstruktur.
 d) Scopes/Least-Privilege-Policy.
 e) Audit-/Nachweisprinzip (Message-Id, Send-Status).

Flock-Agenten – Rollen & Schnittstellen
 a) Eingangs-Detektor (überfällige Fälle).
 b) Reminder-Planer (Stufe/Gebühr/Next-Action).
 c) Benachrichtigungs-Agent (Kanalwahl, Versandauftrag).
 d) Zahlungsabgleich-Agent (PaymentEvents, Fälle schließen/pausieren).
 e) Eskalations-Agent (späte Stufen).
 f) SLA/Monitoring-Agent (Lag, Fehler, Durchlaufzeiten).

Multi-Tenant-Fähigkeit
 a) Tenant-Policy: Pflichtkennzeichnung in Requests/Events.
 b) Datenmodell: tenant_id in fachlichen Tabellen; spätere RLS.
 c) Tenant-Config (Fristen, Gebühren, Kanäle).
 d) Vorlagen/Branding pro Tenant (Policy).
 e) Rechte-/Rollenmodell (Sachbearbeiter, Admin).

Mahnwesen-Domänenprogramm v1
 a) Stufenmodell: Soft → M1 → M2 → Letzte → Eskalation.
 b) Gebühren-/Fristenregeln (überschreibbar pro Tenant).
 c) Kommunikationsregeln: Sendezeit, Kanalpräferenzen.
 d) Fehler-/Sonderfälle: Widerspruch, Teilzahlung.
 e) Dokumentations-/Ablageprinzip je Stufe.

E-Mail-Versand (Brevo)
 a) Einsatz: operative Mahnungen, Transaktionsmails.
 b) Absender-/Domain-Setup (SPF/DKIM).
 c) Zustellnachweis/Events (Delivered, Bounce, Complaint).
 d) Rate-Limits/Throttling-Policy.
 e) Datenschutz-/Opt-Out-Richtlinien.

Monitoring & Dead-Letter-Job
 a) Kennzahlen: events_processed, failures_total, publisher_lag, dlq_size, reminder_cycle_time.
 b) Alerts: DLQ-Alter, Lag-Schwellen, Fehlerrate.
 c) Dead-Letter-Replay-Policy (manuell mit Freigabe).
 d) Health-/Readiness-Kriterien.
 e) Betriebs-Runbook (Störungen, Eskalation).

Tests & Coverage
 a) Testpyramide: Domain-Unit ≥80 %, Application-Integration, E2E.
 b) Contract-Tests für Event-Typen (Producer/Consumer).
 c) Fake-Connectors (Graph/Brevo) für Tests.
 d) Data-Fixtures (in data/) für Mahn-Flows.
 e) Abnahme-Checklisten je Arbeitspaket (Meta-DoD).

CI & Required Checks
 a) Pipelines: pytest, lint, mypy, alembic up/down smoke.
 b) Coverage-Gates (Domain), Artefakte hochladen.
 c) Branch-Schutz: PR erforderlich; Checks required.
 d) Draft-PR-Flow für Coding-Agenten (Nightly).
 e) Issue-Labels/Meilensteine (Backlog-Steuerung).

Vorlagen & Content-Governance
 a) Template-Katalog (Sprachen, Stufen, Branding-Platzhalter).
 b) Genehmigungsprozess (Vier-Augen für rechtliche Änderungen).
 c) Versionierung/Archivierung von Vorlagen.
 d) Preview-/Plausibilitäts-Check (Platzhalter vollständig).
 e) Kommunikations-Historie referenzierbar im Fall.

API-Konnektoren (Meta-Definition)
 a) finAPI/Konteninformationen für PaymentEvents (später aktivieren).
 b) Druck/Briefdienst für letzte Mahnung/Eskalation.
 c) ERP/Buchhaltung (Export/Import-Schnittstellen).
 d) Webhook-/Polling-Strategien pro Connector.
 e) Versionierung/Namensregeln für externe APIs.

Frontend-Integration (minimum viable)
 a) Pipeline-Übersicht (Statusspalten, Filter).
 b) Fall-Detail (Timeline, Aktionen).
 c) Arbeitslisten („Heute fällig“, „Eskalieren“, „Fehler/DLQ“).
 d) Einstellungen (Basispolicies, Kanalpräferenzen).
 e) Accessibility/Performance-Grundsätze.

Backlog-Aufbau & Planungstakt
 a) Aus Punkten 3–18 konkrete Issues ableiten (S/M).
 b) Abend-Runs: klar begrenzte Issues für Coding-Agent, Draft-PR only.
 c) Wöchentlicher Roadmap-Review, nur additive Änderungen.
 d) Verlinkung roadmap.md ↔ Issues/PRs.
 e) „Nicht-Ziele v1“ dokumentieren (z. B. Inkassoübergabe, SMS, KI-Scoring).

Event/Outbox Policy

- Verbindliche Richtlinie: docs/event_outbox_policy.md (Versionierung, Idempotenz, DLQ-Handling, Retention).

Nächster Review-Punkt

- Sonntag, 20:00 Uhr (Inbox & Parsing-Design, Paket A/B/C Status).