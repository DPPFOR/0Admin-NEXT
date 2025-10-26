# Core

Das `backend/core/` Modul enthält querschnittliche Infrastruktur und Services ohne Fachlogik.

## Zweck

- Bereitstellung von technischer Infrastruktur (DB, Config, Auth, Eventstore, Outbox etc.)
- Zentrale Dienste und Utilities für alle Apps
- Keine Geschäftlogik oder fachspezifische Regeln

## Verantwortlichkeiten

- Querschnittliche Konfiguration und Settings
- Datenbankverbindungen und Migrations
- Authentifizierung und Authorisierung
- Eventstore und Outbox-Infrastruktur
- Logging und Monitoring
- Dokumentenverarbeitung
- Ferien-/Feiertagsberechnungen
- Nummerierungssysteme

## Import-Grenzen

Regel: apps → (core|common) erlaubt; core/common keine Fachlogik (Domain).
