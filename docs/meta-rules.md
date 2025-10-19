# Meta-Rules (Arbeitsprinzipien) – Go-Live, keine Demos

### Zur Schema-Frage („0admin“ vs. „zero_admin“)
a) PostgreSQL erlaubt führende Ziffern nur bei zitierten Bezeichnern → "0admin"; unzitiert sind Namen mit führender Ziffer nicht gültig.  
b) Konsequenz: Mit "0admin" müssten ORM, Alembic, SQL und search_path überall sauber quoten; das ist fehleranfällig (Case-/Quote-Drift, Tooling-Inkompatibilitäten).  
c) Empfehlung: zero_admin beibehalten. Wenn „0admin“ aus Branding-Gründen zwingend ist, dann als Datenbank-Name oder Präfix in Tabellen/Events nutzen, nicht als Schema.

---

## Zweck
Diese Regeln sichern Architektur-Disziplin und Produktiv-Reife für 0Admin (Go-Live-Produkt, keine Demo-Inhalte).  
Alle hier beschriebenen Punkte gelten als verbindliche Grundlage für alle Coding-Agenten (Cursor/Copilot) und CI-Pipelines.

---

## Prinzipien
- Jede Änderung startet auf Meta-Ebene (Ziel, Scope, Outcome), erst danach Umsetzung.  
- Roadmaps/READMEs sind Source of Truth; Änderungen nur additiv, nichts löschen.  
- Apps importieren nur core/common; niemals app↔app direkt.  
- Events sind versioniert und idempotent; Writes + Outbox atomar.  
- Agenten (Cursor/Copilot) arbeiten ausschließlich gegen genehmigte Aufgaben (Apply: Always).  
- Keine Befehle/Code in Meta-Dokumenten; Umsetzung erfolgt nur durch Coding-Agenten.  

---

## Verbindliche Entscheidungen
- Python 3.12; Paketführung via requirements.txt und requirements-dev.txt.  
- pip-only; Alembic-only für alle Schemaänderungen.  
- Lokal-first Entwicklung; Deployment per scp.  
- Logging: JSON mit Pflichtfeldern trace_id (immer), tenant_id (immer), request_id (nur im HTTP-Kontext).  
- Go-Live-Prämisse: Alle Artefakte sind produktionsreif zu formulieren (keine Demo-/Seed-Inhalte).  

---

## Baseline-Scope & Regeln (Alembic „initial“)
- Schema: zero_admin als eigenes Schema; Trennung von public.  
- Extension: pgcrypto bereitstellen für gen_random_uuid().  
- search_path: zentral zero_admin, public (App-DB-Session und Alembic env.py), nicht pro Migration.  
- Zeit/UTC: TIMESTAMPTZ, DEFAULT timezone('utc', now()).  
- updated_at: DB-seitiger Trigger; Funktion zero_admin.set_updated_at(), Trigger trg_<table>_set_updated_at.  
- Primärschlüssel: id UUID DEFAULT gen_random_uuid() (serverseitig, keine Client-UUIDs).  
- Mandantenfähigkeit: tenant_id UUID Pflicht in allen fachlichen Tabellen.  
- Indizes: Mandanten-First (mindestens (tenant_id, created_at)), keine GIN/JSONB-Indizes in der Baseline.  
- Baseline enthält keine Fachtabellen; nur Schema, Extension, search_path, Trigger-Infrastruktur, Policies.  

---

## Migrations-Policy
- Alembic-only: Keine direkten DDLs am System vorbei.  
- Shadow-Path: Keine destruktiven Changes; Standard ist create → copy → swap → drop.  
- Versionierung: Baseline „initial“, danach „schema_v1_inbox“.  
- Roundtrip: Nightly downgrade base → upgrade head; PR-Pipeline nutzt Drop-&-Recreate einer Test-DB plus alembic upgrade head.  
- Branch-Schutz: Agent-PRs nie direkt auf main; Required Checks aktiv.  

---

## Naming-Konventionen (SQLAlchemy/Alembic)
- PK: pk_%(table_name)s  
- FK: fk_%(table_name)s__%(referred_table_name)s  
- UNIQUE: uq_%(table_name)s__%(column_0_name)s  
- INDEX: ix_%(table_name)s__%(column_0_name)s  
- CHECK: ck_%(table_name)s__%(constraint_name)s (CHECKs stets explizit benennen)  

---

## CI-Vorgaben
- Pytest ≥ 8.3; vor Tests: alembic upgrade head gegen Test-DB (PR-Pipeline).  
- Nightly: Roundtrip downgrade base → upgrade head; Migrations-Check ist Required Check.  
- Alembic-Revisions werden von Black/Ruff per per-file-ignores ausgenommen (Diff-Hygiene).  

---

## Governance & Agenten
- .cursor/rules/Coding-Agent-Policy.mdc hat Priorität „Apply: Always“; Roadmap/README verlinken dorthin.  
- Issues für Agenten müssen Abnahmekriterien (DoD) enthalten; Draft-PR-Flow bis zur Freigabe.  
- Keine Umsetzung ohne explizites „Go“ auf Meta-Ebene.  

---

## Baseline-PR-Checkliste (nur Meta)
- Abschnitt „Baseline-Scope & Regeln“ ist vollständig und konsistent.  
- Verweis auf .cursor/rules/Coding-Agent-Policy.mdc gesetzt (Apply: Always).  
- Liste Baseline-Elemente vollständig: Schema, Extension, search_path, Trigger-Infrastruktur, Policies.  
- Naming-Konventionen dokumentiert; Beispielnamen für CHECK-Constraints vorhanden.  
- CI-Abschnitt (PR vs. Nightly) mit Required Checks klar beschrieben.  
- README/Roadmap nennen die Baseline als nächsten operativen Schritt für Agenten.  
- Keine Befehle/kein Code im PR-Text; ausschließlich Meta-Spezifikation und DoD.  

---

## Outbox & Event-Verknüpfung (Meta)
- Outbox-Tabellen (event_outbox, processed_events, dead_letters) folgen Naming- und Tenant-First-Regel.  
- Jede Fachoperation (Write) erzeugt atomar einen Outbox-Eintrag (Status pending).  
- Statuspfade aus event_outbox_policy.md sind verbindlich; kein lokaler Override.  
- Retry- und Backoff-Mechanik wird zentral über Policies gesteuert, nicht pro App.  
- Alle Event-Namen und Versionierungen müssen schema_version tragen und im CI verifiziert sein.  

---

## Abnahme (Meta)
- Dokumentation aktualisiert (Roadmap/README/Spec) mit kurzer Begründung.  
- Alle Links funktional; .mdc-Referenzen vorhanden.  
- Entscheidungsvorlage angefügt.  

---

## Entscheidungsvorlage: Baseline „initial“ freigeben?
- Ja: Baseline-Scope & Regeln vollständig, CI/Checks konfiguriert, Governance verlinkt.  
- Nein: Fehlende Elemente markieren (welche, warum), neues Zieldatum definieren.  

---

## Verweise
- Coding-Agent-Policy (Apply: Always): [](/.cursor/rules/Coding-Agent-Policy.mdc)  
- Event/Outbox Policy: [](/docs/event_outbox_policy.md)  
