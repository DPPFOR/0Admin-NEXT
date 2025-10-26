⚙️ ops/README.md
ops/

System- und Betriebsautomatisierung

🎯 Zweck

Das Verzeichnis ops/ enthält alle betrieblichen Artefakte und Automatisierungen von 0Admin – CI/CD-Workflows, systemd-Units und Deploy-Skripte.
Ziel ist ein wiederholbares, überprüfbares und auditierbares Deployment.

🧭 Leitprinzipien

Immutable Deployments: Kein manuelles Nachkonfigurieren nach Deployment.

Infrastructure as Code: Alle Ops-Artefakte versioniert.

CI-Checks als Gatekeeper: Kein Merge ohne erfolgreichen Build + Tests.

systemd für lokale Services: Backend, Agenten, Worker.

pip-only, kein Docker Compose für Produktionspfad.

🧱 Strukturüberblick
ops/
├── systemd/        → Service-Units für Backend & Agenten
│   ├── backend.service
│   ├── agents-mahnwesen.service
│   ├── agents-erechnung.service
│   └── README.md
│
├── ci/             → GitHub Actions & Checks
│   ├── test.yml
│   ├── lint.yml
│   ├── deploy.yml
│   └── README.md
│
└── deploy/         → Setup- und Deployment-Hilfen
    ├── hetzner/
    │   ├── setup.sh
    │   ├── nginx.conf
    │   └── ssl_renew.sh
    └── README.md

🔗 Beziehungen

CI-Workflows triggern Tests (tests/) und Code-Quality-Checks.

systemd-Units starten die produktiven Dienste.

deploy/ enthält Installationsskripte für Hetzner-Server und Let’s Encrypt-Automatisierung.