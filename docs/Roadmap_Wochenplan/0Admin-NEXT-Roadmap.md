## 🧭 Meilenstein 1 – **Inbox & Dateneingang**

**Ziel:** Alle Kundendaten (E-Mails, Dateien, Uploads) laufen strukturiert in das System.  
**Umfang:**  
  a. Projektgrundlagen, Repo-Struktur, Policies, Pip-Setup  
  b. Inbox-Pipelines (Mail, Upload, API)  
  c. Chunking & Parsing-Flow (Rechnungserkennung, Metadaten)  
  d. PostgreSQL-Schema + Alembic-Migrationen  
  e. Data-Validierung & Audit-Logs  
**Ergebnis:** Daten aus verschiedenen Quellen landen normalisiert und versioniert in PostgreSQL.

## ⚙️ Meilenstein 2 – **Core & Event-Driven Basis**

**Ziel:** Das System reagiert auf Ereignisse statt auf direkte Aufrufe.  
**Umfang:**  
  a. Outbox-Pattern & Event-Logik (Atomarität, Retries, Dead-Letters)  
  b. Repository-Pattern & Domain-Modelle  
  c. Flock-Agenten-Grundrollen (Planer, Sender, Payment, SLA)  
  d. Logging + Monitoring-Grundstruktur (Trace-ID, JSON-Logs, Health)  
  e. MS Graph-Integration (E-Mail, Calendar Light)  
**Ergebnis:** Events fließen durch das System, Agenten reagieren asynchron, erste Mahnzyklen laufen simuliert.
## 💼 Meilenstein 3 – **Mahnwesen Automation v1**

**Ziel:** Automatische Mahnläufe mit echten Daten und mandantenbezogener Logik.  
**Umfang:**  
  a. Domain-Programm für Reminder (Stufen, Fristen, Kommunikation)  
  b. Flock-Agenten live (Detection, Planer, Benachrichtigung, Payment)  
  c. Multi-Tenant-Fähigkeit (tenant_id, Policies, Templates pro Mandant)  
  d. E-Mail-Versand über Brevo mit Zustellnachweis  
  e. Minimal-Frontend zur Überwachung (Pipeline, Fehler, Eskalationen)  
**Ergebnis:** Ein vollständiger, automatisierter Mahnzyklus läuft End-to-End vom Input bis zum Versand.
## 🧩 Meilenstein 4 – **Ops, Tests & Skalierung**

**Ziel:** Stabilität, Nachvollziehbarkeit, und CI/CD-Reife.  
**Umfang:**  
  a. Test-Coverage ≥80 % Domain, Contract-Tests für Events  
  b. Automatisiertes Monitoring, Dead-Letter-Jobs, Alerting  
  c. CI-Checks (Pytest, Lint, Alembic, Coverage)  
  d. Branch-Protection & Required-Status-Checks  
  e. Dokumentation, Templates, Audit- und Retention-Policies  
**Ergebnis:** Produktionsreifes Backend mit laufender Überwachung und Deployment-Sicherheit.

---

1. Roadmap-Start & Repo-Grundlagen (Root)  
	    a. Projektstruktur anlegen (backend/, agents/, data/, docs/, tools/)  
	    b. Python 3.12, pip-only, requirements/requirements-dev trennen  
	    c. README-first-Regel verankern (jede Hauptebene mit Kurz-README)  
	    d. Coding-Agent-Policy aktiv, Schreibfreigaben nur nach GO  
	    e. Versionierung/Changelog in docs/roadmap.md (lebendiges Dokument)  
2. Backend-Skelett & Kernprinzipien  
	    a. Layering: domain/, application/, infrastructure/ (ohne Implementierungsdetails)  
	    b. Dependency Injection (Constructor), keine Globals  
	    c. Unit-of-Work-Konzept definieren (Transaktionsgrenzen)  
	    d. Event-Driven-Basis mit Outbox (noch ohne Worker)  
	    e. Grund-Exceptions, Logging-Contract (JSON-Felder: trace_id, tenant_id)  
