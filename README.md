# FinanzLab 2.4.0

**FinanzLab** ist eine selbstgehostete Webanwendung zur tagesgenauen Haushalts- und Liquiditätsplanung mit SQLite. Kontostände, Einnahmen, Ausgaben, Kredite, Darlehen und Umbuchungen werden historisiert und für Vorschau, Dashboard und Excel-Export berücksichtigt.

**Projekt:** by Lrd.Tiberius · **Unterstützen:** [☕ Buy me a coffee (via PayPal)](https://www.paypal.com/paypalme/SebastianM207)

> **Wichtig:** FinanzLab besitzt keine integrierte Benutzeranmeldung. Nur in einem vertrauenswürdigen Netzwerk oder hinter einer geeigneten Zugangskontrolle betreiben; Port `8798` nicht öffentlich freigeben.

## Neuerungen in 2.4.0

- **Kontostand-Historie:** Die neuesten fünf Stände sind direkt sichtbar. Ältere Stände werden nach Monaten aufklappbar gruppiert, bleiben aber vollständig gespeichert und werden weiterhin für Berechnungen und Exporte genutzt.
- **Personenverwaltung:** Unter **Einstellungen → Personen / Zuordnung** Personen hinzufügen, umbenennen und – falls unbenutzt – löschen. Die bisherige Begrenzung auf Person A und B entfällt.
- **Kompatible SQLite-Migration:** Historische Person-IDs und Konten-/Buchungszuordnungen bleiben erhalten. Neue Personen stehen als Besitzer für Konten und als Zuordnung für Einnahmen/Ausgaben zur Verfügung.

## Wichtige Funktionen

- Tagesgenaue Kontostand-Prognosen, Monatsvorschau, 6-Monats-Liquiditätsvorschau und Dashboard-Kennzahlen
- Historische Kontostände inklusive Tagesbuchungsstatus, Kontorahmen und Rahmenkredite
- Wiederkehrende und einmalige Einnahmen/Ausgaben, Erledigt-Status, Vorschaukorrekturen und Archive
- Kredite, Konsumfinanzierungen und Darlehen mit Zins-/Tilgungsberechnung und Sondertilgungen
- Umbuchungen, Kontoauszugs-Abgleich, Excel-Export, interne SQLite-Sicherungen
- Optionaler Abgleich von Abschlägen und Vertragszahlungen mit EnergyLab

## Installation

Voraussetzung: Docker Engine und Docker Compose. Das Repository enthält **nur Anwendungscode und Beispielkonfiguration** – keine privaten Finanzdaten.

```bash
git clone https://github.com/lrdtiberius/finanzlab.git
cd finanzlab
docker compose up --build -d
```

Danach ist die Anwendung lokal unter `http://localhost:8798` erreichbar. Die Daten werden im persistenten Docker-Volume gespeichert. Für entfernten Zugriff sind eine eigene Absicherung und passende Port-Freigabe erforderlich.

**Bei bestehenden Installationen:** Vor dem Versionswechsel eine konsistente SQLite-Sicherung erstellen und das **bestehende Datenvolume** unter `/data` weiterverwenden. Die 2.4.0-Migration kann die Personentabelle verändern; für einen Rückwechsel auf ältere Versionen wird eine Vor-Update-Datenbanksicherung benötigt.

Für Portainer und weitere Methoden: [Installationsanleitung](INSTALLATION.md) und [Portainer-Stack](portainer-stack.yaml).

## Dokumentation

- [Benutzerhandbuch](HANDBUCH.md) – Bedienung, Kreditlogik, Vorschau, EnergyLab und häufige Fragen
- [Technische Dokumentation](docs/TECHNISCHE_DOKUMENTATION.md) – Rechenprinzipien, Datenmodell, historisierte Stände, Migration
- [Installationsanleitung](INSTALLATION.md) – Einrichtung, Updates, Datensicherung und Wiederherstellung
- [Änderungsverlauf](CHANGELOG.md)

## Tests

```bash
python3 -m unittest discover -s tests -v
node --check app/static/app.js
```

Die vorhandenen Regressionstests stammen teils aus älteren Versionen. Vor einem Release sind ihre Ergebnisse im Kontext des aktuellen Funktionsumfangs zu bewerten. Ein Tag `v2.4.0` sollte erst erstellt werden, wenn die GitHub-Actions-Tests für diesen Stand erfolgreich laufen.

## Datenschutz und Backups

`planner.db`, Kontoauszüge, Exporte, private Konfigurationsdateien, Zugangsdaten, Screenshots und Backups gehören **nicht** ins Repository. `.gitignore` und `.dockerignore` ergänzen die manuelle Kontrolle; sie schützen nicht automatisch bereits von Git verfolgte Dateien oder ältere Commits. Eine Sicherung im gleichen Docker-Volume ersetzt kein externes Backup.

**Autor / Projektkennung:** Lrd.Tiberius · [Unterstützung per PayPal.Me](https://www.paypal.com/paypalme/SebastianM207)
