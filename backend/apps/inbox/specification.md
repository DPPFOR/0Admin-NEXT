# backend/apps/inbox/specification.md
# Inbox Specification

# Zweck & Scope
- Die Inbox ist die zentrale Eintrittsstelle für alle eingehenden Dokumente (E-Mail, Upload, API). Sie übernimmt die strukturierte Erfassung, Validierung und Aufbereitung der Daten für nachgelagerte Prozesse.
- Nicht Bestandteil: Parsing-Heuristiken, OCR oder KI-Klassifikation – diese folgen nach Stabilisierung der Basispipeline.

# Begriffe & Annahmen
- Inbox-Item: Ein eingegangenes Artefakt (Datei oder Mail-Anhang) mit URI, Hash und Metadaten.
- Parsing: Prozess der inhaltlichen Extraktion (z. B. Rechnungsnummer, Betrag).
- Chunk: Logisch abgegrenzter Abschnitt eines Dokuments (optional).
- Fehlerklasse: Eindeutiger Typ eines technischen oder fachlichen Fehlers, der Wiederholbarkeit und Eskalationspfad bestimmt.

Zustände
1. received
- Zweck: Eingang eines Dokuments wurde erkannt und registriert.
- Eingangsbedingungen: URI und tenant_id vorhanden; Datei erreichbar.
- Arbeitsinhalt: Basis-Metadaten erfassen (Dateiname, Quelle, Hash).
- Ausgangsbedingungen: content_hash berechnet, Audit-Trail begonnen.
- Folgestatus: validated.
- Event: InboxItemReceived (optional).
- Fehlerpfade: io_error (Netz/Storage), format_error (unlesbar).

2. validated
- Zweck: Technische und semantische Validierung des Dokuments.
- Eingangsbedingungen: received erfolgreich; MIME-Typ und Größe bekannt.
- Arbeitsinhalt: Prüfung auf Duplikate (tenant_id, content_hash); Format- und Größenkontrolle; Plausibilitätscheck.
- Ausgangsbedingungen: Validierung bestanden, Parser bestimmbar.
- Folgestatus: parsed oder error.
- Event: InboxItemValidated.
- Fehlerpfade: size_limit, unsupported_mime, hash_duplicate.

3. parsed
- Zweck: Strukturierte Extraktion der Inhalte.
- Eingangsbedingungen: Validierung erfolgreich, Parser verfügbar.
- Arbeitsinhalt: Bestimmung des doc_type; Erzeugung von payload_json; optionale Erstellung von Chunks.
- Ausgangsbedingungen: payload_json vollständig; Referenzen zu Originaldatei/Chunks gesetzt.
- Folgestatus: keiner (Terminalzustand).
- Event: InboxItemParsed.
- Fehlerpfade: parser_error, io_error.

4. error
- Zweck: Abbildung von Fehlern, die den Flow abbrechen.
- Eingangsbedingungen: Fehlerklasse erkannt.
- Arbeitsinhalt: Fehlerprotokollierung, Klassifizierung nach Retrybarkeit, Eskalationspfad hinterlegen.
- Ausgangsbedingungen: Fehler dokumentiert, Event ausgelöst.
- Event: InboxItemFailed.
- Folgestatus: keiner (Terminalzustand).

Übergänge
| Von       | Nach      | Vorbedingungen                         | Nachbedingungen                                | Event              |
| :-------- | :-------- | :------------------------------------- | :--------------------------------------------- | :----------------- |
| received  | validated | URI lesbar, tenant_id + Hash vorhanden | Validierung durchgeführt, kein Duplikat        | InboxItemValidated |
| validated | parsed    | Validierung erfolgreich                | Parsing abgeschlossen, payload_json erstellt   | InboxItemParsed    |
| *         | error     | Fehler erkannt                         | Fehler dokumentiert, Wiederholbarkeit markiert | InboxItemFailed    |

Fehlerklassen & Maßnahmen
| Klasse           | Beschreibung                    | Retry    | Maßnahme                     |
| :--------------- | :------------------------------ | :------- | :--------------------------- |
| format_error     | Datei unlesbar oder beschädigt  | Nein     | Manuelle Prüfung             |
| size_limit       | Datei überschreitet Größenlimit | Bedingt  | Policy prüfen                |
| unsupported_mime | Nicht unterstütztes Format      | Nein     | Whitelist erweitern          |
| hash_duplicate   | Duplikat je Tenant              | Nein     | Verknüpfung mit Original     |
| io_error         | I/O-Fehler oder Timeout         | Ja       | Retry mit Backoff            |
| parser_error     | Fehler im Parser                | Begrenzt | Retry n-mal, dann Eskalation |

