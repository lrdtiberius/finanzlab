# FinanzLab 2.6.4

**FinanzLab** ist eine selbstgehostete Anwendung zur tagesgenauen Haushalts- und Liquiditätsplanung mit SQLite. Konten, Einnahmen, Ausgaben, Kredite und Umbuchungen werden historisiert und für die Vorschau und den Excel-Export ausgewertet.

**Projekt:** by Lrd.Tiberius · **Unterstützung:** [☕ Buy me a coffee (via PayPal)](https://www.paypal.com/paypalme/SebastianM207)

> **Sicherheit:** FinanzLab verfügt über keine integrierte Benutzeranmeldung. Nur in einem geschützten Netzwerk oder hinter einer eigenen Zugriffskontrolle verwenden. Den Port `8798` nicht ungeschützt ins Internet freigeben.

## Was ist neu?

- **2.6.4:** Im grünen Dashboard-Kopf können bis zu vier ausgewählte Bankkonten mit ihrem bis heute berechneten Kontostand angezeigt werden. Die haushaltsbezogene Auswahl steht direkt unter dem weiterhin obersten Excel-Export in den Einstellungen.
- **2.6.3:** Kompaktere Einstellungen mit Finanzassistent über die ganze Breite, Haushalt und Personen nebeneinander sowie einer auf die zwölf neuesten oder zuletzt wiederhergestellten Datenbanksicherungen begrenzten 3×4-Ansicht.
- **2.6.2:** Einzelne Vorschau-Vorgänge können als **Entfällt** markiert werden. Sie bleiben sichtbar, werden aber aus Kontostand, Einnahmen/Ausgaben, Operativ frei und Liquiditätsänderung herausgerechnet.
- **2.6.1:** Änderungen an **Vorgang erledigt** und **Betrag ändern** aktualisieren Dashboard und bereits geöffnete Monatsvorschau unmittelbar.
- **2.6.0:** Deutlich schnellere Vorschau- und Kreditberechnung, kleinere Startdaten, verzögertes Laden seltener Bereiche, gzip-Auslieferung und optimierte Wiederholungsberechnung.
- **2.4.4:** Bei der Kreditart **Geliehen** übernehmen Tilgungsübersicht, Restschuld und Schlussrate auch manuell geänderte einzelne Monatsraten aus der Kontostandsvorschau. Andere Kreditarten behalten ihre Regeln. Auf der Seite **Zinsen** stehen laufende Kredite vor vollständig getilgten oder archivierten Krediten.
- **2.4.3:** Ein neuer Ratenplan für **Geliehen** beendet andere bisherige monatliche Rückzahlungspläne desselben Kredits ab dem Änderungsstichtag; historisch geleistete Rückzahlungen bleiben bestehen. **Geliehen** wird aus der Zinsübersicht ausgeschlossen.
- **2.4.2:** Zwölfmonatige Vorausberechnung im Hintergrund, Browser- und Servercache für Monatsvorschauen sowie Fehlerbehandlung und Navigation der Zinsansicht.
- **2.4.0:** Flexible Personenverwaltung und aufklappbare Kontostand-Historie.

## Funktionen

- Auswählbare heutige Kontostände im Dashboard-Kopf, Kontostands- und Liquiditätsvorschau sowie sechsmonatige Kontostandsübersicht
- Finanzassistent für Dispowarnungen und Sondertilgungsvorschläge
- Berechnungen für zwölf Monate vorbereitet; darüber hinaus auf Abruf
- Historisierte Kontostände, Einnahmen, Ausgaben und Umbuchungen
- Kredite, Konsumkredite, Darlehen und „Geliehen“ mit Raten, Zinsen und Sondertilgungen
- Tilgungshistorie, manuelle Einzelratenkorrekturen und Zinsübersicht
- Excel-Export, auf zwölf Einträge begrenzte Datenbanksicherungen und optionale EnergyLab-Synchronisierung

## Installation

```bash
git clone https://github.com/lrdtiberius/finanzlab.git
cd finanzlab
docker compose up --build -d
```

Lokal ist die Anwendung unter `http://localhost:8798` erreichbar. Das Datenverzeichnis `/data` muss persistent sein. **Für bestehende Installationen vor jedem Update ein konsistentes SQLite-Backup anlegen und das bisherige Datenvolume beibehalten.** Keine alte und neue FinanzLab-Version gleichzeitig auf derselben Datenbank betreiben.

Siehe [Installationsanleitung](INSTALLATION.md), [Portainer-Stack](portainer-stack.yaml), [Benutzerhandbuch](HANDBUCH.md), [Neuerungen 2.6.4](docs/NEUERUNGEN_2.6.4.md), [Neuerungen 2.6.0–2.6.3](docs/NEUERUNGEN_2.6.0_BIS_2.6.3.md), [Ergänzungen 2.4.2–2.4.4](docs/NEUERUNGEN_2.4.2_BIS_2.4.4.md), [technische Dokumentation (Basisstand 2.3.0)](docs/TECHNISCHE_DOKUMENTATION.md) und [Changelog](CHANGELOG.md).

## Tests

```bash
python3 -m unittest discover -s tests -v
node --check app/static/app.js
node --check app/static/credit-archive.js
node --test tests/*.cjs
```

Die Regressionstests verwenden synthetische Daten. Ältere Tests enthalten gekennzeichnete erwartete Fehler. Vor der offiziellen Veröffentlichung müssen die GitHub-Actions-Tests auf dem Pull Request erfolgreich sein.

## Datenschutz

**Keine privaten Finanzdaten veröffentlichen.** Datenbanken, Backups, Zugangsdaten, Logdateien, Servernamen, IP-Adressen, Kontobelege und produktive Einstellungen gehören nicht zu diesem Repository. Bestehende Git-Historie muss unabhängig von der Dateiprüfung betrachtet werden. Persönliche App-Daten liegen ausschließlich im selbst verwalteten Datenvolume und nicht im Quellrepository.
