# CI / Quality Gate v1

Ziel: Merge-sicheres `main` mit harten Qualitätsnachweisen (Lint, Typecheck, Coverage, Smokes, Roundtrip).

Pipelines
- Build (`.github/workflows/ci.yml`):
  - Python 3.12, install requirements
  - Ruff (inkl. Security `S`), mypy (strict für Inbox/Worker), pytest mit Coverage ≥80 % (Domain/Parsing)
  - Artefakte: `artifacts/ci-tests.xml`, `coverage.xml`, `artifacts/egress-violations.json`
- Smokes (`.github/workflows/smoke.yml`):
  - Matrix (upload, programmatic, mail, worker, publisher, read_ops); Artefakte pro Suite
- Nightly Alembic Roundtrip:
  - `alembic downgrade base` → `alembic upgrade head`; Artefakt `artifacts/alembic-roundtrip.log`

Required Checks
- Aktivieren in GitHub: Build (CI Quality Gate), Smoke (matrix), Nightly (optional als Required, empfohlen)

Egress-Sentinel
- Globaler Guard in `tests/conftest.py`: blockiert `socket.getaddrinfo`/`create_connection` und `httpx.Client.__init__` außerhalb whitelisted Callsites; DB-Verbindungen erlaubt.
- JSON-Report: `artifacts/egress-violations.json` (leer bei Erfolg).

Troubleshooting
- Coverage knapp <80 %: zusätzliche Tests schreiben, `omit=` nur gezielt nutzen (kein Maskieren produktiven Codes).
- Ruff Security (`S`): unsichere Patterns (z. B. `subprocess`, `eval`) vermeiden; per-file-ignore sparsam.
- mypy: Typsignaturen in `backend/apps/inbox/*`, `agents/inbox_worker/*` ergänzen; `ignore_missing_imports` minimal halten.
