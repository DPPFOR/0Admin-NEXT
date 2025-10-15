backend/core/specification.md
📘 Modul: Core (Querschnittskomponenten)
🎯 Zweck

core/ bündelt technische Querschnittsdienste, die von allen Produktmodulen genutzt werden:
Event- und Outbox-Infrastruktur, Dokumenterzeugung, Nummernkreise, Kalender/Feiertage sowie AuthN/Z-Grundlagen.
Der Core ist produktneutral, agentenneutral und UI-unabhängig.

🧱 Strukturüberblick
backend/core/
├── eventstore/   → Persistenter Ereignislog (Append-only, Replay)
├── outbox/       → Zustell-Queue für System-Events (Agenten/Integrationen)
├── documents/    → PDF/Template-Engine, Render-Pipeline
├── numbering/    → Nummernkreise, Reservierung & Commit
├── holidays/     → Feiertage, Zahlungsfristen, Fälligkeiten
└── auth/         → Benutzer, Rollen, simple Tokens (Basis)

🧩 Verantwortungsbereiche pro Komponente
1) eventstore/
- Zweck: auditierbare Speicherung fachlicher Ereignisse (immutable).
- Funktionen: append(event), replay(filter), get_by_aggregate(aggregate_id).
- Eigenschaften: append-only, versioniert, idempotenzgesichert (event_id + trace_id).
- Verwendung: Produktsysteme schreiben Domain-Events; Ops/Analyse liest Replays.

2) outbox/
- Zweck: geordnete Weitergabe von System-Events an außerhalb des Backends (z. B. Agents).
- Funktionen: enqueue(topic, payload, headers), dequeue(batch), mark_delivered(id), retry(id).
- Eigenschaften: At-least-once Delivery, dedup via (topic, key), Lease/Visibility-Timeout.
- Verwendung: Produkte legen „Dispatch-Events“ ab; Agents konsumieren.

3) documents/
- Zweck: einheitliche PDF-/Dokumenterstellung (HTML-Templates + Renderer).
- Funktionen: render(template_id, data) -> pdf_path, Asset-Handling, Versionierung.
- Eigenschaften: deterministische Builds (gleiches Input → gleiches Output-Hash).
- Verwendung: Angebote/Rechnungen/Mahnungen, Belege, Reports.

4) numbering/
- Zweck: zentrale Nummernkreise (z. B. Rechnung, Mahnung, Kunde).
- Funktionen: reserve(series, tenant) -> token, commit(token), release(token).
- Eigenschaften: Race-safe (Transaktion/Lock), Vorabreservierung, Formatregeln.
- Verwendung: Vergabe finaler Belegnummern in erechnung/mahnwesen.

5) holidays/
- Zweck: Berechnung von Fälligkeiten/Fristen unter Berücksichtigung von Wochenenden/Feiertagen.
- Funktionen: is_business_day(date, region), add_business_days(date,n,region).
- Eigenschaften: Regionstabellen, Caching, deterministische Regeln.
- Verwendung: Zahlungsziele, Mahnstufen, Skonto-/Verzugstage.

6) auth/
- Zweck: Basismechanismen für Benutzer/Rollen/Zugriffspfade (kein vollständiges IAM).
- Funktionen: authenticate(credentials), authorize(subject, action, resource).
- Eigenschaften: einfache Token/JWT-Verifikation, Rollenlabels, Auditing-Hooks.
- Verwendung: API-Absicherung im Backend; kein direkter Bezug zu Agents.

🔗 Import- & Kopplungsregeln
- Core importiert keine Produktmodule.
- Produkte importieren Core (eventstore/outbox/documents/…); keine Querimporte zwischen Produkten.
- Agents sehen nur Outbox-/Eventstore-Schnittstellen via API/DTOs, keine direkten Core-Imports.

📡 Öffentliche Core-Schnittstellen (Pydantic-DTO, Auszug)
Event:
Event:
  id: UUID
  aggregate_id: UUID
  type: str
  occurred_at: datetime
  payload: dict
  trace_id: str

