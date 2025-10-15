backend/apps/erechnung/specification.md
📘 Modul: E-Rechnung (erechnung)
🎯 Zweck

Das Modul E-Rechnung erzeugt, validiert und verwaltet elektronische Rechnungen nach gängigen Standards (u. a. XRechnung und ZUGFeRD).
Es stellt konsistente Profile, Nummernkreise, PDF-/XML-Kopplung und Validierungsregeln bereit und integriert Versand und Statusrückmeldungen über die Outbox.

🧩 Verantwortungsbereich
1) Erzeugung standardkonformer XML (XRechnung/ZUGFeRD) aus Domänedaten
2) Validierung gegen Schemas/Regeln (technisch & fachlich)
3) Paketierung (Hybrid: PDF+A/3 mit eingebetteter XML; reines XML)
4) Versionierung & Statusführung (draft, issued, delivered, failed, corrected)
5) Events an Agents (Versand, Archivierung, Korrekturen) über Outbox
6) Import/Mapping externer Datenquellen (optional)

🧭 Systemkontext & Abhängigkeiten

- Input-Quellen:
    - backend/products/mahnwesen (Mahnstatus, Referenz auf Ursprungrechnungen)
    - Kunden-/Artikelstamm, Zahlungsbedingungen (common/core)
Output:
    - XML/PDF-Artefakte und Outbox-Events (z. B. erechnung.issued, erechnung.sent)
Kernabhängigkeiten:
    - core/numbering (Rechnungs- und Korrekturrechnungsnummern)
    - core/documents (PDF-Rendering, Anhänge)
    - core/outbox (Event-Dispatch)
    - core/holidays (Fristen/Termine, falls benötigt)

⚙️ Technische Architektur
Verzeichnisstruktur
backend/apps/erechnung/
├── domain/           → Entitäten, Profile, Policy (Invoice, Profile, Constraints)
├── services/         → UseCases (create_xml, validate, issue, correct, package)
├── repositories/     → Persistenzzugriff, Artefakt- und Statusverwaltung
├── schemas/          → Pydantic-Modelle (Requests/Responses, Profile)
├── api/              → FastAPI-Router (POST /erechnung/issue, GET /erechnung/{id})
├── templates/        → PDF-Layouts, ggf. Hybrid-PDF-Ressourcen
└── specification.md

Hauptkomponenten

- Domain:
    - Invoice, InvoiceLine, Party, Tax, Totals, Profile (XRechnung/ZUGFeRD)
    - Policy/Constraints (z. B. Pflichtfelder, Profile-Switching)
- Services:
    - create_xml(data, profile) → baut standardkonformes XML
    - validate(xml, profile) → Schema- und Regelvalidierung
    - issue(invoice_id) → Nummernkreis, Signaturen/Metadaten, Statuswechsel
    - package(pdf, xml) → PDF/A-Hybrid erstellen (optional)
    - correct(original_invoice_id) → Korrekturrechnung ableiten

Repository:
- persistiert Artefakte, Status, Relation invoice ↔ document/xml

🔄 Ablaufübersicht
Beispiel: „Rechnung ausstellen und versenden“
1) Trigger: API-Call POST /erechnung/issue (oder interner UseCase)
2) Service: create_xml() generiert XML nach gewähltem Profil
3) Service: validate() prüft Schema/Regeln → hard fail bei Verstößen
4) Service: issue() vergibt finale Rechnungsnummer, setzt Status issued
5) Optional: package() erstellt PDF/A-Hybrid (PDF mit eingebetteter XML)
6) Outbox: Event erechnung.issued mit Referenzen auf Artefakte
7) Agent (Flock): Versand über agents/erechnung (Mail/Peppol/Upload)
8) Outbox: erechnung.sent oder erechnung.failed mit Details/Audit

🧪 Teststrategie
- Unit: Profil-Regeln, Betragslogik, Summen/Steuern, XML-Struktur
- Integration: API-Endpoints, Repository, Outbox-Integration
- E2E: Issue → Validate → Package → Send (über Agent-Mock)
- Determinismus: identische Eingaben → byte-identische XML/PDF (Hash-Vergleich)
- Fehlerpfade: ungültige Profile, fehlende Pflichtfelder, Rundungsdifferenzen

🧱 Datenmodelle (Auszug)
Invoice:
  id: UUID
  customer_id: UUID
  issue_date: date
  due_date: date
  currency: str
  lines: InvoiceLine[]
  totals:
    net_amount: Decimal
    tax_amount: Decimal
    gross_amount: Decimal
  profile: Enum("XRechnung", "ZUGFeRD")
  status: Enum("draft", "issued", "delivered", "failed", "corrected")

InvoiceLine:
  id: UUID
  description: str
  quantity: Decimal
  unit_price: Decimal
  tax_rate: Decimal
  net_amount: Decimal
  tax_amount: Decimal
  gross_amount: Decimal

🧩 Events (Outbox)
| Event                | Beschreibung                       | Payload (Beispiel)                                       |
| -------------------- | ---------------------------------- | -------------------------------------------------------- |
| `erechnung.issued`    | Rechnung final erstellt/nummeriert | `{ invoice_id, profile, xml_path, pdf_path?, trace_id }` |
| `erechnung.sent`      | Versand erfolgreich                | `{ invoice_id, channel, recipient, trace_id }`           |
| `erechnung.failed`    | Versand/Validierung fehlgeschlagen | `{ invoice_id, reason, step, trace_id }`                 |
| `erechnung.corrected` | Korrekturrechnung erzeugt          | `{ original_id, correction_id, reason, trace_id }`       |


🧩 Validierung & Profile
- XRechnung: Schema-Validierung (UBL/CIUS-DE), Pflichtfelder (Leistung, Beträge, USt-ID/Steuerbefreiung)
- ZUGFeRD: Profile BASIC/EN16931 (mindestens), strukturidentische Beträge/Steuern
- Rundung & Summen: deterministische Regeln (Banker’s Rounding vermeiden), Differenzen < 0,01 strikt behandeln
- Anhänge: nur erlaubte Anhänge gemäß Profil (z. B. keine willkürlichen Binärdateien)

🔐 Policy & Statusführung
- Zustände: draft → issued → delivered/failed → corrected
- Idempotenz: gleicher Eingabe-Hash + gleicher trace_id → kein zweites Artefakt/Versand
- Korrektur: corrected referenziert original_id, nie rückwirkende Modifikation von issued

🧱 Erweiterbarkeit
- PEPPOL-Anbindung (Agent-seitig) mit Zustell-Quittungen
- Signaturen/Qualifizierte Zeitstempel (falls rechtlich gefordert)
- Multi-Profile (weitere CIUS/Branchenprofile)
- Wechselkurs-/Mehrwährungsfähigkeit
- Import externer Belege (Mapping in internes Modell + Re-Issue)

📋 Definition of Done
- Profile XRechnung und ZUGFeRD erzeugbar und validierbar
- Deterministische XML (Hash-stabil), optional Hybrid-PDF paketiert
- Statusübergänge korrekt & auditierbar, Events in Outbox vollständig
- Unit/Integration/E2E-Tests grün, Fehlerpfade abgedeckt
- Idempotenz-Nachweis (zweiter Lauf mit gleicher trace_id erzeugt keine Doppler)