# Datenfluss
- Eingang: Registrierung eines neuen Artefakts mit tenant_id, URI, content_hash.
- Normalisierung: Standardisierung von Dateinamen und Metadaten.
- Validierung: Technische und semantische Prüfung, Duplicate-Check.
- Parsing: Extraktion strukturierter Felder, Erzeugung von payload_json.
- Persistenz & Events: Schreiben der Datenbankeinträge, Emission der Zustands-Events.

# Definition of Done (DoD)
- Alle vier Zustände vollständig beschrieben.
- Übergänge mit Vor- und Nachbedingungen dokumentiert.
- Fehlerklassen eindeutig klassifiziert, Maßnahmen definiert.
- Datenfluss lückenlos nachvollziehbar.
- Referenzen zu Policies enthalten, keine Duplikation von Regeltext.

# Nicht-Ziele v1
- Keine OCR, kein maschinelles Lernen.
- Keine automatische Wiederverarbeitung ohne Freigabe.
- Keine Performance-Optimierung oder JSONB-Indexierung.

# Referenzen
- .cursor/rules/Coding-Agent-Policy.mdc – operative Leitplanken.
- docs/event_outbox_policy.md – Event-Versionierung und Idempotency.
- docs/meta-rules.md – Baseline-Regeln, UTC, Naming-Konventionen.

# Tabellenübersicht
- inbox_items  
- parsed_items  
- chunks (optional, nach Parsing)

# Tabellenbeschreibung
## inbox_items
- Zweck: Speicherung eingehender Artefakte mit minimaler Metadatenbasis.  
- Primärschlüssel: id UUID DEFAULT gen_random_uuid().  
- Felder:
  - tenant_id UUID NOT NULL  
  - source VARCHAR(64) NOT NULL  
  - filename VARCHAR(255)  
  - status VARCHAR(32) CHECK (status IN ('received','validated','parsed','error'))  
  - created_at TIMESTAMPTZ DEFAULT timezone('utc', now())  
  - content_hash CHAR(64) NOT NULL  
  - uri TEXT NOT NULL  
- Constraints:
  - PRIMARY KEY (id)  
  - UNIQUE (tenant_id, content_hash)  
  - CHECK ck_inbox_items__status_valid  
- Indizes:
  - (tenant_id, created_at)  
  - (tenant_id, status)

## parsed_items
- Zweck: Ergebnisstruktur nach erfolgreichem Parsing eines Inbox-Items.  
- Primärschlüssel: id UUID DEFAULT gen_random_uuid().  
- Felder:
  - tenant_id UUID NOT NULL  
  - inbox_item_id UUID NOT NULL  
  - doc_type VARCHAR(64) NOT NULL  
  - payload_json JSONB NOT NULL  
  - created_at TIMESTAMPTZ DEFAULT timezone('utc', now())  
- Constraints:
  - PRIMARY KEY (id)  
  - FOREIGN KEY (inbox_item_id) REFERENCES inbox_items(id) ON DELETE CASCADE  
  - CHECK ck_parsed_items__doc_type_valid  
- Indizes:
  - (tenant_id, inbox_item_id)  
  - (tenant_id, created_at)

## chunks (optional)
- Zweck: Speicherung von Dokumentabschnitten nach Parsing.  
- Primärschlüssel: id UUID DEFAULT gen_random_uuid().  
- Felder:
  - tenant_id UUID NOT NULL  
  - parsed_item_id UUID NOT NULL  
  - seq_no INT NOT NULL  
  - text TEXT NOT NULL  
  - token_count INT  
- Constraints:
  - PRIMARY KEY (id)  
  - FOREIGN KEY (parsed_item_id) REFERENCES parsed_items(id) ON DELETE CASCADE  
  - UNIQUE (tenant_id, parsed_item_id, seq_no)  
- Indizes:
  - (tenant_id, parsed_item_id)
  - (tenant_id, seq_no)

# Naming-Konventionen
- pk_%(table_name)s  
- fk_%(table_name)s__%(referred_table_name)s  
- uq_%(table_name)s__%(column_0_name)s  
- ix_%(table_name)s__%(column_0_name)s  
- ck_%(table_name)s__%(constraint_name)s  

# ON DELETE-Strategie
- parsed_items → inbox_items: ON DELETE CASCADE  
- chunks → parsed_items: ON DELETE CASCADE  
- Outbox-bezogene Tabellen (nicht Teil dieser Datei): kein CASCADE  

# Idempotenz & Duplikatvermeidung
- Eindeutigkeit durch (tenant_id, content_hash).  
- Keine Re-Insert-Versuche bei bestehendem Hash.  
- Events referenzieren die ursprüngliche ID, nicht die Hash-Kombination.

# Risiken & Maßnahmen
- Über-Indexierung bei kleinen Mandanten möglich → CI-Review nach Query-Pattern.  
- Unter-Indexierung bei wachsender Tenants-Zahl → Nightly-Planung für Optimierungen.  
- JSONB-Indizes erst nach Stabilisierung der Zugriffspfade aktivieren.