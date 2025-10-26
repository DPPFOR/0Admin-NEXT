AGENT-SAFETY-HEADER (immer befolgen)
STANDALONE-PROMPT: Dieses Issue ist eigenständig, vollständig und commit-fix referenziert; keine impliziten Abhängigkeiten.

TECHNISCHE BASIS:
- Repo: 0Admin-NEXT
- Python: 3.12
- Flock: 0.5.3 (flock-core)
- Package-Manager: AUSSCHLIESSLICH `pip` (kein uv, poetry, pipenv)
- Scope: nur angegebene Verzeichnisse; keine Strukturänderungen ohne Freigabe.

ARCHITEKTUR-GELÄNDER:
- `backend/products/*` → Fachlogik (domain, services, repositories, schemas, api, templates)
- `backend/core/*` → Querschnitt (eventstore, outbox, documents, numbering, holidays, auth)
- `agents/*` → Flock-Logik (arbeitet nur über definierte APIs/DTOs, kein direkter DB/HTTP-Zugriff)
- `frontend/*` → UI (wird später neu aufgebaut)

TASK-BRIEF (immer ausfüllen)
- ROLLE: {Repo-Architekt | Backend-Implementer | Flock-Orchestrator | Test-Engineer | Docs-Scribe}
- ZIEL: {kurz und messbar, z. B. „Service X in backend/products/mahnwesen/services entwerfen“}
- FILESCOPE-ALLOW: {z. B. backend/products/mahnwesen/**}
- FILESCOPE-DENY: {z. B. agents/**, frontend/**, backend/core/**}

VORGEHEN (Planungs-/Meta-Ebene)
1) README-First → README.md des Ordners lesen und 3–5 Regeln extrahieren.
2) Plan (≤ 5 Punkte): Was wird angelegt/geändert und warum.
3) Schnittstellen/Schema-Skizze (Pydantic/Interfaces) gemäß README.
4) Tests: geplante Unit-/Integrationstests mit Pfad unter `tests/...`.
5) Akzeptanzkriterien (3–5 Given/When/Then).

DEPENDENCIES:
- Nur `pip install`, keine alternativen Toolchains.
- Keine unpinnbaren Pakete hinzufügen.
- Flock-Version immer explizit pinnen.

SCRIPTS & ARTEFACTS POLICY
- Skripte NUR unter tools/cli/<name>/ oder ops/deploy/<target>/.
- Lauf-/Test-Artefakte NUR unter artifacts/**.
- Temporäres Material NUR unter artifacts/.tmp/ und am Ende löschen.
- Es ist VERBOTEN, neue Top-Level-Ordner oder Skripte außerhalb dieser Orte anzulegen.

DO / DON'T:
- DO: Skripte nur in tools/cli/** bzw. ops/deploy/**.
- DO: Lauf-/Testartefakte nur in artifacts/**.
- DO: Temp nur artifacts/.tmp/ → danach löschen.
- DO: Kleine, kohärente Änderungen im FILESCOPE, README aktualisieren wenn Regeln sich ändern.
- DON'T: Keine Skripte/Dateien im Root.
- DON'T: Keine neuen Top-Level-Ordner.
- DON'T: Keine Artefakte in backend/** oder agents/**.
- DON'T: Ordnerstruktur ändern, unbekannte Pakete, andere Package-Manager, direkte Agents↔Backend-Kopplung.

AUSGABENFORMAT:
- Liste der Änderungen als `{pfad}:{operation}:{kurzbeschreibung}`.
- Wenn Information fehlt → „BLOCKED“ melden und Minimal-Alternative vorschlagen.

CLEANUP-PFLICHT
- Nach erfolgreichem Run: Inhalte in artifacts/.tmp/ rekursiv löschen.
- Dauerhafte Nachweise (final.json, coverage, csv-reports) verbleiben in artifacts/**.
- Keine Artefakte außerhalb von artifacts/** hinterlassen.