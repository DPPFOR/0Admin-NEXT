# Diese Datei definiert verbindliche Regeln für Events, Outbox, Retries und Dead-Letter-Handling.
Gilt für alle Worker, Scheduler und Flock-Agenten. Änderungen nur durch den Architekten.

vollständigen, konsistenten Stack aus vier Policy-Ebenen:
1️⃣ Policy („Gesetzbuch“)
2️⃣ Agents („Leitfaden“)
3️⃣ Issue-Template („Mission Brief“)
4️⃣ Event-Outbox-Policy („Technische Leitlinie“)

🔄 Beziehungen und Überschneidungen
Datei	Geltungsbereich	Inhalt	Verändert sich häufig?	Wird referenziert von
.cursor/rules/policy.mdc	global, dauerhaft	Gesetze & Verbote	selten	agents.mdc, Issue-Templates
.cursor/rules/agents.mdc	global, entwicklungsbezogen	Methoden & Best Practices	mittel	Issue-Templates
.cursor/rules/issue-template.mdc	pro Issue	operative Aufgabenbeschreibung	bei jedem Task neu	—
.cursor/rules/Event-Outbox-Policy-Ereignisrichtlinie.mdc	systemisch (Events, DLQ)	Event-Schema, Versionierung, Retry/Dead-Letter-Strategie	bei Bedarf (neue Eventtypen)	policy.mdc, agents.mdc, tests/**

Überschneidung:
agents.mdc und policy.mdc teilen kein Regel-Duplicate, sondern bilden ein Stack:
Policy = „was ist erlaubt“ → Agents = „wie wird’s gemacht“.
Die Event-Outbox-Policy erweitert die policy.mdc technisch – sie präzisiert, wie Events strukturiert, versioniert und wiederhergestellt werden.

Das Issue-Template bezieht sich auf beide und liefert Kontext + Scope + Tests.

4️⃣ Empfohlene Kombination für 0Admin-NEXT

Behalte alle vier – sie ergänzen sich perfekt:
 • policy.mdc = feste Compliance-Schicht
 • Event-Outbox-Policy-Ereignisrichtlinien.mdc = erweitert die policy.mdc technisch – sie präzisiert, wie Events strukturiert, versioniert und wiederhergestellt werden.
 • agents.mdc = operative Arbeitslogik
 • issue-template.mdc = standardisierter Task-Input für Copilot / Codex / Cursor


Workflow:
 • Du (als Architekt) formulierst ein neues Issue nach dem Template.
 • Der Agent liest zuerst policy.mdc → dann agents.mdc → dann das Issue.
 • So entsteht ein konsistenter, CI-konformer Prompt-Kontext.

Priorität bei Konflikten:
1️⃣ policy.mdc → 2️⃣ Event-Outbox-Policy → 3️⃣ agents.mdc → 4️⃣ issue-template.mdc

5️⃣ Empfohlene Hinweise

Behalte policy.mdc als oberste Instanz („Gesetzbuch“) unverändert.

Ergänze in agents.mdc ganz oben den Hinweis:
 > „Diese Datei ergänzt die policy.mdc. Bei Konflikt gilt Policy höher.“

Verwende dein neues issue-template.mdc zusätzlich als GitHub-Issue-Template (.github/ISSUE_TEMPLATE/).

Kopple Branch-Protection („PR required + required checks“), damit alle drei Schichten greifen.

1️⃣ policy.mdc → Verbindliche Hausordnung („Gesetzbuch“)

Zweck: Legt unveränderliche Systemregeln für alle Coding-Agents fest.
Inhalt: DDD, Outbox-Worker, Multi-Tenancy, Security, Quality Gates, Enforcement.
Charakter: Stabil, dauerhaft, höchste Autorität.
Analogie: 🧱 Betriebssystem-Policy / Constitution

2️⃣ agents.mdc → Arbeitsstil und Prompt-Kontext („Leitfaden“)

Zweck: Beschreibt, wie ein Agent arbeitet, denkt und promptet.
Inhalt: Prompt-Driven-Development, AAA-Pattern, Table-Driven-Tests, Mocking.
Charakter: Dynamisch, methodisch, entwickelt sich mit der Praxis.
Analogie: 🧩 Developer-Playbook / Arbeitsanweisung

3️⃣ issue-template.mdc → Ausführungs-Briefing („Mission Brief“)

Zweck: Für jedes Coding-Issue (Cursor / Copilot) – enthält alle Infos standalone.
Inhalt: Commit-Scope, Ziel, Pfade, Tests, DoD, Rollback, Sicherheitsheader.
Charakter: Dynamisch, pro Task neu generiert.
Analogie: 📋 Mission Order / Issue-Briefing

4️⃣ event-outbox-policy.mdc → Ereignis- und Wiederherstellungsrichtlinie („Technische Leitlinie“)

Zweck: Definiert die verbindlichen technischen Regeln für Events, Outbox-Verarbeitung, Retries und Dead-Letter-Handling in allen Backend- und Agentenkomponenten.
Inhalt: 
- Strukturvorgaben für Event-Schemas (Pflichtfelder: schema_version, event_type, trace_id, tenant_hint, idempotency_key)
- Regeln zur Versionierung und Abwärtskompatibilität (SemVer, keine Breaking Changes ohne Migrationspfad)
- Standardisierte Retry-Strategie (Backoff: 5 → 30 → 300 s, max. 3 Versuche)
- Dead-Letter-Kriterien und Replay-Verfahren mit Freigabe durch den Architekten
- Pflicht zur Protokollierung (eventlog, outbox, processed_events)
Charakter: Stabil, technisch präzise, ergänzt die policy.mdc um konkrete Durchführungsregeln für Eventing und Wiederherstellung.
Analogie: ⚙️ Kernel-Modul / Systemdienst


