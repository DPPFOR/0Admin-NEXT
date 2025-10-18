# 0Admin-NEXT

Vernetzte Automationsplattform für KMU-Handwerksbetriebe

## 🎯 Zweck

0Admin-NEXT ist die Backend- und Agentenbasis der SaaS-Lösung **0Admin**.
Das System automatisiert wiederkehrende Büro- und Verwaltungsprozesse in Handwerksbetrieben – von Kommunikation bis Rechnungsabwicklung – und bildet die Grundlage für zukünftige Module und Integrationen.

## 🧭 Leitprinzipien

* **README-first:** Jeder Ordner beginnt mit einer eigenen README.md, die Aufbau, Zweck und Arbeitsweise beschreibt.
* **Standalone-Prompts:** Alle Coding-Prompts sind kontextfrei, 1:1 ausführbar und enthalten sämtliche Entscheidungen innerhalb des Prompts.
* **pip-only, Python 3.12:** Keine alternativen Toolchains oder Buildsysteme.
* **Flock 0.5.3:** Standard-Framework für ereignisgesteuerte Agenten.
* **Lokal-First-Entwicklung:** Arbeiten in VS Code, Deploy per `scp` auf Server.
* **Meta-Ebene vor Umsetzung:** Erst Struktur und Architektur klären, dann „Go“ zur Realisierung.

## Roadmap 

Übersicht Inhalte, Packete und Terminschiene [](/docs/roadmap.md)


⚙️ Coding-Agenten (Cursor & GitHub Copilot Coding-Agent)

Diese drei Unterlagen definieren das Verhalten, die Regeln und den Arbeitsstil aller KI-basierten Coding-Agents in 0Admin-NEXT.
Sie sind verbindlich zu lesen und stehen unter Schreibverbot (nur Änderung durch den Architekten).

Policy [Policy](/.cursor/rules/Coding-Agent-Policy.mdc)
 — feste Compliance- und Architektur-Schicht

Agents [Agents](/.cursor/rules/agents.mdc)
 — operative Arbeitslogik und Prompt-Methodik

Issue-Template [Issue-Template](/.cursor/rules/Issue-Template_für_GitHub_Copilot_Coding-Agent.mdc)
 — standardisierter Task-Input für Copilot / Codex / Cursor

Weitere Hintergrundinformationen und Zusammenhänge findest du in der begleitenden
README unter [README](/docs/coding-agents/README.md)


## 🧱 Architektur-Überblick

```
backend/     → Geschäftslogik & Core-Services  
agents/      → Flock-basierte Orchestrierung (Mail, Kalender, Reports, Scheduler)  
frontend/    → Benutzeroberfläche (React + Tailwind + Vite)  
tools/       → CLI-Hilfsprogramme, Prompt-Standards  
docs/        → Produkt- und Prozessdokumentation  
tests/       → Integration- & End-to-End-Tests  
ops/         → CI, Systemd-Units, Deployment-Skripte  
data/        → Beispieldaten & Seeds
```

### Kernmodule

* **Inbox (Mail & Drop-Pipelines)** – zentrale Erfassung externer Eingänge
* **Angebots- & Rechnungserstellung** – Vorlagen, Nummernkreise, PDF-Layouts
* **E-Rechnung (ZUGFeRD / XRechnung)** – valide E-Rechnungsprofile
* **Mahnwesen** – automatische Mahnläufe, Eskalationsstufen, Kommunikationsadapter
* **BankFin** – Kontoabgleich und Buchungslogik
* **RAG-Wissen** – Trainings- und Wissenskomponente für interne Nutzung

## 📂 Navigations-Index

### Event / Outbox Policy
- [Event / Outbox Policy](docs/event_outbox_policy.md)


### Backend

* [](backend/README.md)
* [](backend/apps/mahnwesen/specification.md)
* [](backend/core/specification.md)

### Agents

* [](agents/README.md)
* [](agents/mahnwesen/specification.md)

### Tests

* [](tests/README.md)

### Ops / CI

* [](ops/ci/README.md)

### Tools

* [](tools/agent_safety_header.md)

## ⚙️ Arbeitsweise

1. Entwicklung ausschließlich lokal in VS Code.
2. Keine Änderungen direkt auf Servern, außer Notfall.
3. Vor jeder Umsetzung Meta-Ebene definieren und absegnen.
4. Änderungen dokumentieren, commit + push auf `main`.
5. CI-Checks (pytest, lint, migrations) sind verbindlich.

## 🔐 Policies

* Python 3.12 + pip only
* Flock 0.5.3 (fixe Version)
* Keine Strukturänderungen ohne Meta-Freigabe
* Pinned Dependencies in `requirements.txt`
* Ziel: stabiles, erweiterbares Produkt-Backend für reale Kundenbetriebe

Das Projekt nutzt zwei Anforderungsdateien:

- `requirements.txt` – Laufzeitabhängigkeiten für den produktiven Betrieb  
- `requirements-dev.txt` – Entwicklungs- und Testabhängigkeiten für lokale Umgebung und CI  

Installation:
- source .venv/bin/activate
- pip install -r requirements.txt -r requirements-dev.txt
Die Trennung sorgt dafür, dass Produktionssysteme nur minimale, sichere Pakete laden.
