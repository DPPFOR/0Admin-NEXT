# agents/

Agentenebene und Orchestrierung in 0Admin

## 🎯 Zweck

Die Agentenschicht bildet das verteilte, ereignisgesteuerte Nervensystem von 0Admin.
Sie nutzt das Framework **Flock (Version 0.5.3)**, um Aufgaben zwischen autonomen Prozessen zu koordinieren – vollständig deklarativ, typ-sicher und parallelisierbar.

## 🧭 Leitprinzipien

* **Blackboard-Architektur:** Alle Agenten kommunizieren ausschließlich über den zentralen Flock-Blackboard-Store (SQLite oder DuckDB).
* **Deklarative Kontrakte:** Verhalten wird über Pydantic-Typen beschrieben, nicht über Prompts.
* **Lose Kopplung:** Keine direkten Funktionsaufrufe zwischen Agenten. Kommunikation nur über veröffentlichte Artefakte.
* **Type-safety & Runtime-Validation:** Jeder Publish-/Consume-Pfad validiert seine Payloads zur Laufzeit.
* **pip-only, Python 3.12:** Keine Alternativ-Toolchains.
* **Standalone-Startbarkeit:** Jeder Agent ist einzeln ausführbar und testbar.

## 🧱 Strukturüberblick

```
agents/
├── mahnwesen/       → Agenten zur Steuerung von Mahnprozessen  
│   ├── collector/   → sammelt Mahnrelevante Rechnungen  
│   ├── analyzer/    → prüft Fristen und Beträge  
│   ├── notifier/    → generiert Mahnungen und Kommunikation  
│   └── __init__.py  
│
├── erechnung/        → Agenten für E-Rechnungen (Erzeugung, Validierung, Versand)  
├── inbox/           → Mail-, Upload- und Parser-Agenten  
├── scheduler/       → Zeit- und Ereignis-Trigger  
├── monitor/         → Überwachung, Circuit-Breaker, Self-Healing  
├── store/           → Blackboard-/Event-Store-Erweiterungen  
└── common/          → Typdefinitionen, Utilities, Komponenten
```

## 🔗 Orchestrierungsregeln

1. Agenten dürfen **nur** Artefakte (Pydantic-Typen) austauschen, keine Objekte aus dem Backend importieren.
2. Kommunikation läuft ausschließlich über den **Flock-Blackboard-Store**.
3. Jeder Agent beschreibt:
   * **Consumes:** Eingabedaten (Typen)
   * **Publishes:** Ausgabedaten (Typen)
4. Kein Agent darf Datenbanken oder Services direkt ansprechen, die Backend-Domäne bleibt entkoppelt.

## ⚙️ Laufzeit & Beobachtung

* Ausführung: `python -m flock run` oder Dashboard-Start via `await flock.serve(dashboard=True)`
* Persistenz: `.flock/blackboard.db` (lokal), alternativ DuckDB-Tracing
* Observability: `FLOCK_AUTO_TRACE=true` aktiviert DuckDB-basierte Traces in `.flock/traces.duckdb`

## 🧩 Interaktion mit Backend

* Backend → veröffentlicht Ereignisse in die **Outbox**.
* Agents → konsumieren Ereignisse über Flock und veröffentlichen neue Artefakte.
* Kein Agent darf direkt auf `backend.*` zugreifen. Nur über Typen und Events.

## 🧪 Tests

* Jeder Agent besitzt lokale Unit-Tests.
* Integrationstests befinden sich unter `tests/integration/agents/<agentname>`.
* Testlauf immer mit `pytest -W error --maxfail=1`.

## 🧱 Erweiterbarkeit

Neue Agenten werden modular hinzugefügt:

```
myagent/
├── types.py        → @flock_type-Definitionen  
├── logic.py        → Hauptlogik  
├── components.py   → optionale Lifecycle-Hooks  
├── __init__.py     → Registrierung & Flock-Setup  
└── README.md       → Zweck, Inputs, Outputs, Beispiel-Flows
```