3. Inbox als primärer Dateneingang (vor Multi-Tenant)  
	    a. Quellen: E-Mail-Weiterleitung, Drag&Drop, Datei-Upload, API  
	    b. Dateitypen: PDF, PNG/JPG, CSV/XLSX, XML/JSON  
	    c. Normalisierungs-Flow definieren (Store+Meta, kein Parsing in diesem Schritt)  
	    d. Quarantäne/Validierung: Format, Größe, Mandantenmarker optional  
	    e. Minimal-Frontend: Upload, Status, Fehleranzeige  
4. Parsing & Chunking-Pipeline  
	    a. Dokumentklassifikation (Rechnung, Zahlung, Sonstiges)  
	    b. Extraktion strukturierter Felder (Rechnungsnummer, Betrag, Fälligkeit)  
	    c. Chunking-Regeln (Seiten/Abschnitte, Referenzen zu Originalen)  
	    d. Fehlerfälle markieren, manuelle Nacharbeitungspfad definieren  
	    e. Persistenz von Extraktions-Logs (Audit)  
5. PostgreSQL-Grundschema & Alembic  
	    a. Tabellen: invoices, customers, reminders, inbox_items, parsed_items, eventlog, outbox, processed_events, dead_letters  
	    b. Indizes/Keys (invoice_id, customer_id, status, created_at)  
	    c. Alembic-only-Policy, Upgrade/Downgrade-Checkliste  
	    d. Seed-/Demo-Datenpfad (data/) festlegen  
	    e. Naming-Konventionen (snake_case, fk__)  
6. Datenzugriff & Domänenkontrakte  
	    a. Repository-Interfaces (Invoice, Reminder, Inbox, Event)  
	    b. Application-Commands/Queries (ohne Implementierung)  
	    c. Domain-Modelle (Invoice, Reminder, PaymentEvent) beschreiben  
	    d. Idempotency-Keys-Politik definieren  
	    e. Transaktions-DoD: Write + Outbox atomar  
7. Outbox/Eventing-Grundlage (noch ohne Worker)  
	    a. Event-Felder: event_type, schema_version, tenant_hint (optional), trace_id, idempotency_key  
	    b. Status-States: pending, processing, sent, failed  
	    c. Retry-Strategie als Policy (Backoff-Stufen)  
	    d. Dead-Letter-Kriterien textlich festlegen  
	    e. Event-Versionierungsregeln (SemVer)  
8. Microsoft Graph Einführung (E-Mail/Calendar – minimal)  
	    a. Mail: Entwurf+Senden für Mahnungen (Tenant-Postfächer oder App-Only)  
	    b. Calendar: Wiedervorlagen/Follow-ups als Termine  
	    c. Ablage: OneDrive/SharePoint-Ordnerstruktur (pro Kunde/Rechnung)  
	    d. Scopes/Least-Privilege-Policy definieren  
	    e. Audit-/Nachweisprinzip (Message-Id, Send-Status)  
9. Flock-Agenten (eventgetrieben) – Rollen & Schnittstellen  
	    a. Eingangs-Detektor (überfällige Fälle, „ReminderNeeded“)  
	    b. Reminder-Planer (Stufe/Gebühr/Next-Action, schreibt Domain-Event)  
	    c. Benachrichtigungs-Agent (Kanalwahl, Vorlage referenzieren, Versandauftrag)  
	    d. Zahlungsabgleich-Agent (PaymentEvents konsumieren, Fälle schließen/pausieren)  
	    e. Eskalations-Agent (späte Stufen, Telefon/Brief/RA)  
	    f. SLA/Monitoring-Agent (Lag, Fehler, Durchlaufzeiten; Alerts)  
10. Multi-Tenant-Fähigkeit (nach Grundlagen)  
	    a. Tenant-Policy: kein Fallback, Pflichtkennzeichnung in Requests/Events  
	    b. Datenmodell: tenant_id in fachlichen Tabellen, spätere RLS-Einführung vorgesehen  
	    c. Tenant-Config (Fristen, Gebühren, Kanäle) konzeptionell beschreiben  
	    d. Vorlagen/Branding pro Tenant (nur Policy, keine Umsetzung)  
	    e. Rechte-/Rollenmodell skizzieren (Sachbearbeiter, Admin)  
