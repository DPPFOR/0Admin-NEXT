# Coding-Agenten (Cursor und Github Copilot Coding-Agent)
Diese drei Unterlage sind durch zu lesen und haben Schreibverbot:

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


# [PROMPT-Template] für OPENAI-Extension:

Interner Merker (für mich, nicht in den Prompt kopieren):
Immer einen Standalone-Prompt liefern (alles Nötige drin, keine externen Verweise).
Ausführen bevorzugt im Devcontainer. Falls kein .devcontainer vorhanden ist, führe alles lokal in .venv (Python 3.12) aus. Brich nur ab, wenn Python 3.12/pip fehlen. Keine globalen Host-Installationen außer apt für python3.12/python3-pip. nur pip, Python 3.12, Tests am Ende automatisch.
Vollständige Logs + ein einziger Unified-Diff, keine Commits.
Wenn DB nötig: nur nutzen, wenn DATABASE_URL gesetzt; sonst sauber skippen.

Richtlinie:
- Bevorzugt im VS-Code-Devcontainer ausführen. **Wenn kein `.devcontainer/` vorhanden ist:** lokal im Repo arbeiten.
- Lokal: ausschließlich in einem **.venv** mit **Python 3.12.x** und **pip** (kein uv/poetry/conda). Wenn Python 3.12 fehlt, weise kurz auf `sudo apt install python3.12 python3.12-venv python3-pip` hin und brich mit sauberer Meldung ab.
- **Keine globalen** Host-Installationen außer dem genannten apt-Schritt für Python/Pip.
- **Kein Commit/Push**. Änderungen nur als Diff-Vorschlag anzeigen (Unified-Diff) und Dateien im Arbeitsbaum anlegen/anpassen – aber **nicht** committen.
- **Vollständige Terminal-Logs** aller ausgeführten Schritte am Ende zeigen (Kommando → Output).
- **Reproduzierbarkeit:** benutze ausschließlich die projektseitigen Versionen/Lockfiles (requirements*). Falls etwas fehlt, melde es und brich ab.
- Multi-Tenant, Flock-Kontext und MCP-Artefakt-Pfadlogik **nicht verändern**, nur nutzen, wo nötig.


AUTOMATISCHE ABSCHLUSS-CHECKS (zwingend)
- Python-Version prüfen: 3.12.x erwartet → bei Abweichung abbrechen.
- Sicherstellen: pip verfügbar; KEIN uv/poetry verwendet.
- Falls Alembic-Migrationen geändert/neu: `python -m alembic -c alembic.ini upgrade head` ausführen.
- Tests am Ende:
  - Unit/Offline: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q`
  - DB-Tests nur, wenn `RUN_DB_TESTS=1` **und** `DATABASE_URL` gesetzt; sonst überspringen und darauf hinweisen.
- Nicht-grüne Schritte ⇒ hart scheitern (Exit≠0) und Logs ausgeben.

AUSGABEFORMAT (Pflicht, Reihenfolge einhalten)
[Kontext]        – was vorgefunden wurde (pwd/whoami, OS, devcontainer-Hinweise, python/pip Version, git-Branch/HEAD)
[Plan]           – kurze, nummerierte Schritte
[Befehle+Logs]   – alle Kommandos mit vollständiger Ausgabe
[Ergebnis]       – kurzer Status: was erzeugt/geändert, wo liegen Artefakte
[Unified Diff]   – EIN zusammenhängender `git diff` Block über alle Änderungen
[Nächste Schritte] – was ich manuell tun kann (z. B. CLI-Snippets)

VORBEREITUNG (erst ausführen, dann weiter)
1) Devcontainer-Nachweis (mind. zwei):
   - `pwd && whoami`
   - `cat /etc/os-release || cat /etc/issue`
   - `test -d .devcontainer && echo "devcontainer dir present"`
2) Toolchain prüfen:
   - `python -VV && pip --version`  (erwartet: Python 3.12.x)
3) Abhängigkeiten (nur wenn nötig/erlaubt):
   - `pip install -r requirements.txt`  (oder `requirements-dev.txt`, falls vorhanden)
4) Git-Zustand:
   - `git status -uno && git rev-parse --abbrev-ref HEAD && git rev-parse --short HEAD`

AUFGABE
Bitte erledige das folgende Arbeitspaket **reproduzierbar im Devcontainer**:

<TITEL_DER_AUFGABE>
- Ziel: <kurze Zieldefinition in 1–2 Sätzen>.
- Akzeptanzkriterien (DoD):
  1) <z. B. neue Dateien nur unter erlaubten Pfaden; keine Top-Level-Strukturänderungen>
  2) <z. B. Alembic-Revision vorhanden; `upgrade head` läuft fehlerfrei>
  3) <z. B. Unit-Tests grün; DB-Tests nur mit gesetzter DB-Umgebung>
  4) <z. B. CLI/Endpoint liefert erwartete Ausgabe / Exit-Code 0>
  5) <z. B. PII-saubere Logs, deterministische Tests>

Randbedingungen:
- Multi-Tenant beachten (`tenant_id`), PII nicht loggen.
- Nur pip; KEIN uv/poetry.
- Keine Langläufer/Server starten, außer ausdrücklich gefordert.
- DB: verwende `DATABASE_URL` aus ENV; wenn nicht gesetzt, DB-Tests freundlich überspringen.

BEISPIEL-TESTLAUF (falls zutreffend)
- Unit/Offline: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q tests`
- DB/E2E (optional): `RUN_DB_TESTS=1 DATABASE_URL=<…> PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q tests`
- CLI-Smoke (optional): `python tools/<pfad>/mein_cli.py <args>`

ERWARTETE ARTEFAKTE (falls zutreffend)
- Code: `backend/apps/<…>/*.py`, `tools/flows/*.py`, `docs/<…>.md`, `ops/alembic/versions/*.py`
- Tests: `tests/<bereich>/test_*.py`
- Konfig: `.vscode/tasks.json` (nur gezielt ergänzen)

JETZT AUSFÜHREN
Gehe nach obigen Schritten vor und liefere das Ergebnis **in den geforderten Abschnitten**. Brich ab, wenn eine Policy verletzt würde, und erkläre warum.
