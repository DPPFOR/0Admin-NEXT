🔄 Beziehungen und Überschneidungen
Datei	Geltungsbereich	Inhalt	Verändert sich häufig?	Wird referenziert von
.cursor/rules/policy.mdc	global, dauerhaft	Gesetze & Verbote	selten	agents.mdc, Issue-Templates
.cursor/rules/agents.mdc	global, entwicklungsbezogen	Methoden & Best Practices	mittel	Issue-Templates
.cursor/rules/issue-template.mdc	pro Issue	operative Aufgabenbeschreibung	bei jedem Task neu	—

Überschneidung:

agents.mdc und policy.mdc teilen kein Regel-Duplicate, sondern bilden ein Stack:
Policy = „was ist erlaubt“ → Agents = „wie wird’s gemacht“.

Das Issue-Template bezieht sich auf beide und liefert Kontext + Scope + Tests.

4️⃣ Empfohlene Kombination für 0Admin-NEXT

Behalte alle drei – sie ergänzen sich perfekt:
 • policy.mdc = feste Compliance-Schicht
 • agents.mdc = operative Arbeitslogik
 • issue-template.mdc = standardisierter Task-Input für Copilot / Codex / Cursor

Workflow:
 • Du (als Architekt) formulierst ein neues Issue nach dem Template.
 • Der Agent liest zuerst policy.mdc → dann agents.mdc → dann das Issue.
 • So entsteht ein konsistenter, CI-konformer Prompt-Kontext.

Priorität bei Konflikten:
 1️⃣ Policy → 2️⃣ Agents → 3️⃣ Issue

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