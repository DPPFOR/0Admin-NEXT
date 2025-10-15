🧪 tests/README.md
tests/

Testarchitektur, Standards und Ausführungsregeln

🎯 Zweck

Das Verzeichnis tests/ bündelt alle automatisierten Tests von 0Admin – von Unit- bis End-to-End-Ebene.
Es dient als Sicherheitsnetz für jede Codeänderung und als Qualitätsnachweis für Merges, CI und Releases.

🧭 Leitprinzipien

Test-first-Mindset: Jeder neue Code entsteht mit begleitendem Test.
Trennung nach Testebene: Unit ≠ Integration ≠ E2E.
Determinismus: Keine externen API-Abhängigkeiten ohne Mock.
Idempotente Läufe: Wiederholte Tests müssen identische Ergebnisse liefern.
pytest ≥ 8.3, Python 3.12, pip-only.

🧱 Strukturüberblick
tests/
├── unit/              → reine Funktions- und Modultests
│   ├── core/
│   ├── mahnwesen/
│   └── erechnung/
│
├── integration/       → Endpunkte & Modulgrenzen (DB, API, Outbox)
│   ├── mahnwesen/
│   ├── erechnung/
│   └── shared/
│
├── e2e/               → systemweite Tests (CLI, Flows, UI-Checks)
│   ├── backend/
│   └── frontend/
│
├── fixtures/          → Testdaten, geladen über data/fixtures/
└── README.md

🧪 Testausführung

Lokaler Lauf:
pytest -W error -q


Coverage-Report:
pytest --cov=backend --cov-report=term-missing

🔗 Beziehungen

nutzt Daten aus data/fixtures/
wird in CI über ops/ci/test.yml automatisiert ausgeführt