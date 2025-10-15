backend/apps/mahnwesen/specification.md
📘 Modul: Mahnwesen (mahnwesen)
🎯 Zweck

Das Modul Mahnwesen verwaltet alle Schritte des Forderungsmanagements innerhalb von 0Admin.
Es erkennt überfällige Rechnungen, erstellt Mahnschreiben, steuert Versand und Eskalationslogik und interagiert mit Bank- und E-Rechnungsmodulen.

Ziel: vollautomatische Mahnläufe, die nachvollziehbar, konfigurierbar und rechtssicher sind.

🧩 Verantwortungsbereich
Das Modul ist für folgende Teilaufgaben zuständig:
1) Ermittlung überfälliger Rechnungen
2) Berechnung von Mahnstufen und Gebühren
3) Generierung von Mahnschreiben (PDF + eRechnung)
4) Versand per Mail oder Druckdienst (über agents/mahnwesen/)
5) Protokollierung in Outbox + Audit-Log
6) Übergabe an nachgelagerte Workflows (Inkasso, Storno, Zahlungseingang)

🧭 Systemkontext & Abhängigkeiten

- Input-Quelle: backend/apps/erechnung/ (Rechnungsstatus, Zahlungseingänge)
- Output: Outbox-Einträge für Agenten (z. B. Mahn-Mail, Kalendereintrag, Export)
- Event-Publisher: core/outbox
- Template-Engine: backend/core/documents (PDF-Layout)
- Datengrundlage: core/numbering (für Mahnnummern), core/holidays (Fälligkeiten)

⚙️ Technische Architektur
Verzeichnisstruktur
backend/apps/mahnwesen/
├── domain/           → Entitäten, Regeln (Invoice, DunningCase, DunningStage)
├── services/         → UseCases (find_overdues, create_notice, escalate_case)
├── repositories/     → DB-Queries, Mapping, Filterlogik
├── schemas/          → Pydantic-Modelle für Requests/Responses
├── api/              → FastAPI-Router (GET /mahnwesen, POST /mahnwesen/run)
├── templates/        → PDF/Email-Layouts
└── specification.md

Hauptkomponenten
- Domain: definiert die Entitäten und Mahnlogik (Invoice, DunningCase, Stage).
- Service-Layer: steuert Workflows und orchestriert Repository-Aufrufe.
- Repository: abstrahiert die Datenhaltung (SQLAlchemy, Async).
- API: REST-Endpunkte zur manuellen oder automatisierten Mahnauslösung.

🔄 Ablaufübersicht
Beispiel: automatischer Mahnlauf

1) Trigger: Scheduler oder CLI (tools/cli/mahnwesen-inspect) startet Prozess.
2) Service: find_overdues() sucht Rechnungen mit due_date < today.
3) Domain-Regel: Ermittelt stage anhand letzter Mahnung + Tageüberfälligkeit.
4) Service: create_notice() erstellt Mahndokument (PDF + JSON-Payload).
5) Outbox: Nachricht notice.created wird mit Payload gespeichert.
6) Agent (Flock): agents/mahnwesen/workers/notice_dispatcher sendet E-Mail.
7) Audit: Eintrag im Eventstore mit trace_id + Status sent.

🧪 Teststrategie

- Unit-Tests: Domain-Regeln, Gebührenberechnung
- Integrationstests: API-Endpunkte, Outbox-Verknüpfung
- E2E-Tests: Vollständiger Mahnlauf inkl. PDF-Erzeugung + Versandmock
- Alle Tests laufen mit pytest -W error und müssen deterministisch sein

🧱 Datenmodelle (Auszug)
DunningCase:
  id: UUID
  invoice_id: UUID
  customer_id: UUID
  stage: int
  due_date: date
  last_notice_at: datetime
  status: Enum("open", "escalated", "closed")


🧩 Events (Outbox)
Event	Beschreibung	Payload
notice.created	Mahnung wurde erstellt	{ case_id, stage, pdf_path, recipient }
notice.sent	Versand erfolgreich	{ case_id, recipient, channel, trace_id }
notice.failed	Versand fehlgeschlagen	{ case_id, reason, retry_count }
🧱 Erweiterbarkeit

weitere Eskalationsstufen (Stage 4+: Inkasso)
- SMS- oder Briefversand-Agent
- KI-Bewertung von Zahlungsausfällen (später via agents/scoring/)

📋 Definition of Done
- Alle Stages (1–3) abbildbar
- PDF-Template-Rendering und Outbox-Dispatch laufen grün
- Revisionsfähig (Migration reversibel)
- Alle Tests grün (unit/integration/e2e)
- Idempotente Mahnläufe (gleiche trace_id → keine Dopplung)