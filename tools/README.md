🧰 tools/README.md
tools/

Entwicklungs-, QA- und CLI-Utilities

🎯 Zweck

Das Verzeichnis tools/ bündelt alle Hilfsprogramme für Entwicklung, Tests, Datenprüfung und interne Automatisierung.
Es stellt Funktionen bereit, die den Lebenszyklus des Projekts unterstützen, ohne Teil der Kernlogik zu sein.

🧭 Leitprinzipien

Kein Business-Code: Tools dürfen nur indirekt mit Kernlogik interagieren.
pip-only-Kompatibilität: keine Systemabhängigkeiten außer Python 3.12.
CLI-Standard: jede CLI akzeptiert --trace-id und gibt JSON-Finals aus.
Prompt-Sicherheit: Jeder Coding-Agent-Prompt basiert auf deinem Root-„AGENT-SAFETY-HEADER“.

🧱 Strukturüberblick
tools/
├── cli/             → manuelle Befehle (z. B. mahnwesen-inspect, erechnung-validate)
│   ├── mahnwesen-inspect/
│   ├── erechnung-validate/
│   └── README.md
│
├── data/            → kleine Datenskripte (Fixtures, Samples)
│   ├── generate_fixtures.py
│   ├── sample_to_csv.py
│   └── README.md
│
├── qa/              → Qualitätssicherung & Konformitätsprüfungen
│   ├── smoke/
│   ├── contracts/
│   └── README.md
└── README.md

🔗 Beziehungen

greift auf backend/ & data/ zu, aber nie direkt auf agents/.
CLI-Tools werden in CI-Jobs getestet (ops/ci/test.yml).
alle Tools verwenden dieselben Umgebungsvariablen (.env-Schema unter config/).

🧩 Erweiterbarkeit

Neue Tools oder CLI-Module folgen diesem Muster:
tools/cli/<name>/
├── main.py
├── __init__.py
└── README.md