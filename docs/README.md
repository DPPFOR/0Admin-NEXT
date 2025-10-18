# docs/

Technische und funktionale Dokumentation von 0Admin

## 🎯 Zweck

Das Verzeichnis `docs/` bündelt alle projektrelevanten Dokumente zu Architektur, Entscheidungen, Schnittstellen und Prozessen.
Es dient als **zentrale Wissensbasis** für Entwickler, Reviewer und Operatoren – unabhängig von externen Tools oder Wikis.

## 🧭 Leitprinzipien

* **Single Source of Truth:** Alle Architektur- und Entscheidungsdokumente werden hier gepflegt, nicht in Tickets oder Chat-Threads.
* **Verknüpfung über README-Kaskade:** Jeder Unterordner enthält eine eigene `README.md` mit Kurzüberblick und Links.
* **Markdown only:** Kein PDF, kein DOCX. Alles muss diff-fähig bleiben.
* **Stable API-Level:** Nur Dokumente, die reale Code- oder Systemzustände abbilden, gehören hierher.
* **Trennung von Architektur und Betrieb:** Konfigurationen oder Deployments liegen unter `scripts/` oder `infra/`, nicht unter `docs/`.

## 🧱 Strukturüberblick

```
docs/
├── architecture/       → Systemarchitektur, Module, Datenflüsse
│   ├── context-diagram.md
│   ├── component-view.md
│   ├── dataflow.md
│   └── README.md
│
├── decisions/          → Architekturentscheidungen (ADR-Format)
│   ├── ADR-001-core-structure.md
│   ├── ADR-002-agent-orchestration.md
│   └── README.md
│
├── api/                → Schnittstellenbeschreibungen (REST, Event, Flock)
│   ├── backend.md
│   ├── agents.md
│   └── README.md
│
├── operations/         → Deployment, Monitoring, Incident-Playbooks
│   ├── deployment.md
│   ├── monitoring.md
│   ├── incidents.md
│   └── README.md
│
└── glossary.md         → Einheitliche Begriffe und interne Taxonomie
```

## 🔗 Beziehungen

1. **architecture/** beschreibt den Aufbau von 0Admin auf Modulebene.
2. **decisions/** dokumentiert alle Architekturentscheidungen in ADR-Form (Architecture Decision Record).
3. **api/** beschreibt interne und externe Schnittstellen – sowohl REST-Endpoints als auch Flock-Typen.
4. **operations/** bündelt technische Anleitungen für Betrieb, Monitoring und Recovery.
5. **glossary.md** stellt konsistente Begrifflichkeiten für alle Beteiligten sicher.

## 🧩 Standards & Format

* **ADR Format:**

  ```
  # ADR-00X <Kurztitel>
  ## Status
  Accepted | Superseded | Draft
  ## Kontext
  <Problemstellung / Ausgangssituation>
  ## Entscheidung
  <getroffene Architekturentscheidung>
  ## Konsequenzen
  <positive und negative Auswirkungen>
  ```
* **Diagramme:** PlantUML (`.puml`) oder Mermaid (`.mmd`), nie eingebettete Screenshots.
* **Verlinkung:** Relative Links zwischen Dokus, keine externen URLs (außer Quellenangaben).

## 🧰 Nutzung

Die Dokumentation ist als **Begleitstruktur zum Code** gedacht:

* Entwickler → lesen `docs/architecture` und `docs/decisions`, bevor sie neue Module anlegen.
* Operatoren → nutzen `docs/operations` als Laufzeit-Handbuch.
* Reviewer → prüfen ADRs und API-Beschreibungen vor Merge-Requests.

## 🧱 Erweiterbarkeit

Neue Dokumente folgen demselben Muster:

* Präfix `ADR-` für Entscheidungen.
* Präfix `RFC-` für konzeptionelle Vorschläge.
* Präfix `SPEC-` für technische Spezifikationen (z. B. Datenformate).