11. Mahnwesen-Domänenprogramm (v1, ohne Technik)  
	    a. Stufenmodell: Soft → M1 → M2 → Letzte → Eskalation (Eintrittsbedingungen)  
	    b. Gebühren-/Fristenregeln als Richtlinie (überschreibbar pro Tenant)  
	    c. Kommunikationsregeln: Sendezeit, Kanalpräferenzen, Double-Opt-In/Out  
	    d. Fehler-/Sonderfälle: Widerspruch, Teilzahlung, unklare Zuordnung  
	    e. Dokumentations-/Ablageprinzip für jede Stufe  
12. E-Mail-Versand über Drittanbieter (Brevo)  
	    a. Einsatzbereiche: operative Mahnungen, Transaktionsmails  
	    b. Absender-/Domain-Setup (SPF/DKIM, Tracking-Optik)  
	    c. Zustellnachweis/Events (Delivered, Bounce, Complaint) als Statusquelle  
	    d. Rate-Limits/Throttling-Policy  
	    e. Datenschutz-/Opt-Out-Richtlinien  
13. Monitoring & Dead-Letter-Job (automatisiert)  
	    a. Kennzahlen: events_processed, failures_total, publisher_lag, dlq_size, reminder_cycle_time  
	    b. Alerts: DLQ-Alter, Lag-Schwellen, Fehlerrate pro Agent  
	    c. Dead-Letter-Replay-Policy (manuell mit Freigabe)  
	    d. Health-/Readiness-Definitionen (Services, Agents)  
	    e. Betriebs-Runbook (Störungen, Eskalation)  
14. Tests & Coverage-Lücken schließen  
	    a. Testpyramide: Domain-Unit ≥80 %, Application-Integration, E2E-Flows  
	    b. Contract-Tests für Event-Typen (Producer/Consumer)  
	    c. Fake-Connectors (Graph/Brevo) für Testszenarien  
	    d. Data-Fixtures (in data/) für Mahn-Flows  
	    e. Abnahme-Checklisten je Arbeitspaket (Meta-DoD)  
15. CI & Required Checks (nach Grundgerüst)  
	    a. Pipelines: pytest, lint, mypy, alembic up/down smoke  
	    b. Coverage-Gates (Domain), Artefakte hochladen (Berichte)  
	    c. Branch-Schutz: PR erforderlich, Checks required  
	    d. Draft-PR-Flow für Coding-Agents (Nightly)  
	    e. Issue-Labels/Meilensteine (Backlog-Steuerung)  
16. Vorlagen & Content-Governance (Mahnwesen)  
	    a. Template-Katalog (Sprachen, Stufen, Branding-Platzhalter)  
	    b. Genehmigungsprozess (Vier-Augen für rechtliche Änderungen)  
	    c. Versionierung/Archivierung von Vorlagen  
	    d. Preview-/Plausibilitäts-Check (Platzhalter vollständig)  
	    e. Kommunikations-Historie referenzierbar im Fall  
17. API-Konnektoren (priorisiert, Meta-Definition)  
	    a. finAPI/Konteninformationen für PaymentEvents (später aktivieren)  
	    b. Druck/Briefdienst für letzte Mahnung/Eskalation  
	    c. ERP/Buchhaltung (Export/Import-Schnittstellen)  
	    d. Webhook-/Polling-Strategien pro Connector  
	    e. Versionierung/Namensregeln für externe APIs  
18. Frontend-Integration (minimum viable)  
	    a. Pipeline-Übersicht (Statusspalten, Filter)  
	    b. Fall-Detail (Timeline, Aktionen Pausieren/Eskalieren/Schließen)  
	    c. Arbeitslisten („Heute fällig“, „Eskalieren“, „Fehler/DLQ“)  
	    d. Einstellungen (Basispolicies, Kanalpräferenzen)  
	    e. Accessibility/Performance-Grundsätze  
19. Backlog-Aufbau & Planungstakt  
	    a. Aus Punkten 3–18 konkrete Issues ableiten (S/M)  
	    b. Abend-Runs: klar begrenzte Issues für Coding-Agent, Draft-PR only  
	    c. Wöchentlicher Roadmap-Review, nur additive Änderungen  
	    d. Verlinkung zwischen roadmap.md ↔ ROADMAPs ↔ Issues/PRs  
	    e. „Nicht-Ziele v1“ festhalten (z. B. Inkassoübergabe, SMS, KI-Scoring)