# data/

Beispieldaten, Seeds und strukturierte Exporte

## 🎯 Zweck

Das Verzeichnis `data/` enthält alle statischen, halb-statischen und generierten Datensätze,
die in 0Admin zu Demonstrations-, Test- oder Initialisierungszwecken verwendet werden.
Es dient als gemeinsame Quelle für Beispielkunden, Templates, Konten und Testrechnungen.

## 🧭 Leitprinzipien

* **Keine Produktionsdaten:** Nur Mock-, Demo- oder Trainingsdaten.
* **Klare Trennung:** Seeds (Systeminitialisierung) ≠ Samples (Demodaten) ≠ Fixtures (Tests).
* **Reproduzierbarkeit:** Jeder Datensatz ist deterministisch generierbar.
* **pip-only, Python 3.12:** Keine externen Daten-Generatoren.
* **Versionsführung:** Jede Datei wird versioniert, keine Ad-hoc-Änderungen im Deployment.

## 🧱 Strukturüberblick

```
data/
├── seeds/            → Initialdaten für Systemstart (z. B. Mandanten, Benutzer, Nummernkreise)
├── samples/          → Beispielkunden, Rechnungen, Mahnungen
├── fixtures/         → Testdaten für Unit- und Integrationstests
├── exports/          → Exportierte Reports, CSV-/JSON-Beispiele
├── schema/           → Datenbeschreibungen (JSONSchema/Pydantic-Modelle)
└── README.md
```

## 🔗 Beziehungen

1. **Seeds** werden bei Setup/Init-Läufen eingespielt (`python scripts/init_seed.py`).
2. **Samples** dienen zur UI- oder Flow-Demo (z. B. Beispielrechnung, Mahnzyklus).
3. **Fixtures** werden von `pytest` verwendet (`tests/fixtures/data_loader.py`).
4. **Exports** sind menschenlesbare oder systemkompatible Beispieldateien (z. B. `e-invoice_sample.xml`, `mahnung_v2.pdf`).

## 🧩 Standards & Formate

* **JSON:** Standard für strukturierte Daten.
* **CSV:** Nur für tabellarische Testreports.
* **XML:** Nur in Kontext von E-Rechnung oder externem Format.
* **UTF-8 only:** Keine Kodierungsmischungen.

## 🧰 Tools & Skripte

Unter `scripts/` liegen optionale Generatoren und Loader, z. B.:

```
scripts/
├── init_seed.py         → Initialisiert Seeds aus data/seeds/  
├── generate_samples.py  → Erstellt Demodaten  
├── export_fixtures.py   → Konvertiert Fixtures in Exportformate  
```

## 🧪 Tests

* Jede Datei unter `data/fixtures/` wird beim CI-Testlauf validiert (Schema + Integrität).
* Änderungen an Seeds erfordern Review & Doppelsignatur, da sie Startzustände beeinflussen.

## 🧱 Erweiterbarkeit

Neue Datensätze folgen diesem Muster:

```
samples/
├── <bereich>_<beschreibung>.json
├── <bereich>_<beschreibung>.csv
└── <bereich>_<beschreibung>.md
```

Beispiel: `samples/rechnung_musterkunde.json`, `samples/mahnung_v1.json`