OutboxMessage:
  id: UUID
  topic: str
  key: str
  payload: dict
  headers: dict
  visible_at: datetime
  delivered_at: datetime|null
  delivery_attempts: int
  trace_id: str

DocumentJob:
  template_id: str
  data: dict
  output_path: str
  hash: str

NumberReservation:
  token: str
  series: str
  next_value_preview: str
  expires_at: datetime

BusinessDayRequest:
  date: date
  region: str


🧩 Ereignistypen (Beispiele, genutzt von Produkten)
| Event-Typ                | Quelle (Produkt) | Zweck                          |
| ------------------------ | ---------------- | ------------------------------ |
| `invoice.issued`         | erechnung         | Finale Belegerstellung         |
| `mahnwesen.notice.created` | mahnwesen          | Mahndokument erzeugt           |
| `payment.received`       | bankfin/später   | Zahlungseingang verbucht       |
| `document.rendered`      | documents        | PDF/Paket erfolgreich erstellt |



🔐 Policies & Nicht-Ziele
- pip-only, Python 3.12, keine alternativen Toolchains.
- Core persistiert keine UI-Zustände, keine Agenten-IDs, keine modulefremden Regeln.
- Outbox/Eventstore sind separat von Business-Transaktionen abzusichern (Transaktionsgrenzen definieren).
- Idempotenz überall: gleiche trace_id + gleicher Schlüssel ⇒ kein Duplikateffekt.

🧪 Teststrategie
- Unit (pro Komponente):
    - eventstore: append/replay, Ordering, Filter
    - outbox: enqueue/dequeue/lease/retry, dedup, visibility timeout
    - documents: Template → PDF Hash-Gleichheit
    - numbering: Parallelreservierung, commit/release
    - holidays: Randfälle (Jahreswechsel, regionale Ausnahmen)
    - auth: Rollenpfade, neg./pos. Fälle

- Integration: Core↔Produkt über öffentliche Interfaces, Outbox-to-Agent-Mock.
- Determinismus: gleiche Inputs → gleiche Outputs (Hash, Reihenfolge).
- Fehlerpfade: Netzwerk-/Rendererfehler simulieren, Retry/Backoff belegen.

🗃️ Persistenz & Tabellen (vereinfachter Auszug)
-- eventstore
events(id PK, aggregate_id, type, occurred_at, payload_json, trace_id, version)

-- outbox
outbox_messages(id PK, topic, key, payload_json, headers_json,
                visible_at, delivered_at NULL, delivery_attempts, trace_id)

-- documents
documents(id PK, template_id, hash, output_path, created_at, meta_json)

-- numbering
number_series(series PK, last_value, format, tenant_id)
number_reservations(token PK, series, reserved_value, expires_at, tenant_id)

-- holidays (regionale Kalendertage)
holiday_calendar(region, date, is_business_day)


🚦 Akzeptanzkriterien (Definition of Done)
- Eventstore garantiert append-only und stabile Reihenfolge pro aggregate_id.
- Outbox liefert at-least-once, mit dedup auf (topic,key) und sichtbaren Retries.
- Documents rendert deterministisch (identischer Hash bei gleichen Inputs).
- Numbering ist race-safe (Reservierung/Commit), keine Doppelnummern.
- Holidays liefert korrekte Business-Day-Berechnungen pro Region.
- Auth erlaubt minimale Absicherung (kein vollständiges IAM), mit klaren Erweiterungspunkten.
- Alle Core-Komponenten besitzen Unit- & Integrationstests (grün, deterministisch).

🔧 Erweiterbarkeit
- Austauschbarer Store (z. B. Postgres/SQLite) hinter Eventstore/Outbox-Interface.
- Erweiterte Dokument-Pipeline (Hybrid-PDF, Signaturen, Stempel).
- Mehrmandantenfähige Nummernkreise & Serienregeln.
- Regionale/branchenspezifische Feiertagsmodule.
- Delegation von Auth an externes IAM (OIDC/OAuth2) – Core bleibt schlank.