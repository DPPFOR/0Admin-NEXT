backend/migrations/specification.md
📘 Modul: Migrations (Alembic Lifecycle)
🎯 Zweck

migrations/ verwaltet alle Datenbankschemata, Revisionen und Migrationsläufe via Alembic-only Policy.
Ziel: reproduzierbare, reversible und dokumentierte Migrationen ohne direkte SQL-Manipulationen.

🧩 Verantwortungsbereich
1) Alembic-Konfiguration (alembic.ini, env.py)
2) Revisionsverwaltung (versions/*.py)
3) Lifecycle-Management (upgrade, downgrade, stamp)
4) Dokumentation der Revisionen & Abhängigkeiten
5) Integration in CI (GitHub Actions, pytest)

🧱 Struktur
backend/migrations/
├── alembic.ini
├── env.py
├── versions/
│   ├── 20241015_0001_init.py
│   ├── ...
└── specification.md

⚙️ Richtlinien
- Migrationen nur über Alembic (python -m alembic revision/upgrade)
- Keine Raw-SQL-Dateien, keine ORM-Autogenerates ohne Review
- Jede Revision muss downgradefähig sein
- CI validiert Up-/Down-Flow mit Exit-Code

🧪 Tests
- Revisionsgraph testet roundtrip (upgrade → downgrade → upgrade)
- Schema-Diff gegen ORM-Modelle wird protokolliert
- Exit-Codes & Revisionslog persistiert in artifacts/

📋 Definition of Done
- Alle Revisionen upgrade/downgradefähig
- Keine manuelle SQL-Ausführung
- CI-Testlauf erfolgreich mit Python 3.12 + pip
- Artefakte (alembic current, Revisionslog) vorhanden