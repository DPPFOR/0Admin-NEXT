# === 0Admin – Standalone-Operations-Prompt (FASTLANE) ===
# Zweck: Eine Aufgabe in 0Admin-NEXT reproduzierbar, policy-konform und go-live-orientiert umsetzen.
# WICHTIG: Alles Nötige steht in diesem Prompt. Keine Abhängigkeit zu Chatverlauf/Links.

TITLE: <Kurztitel – Modul/Feature – Datum>

REPO_ROOT: /home/satinder/dev/0Admin-NEXT
PYTHON_VERSION_REQUIRED: 3.12
VENV_PATH: .venv
ALLOWED_CODE_PATHS:
  - agents/
  - backend/
  - tools/
  - tests/
  - docs/
  - .vscode/tasks.json
  - ops/alembic/
ALLOWED_REPORT_PATHS:
  - artifacts/reports/
  - artifacts/tests/
  - artifacts/env/

GOAL (ein Satz):
- <Was am Ende vorliegen muss – z. B.: „Mahnwesen MVR – Templates & Dispatch finalisieren, Tests grün, Multi-Tenant-fähig, DoD erfüllt.“>

CONSTRAINTS & POLICY
- Arbeite NUR im lokalen Workspace: ${REPO_ROOT}. Falls Devcontainer vorhanden: bevorzugt nutzen; sonst lokal.
- Toolchain: Python ${PYTHON_VERSION_REQUIRED} im aktiven ${VENV_PATH}.
- Paketinstallation: primär mit pip im aktiven venv. **uv ist erlaubt**, wenn via `python -m uv` aus dem aktiven venv ausgeführt wird. **poetry/conda verboten**.
- Keine globalen Host-Installs außer minimal (falls nötig) python/pip. Keine Fremddienste außer Together (optional).
- Multi-Tenant strikt: `X-Tenant-Id` Header → DTO/Event → Outbox. Keine Hardcodes je Tenant.
- Idempotenz & Determinismus: identische Inputs ⇒ identische Outputs (TZ=UTC, PYTHONHASHSEED=0, injizierbares now()).
- PII-Schutz: Logs als JSON, IBAN/E-Mail/Tel maskiert. Keine Klartext-PII in Artefakten.
- Keine Top-Level-Strukturänderungen. Änderungen nur in ALLOWED_CODE_PATHS.
- **Keine Commits/Pushes.** Am Ende **ein** `git diff` (konsolidiert).

GUARDS (harte Abbruchkriterien)
- venv inaktiv ODER Python != ${PYTHON_VERSION_REQUIRED}.x ⇒ ABBRUCH mit Begründung.
- pip/uv nicht aus aktivem venv (`python -m pip debug --verbose` prüfen) ⇒ ABBRUCH.
- Projekt-Requirements/Constraints fehlen ⇒ ABBRUCH.
- Policy-Konflikt (z. B. Änderung außerhalb ALLOWED_CODE_PATHS) ⇒ ABBRUCH (nur diff anzeigen).
- DB-Gate: **Nur** DB-Operationen/DB-Tests, wenn `RUN_DB_TESTS=1` **und** `DATABASE_URL` gesetzt. Sonst sauberer **SKIP** (kein Fail).
- LLM-Gate (Together): **Nur** wenn `TOGETHER_BASE_URL`, `TOGETHER_API_KEY`, `TOGETHER_MODEL` gesetzt. Sonst **SKIP** mit Begründung.

ENV HANDLING
- `. env` laden via: `set -a; source .env; set +a` (keine Secrets in Logs).
- In Status: `printenv | grep -E '^(DATABASE_URL|RUN_DB_TESTS|TOGETHER_)' | sed 's/=.*/=<SET>/'`

TESTS (Läufe)
- Immer setzen: `TZ=UTC`, `PYTHONHASHSEED=0`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`.
- Offline-Tests (default): `pytest -q tests/<bereich>` (oder konkrete Dateien).
- DB-Tests: nur wenn Gate offen; sonst SKIP mit Grund.
- Together-Smoke (optional): nur wenn Gate offen; bei fehlendem ENV ⇒ SKIP.
- **Template-Tests**: Niemals Repo-Templates persistent überschreiben. Wenn ein Test Dateien benötigt, nutze **tmp_path** (Isolation). Falls ein bestehender Test Templates mutiert, isoliere ihn oder selektiere temporär `--deselect` mit Begründung im Output (und TODO notieren).

ACCEPTANCE (DoD)
- Alle neuen/offline Tests **grün**; optionale DB-Tests werden sauber **geskippt**, nicht gefailt, wenn ENV fehlt.
- Multi-Tenant end-to-end (Header → DTO → Event) nachweisbar.
- Idempotenz/Determinismus nachweisbar (stabile Keys/Hashes, injizierbares now()).
- PII-Redaction in Logs stichprobenhaft getestet (Regex-Asserts).
- Genau **ein** Unified-Diff; Änderungen nur in erlaubten Pfaden.
- Together-Smoke: **OK** (200 + Minimal-Check) oder sauberer **SKIP** mit Grund.

OUTPUT FORMAT (streng in dieser Reihenfolge ausgeben)
1) STATUS
   - `pwd && whoami`
   - OS/Kernel kurz
   - Devcontainer-Nachweis (ja/nein)
   - `python -VV`
   - `pip --version`
   - `python -m pip debug --verbose` (nur die venv-Relevanzzeilen)
   - `git status -sb` + aktueller Branch/HEAD
   - `echo "PYTHONPATH=$PYTHONPATH"`
   - Maskierte ENV (s. ENV HANDLING)
2) COMMANDS & LOGS
   - Alle Kommandos mit vollständiger Terminalausgabe (inkl. Fehlern).
3) TEST RESULTS
   - Zusammenfassung pro Lauf (Offline, optional DB, optional Together) inkl. Skip-Gründe.
4) UNIFIED-DIFF
   - Ein `git diff --no-color` über alle Änderungen.
5) RESULT FILES
   - Liste der erzeugten/geänderten Dateien (mit Pfaden).
6) NEXT STEPS
   - 2–3 kurze Hinweise (z. B. VSCode Task/CLI-Aufruf).
7) NOTES
   - Auffälligkeiten, TODOs (z. B. Tests, die temporär deselektiert wurden, mit Begründung).

RUNTIME STEPS (umsetzen – keine Prosa, nur tun und loggen)
- [ ] venv aktivieren; Toolchain verifizieren.
- [ ] `.env` laden; Gates prüfen (DB/LLM).
- [ ] `export PYTHONPATH="$PWD"`.
- [ ] Aufgabe implementieren (nur erlaubte Pfade anfassen).
- [ ] Tests ausführen (Offline ⇒ ggf. auch gezielt Dateien/Module).
- [ ] Optionale DB-Tests nur bei offenem Gate.
- [ ] Optional Together-Smoke durchführen (Gate).
- [ ] Unified-Diff erzeugen.
- [ ] Output nach „OUTPUT FORMAT“ strukturieren.

TASK (heute umsetzen – konkret)
- Titel: <konkreter Taskname>
- Ziel: <1–2 Sätze fachlich/technisch>
- Akzeptanz:
  - <Kriterium 1 (prüfbar)>
  - <Kriterium 2 (prüfbar)>
  - <Kriterium 3 (prüfbar)>
- Randbedingungen:
  - Keine Netz-Egress außer optional Together-Smoke.
  - Keine Langläufer/Server starten (außer explizit gefordert).
  - Multi-Tenant/Policy/Flock strikt einhalten.
