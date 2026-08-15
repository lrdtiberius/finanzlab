# Haushaltsplaner

Lokale Webanwendung zur tagesgenauen Liquiditätsplanung für private Haushalte.

Die Anwendung verwaltet Konten mit historisierten Kontoständen, regelmäßige und einmalige Einnahmen und Ausgaben sowie Umbuchungen zwischen eigenen Konten. Prognose und Monatsvorschau berechnen die daraus entstehenden Kontobewegungen pro Tag.

## Funktionen

- mehrere Haushalte und Konten
- historisierte Kontostände mit Kennzeichnung bereits enthaltener Tagesbuchungen
- Standardkonto für neue Einnahmen und Ausgaben
- Einnahmen und Ausgaben mit Rhythmus und optionalem Enddatum
- Saldo aller angelegten Positionen direkt auf den Einnahmen- und Ausgabenseiten
- Ausgabeart „Kredit“
- Umbuchungen mit Rhythmus, optionalem Enddatum und optionaler Ausführungsanzahl
- Tagesprognose und taggenaue Monatsvorschau
- strukturierter Excel-Export mit Monats-/Tagesprognosen, Bewegungen und sämtlichen Eingaben
- Warnung bei Überschreitung eines hinterlegten Disporahmens
- Datenprüfung für nicht berücksichtigte oder unvollständige Positionen

Importfunktionen, Kredit-Sondermodule und Zinsberechnungen sind nicht Bestandteil dieser Version.

## Schnellstart mit Docker

Voraussetzungen: Docker Engine mit Docker Compose.

```bash
docker compose up --build -d
```

Danach ist die Anwendung auf dem lokalen Rechner erreichbar:

```text
http://localhost:8798
```

Der Port kann in `compose.yaml` angepasst werden. Die Anwendungsdaten liegen ausschließlich im Docker-Volume `finanzlab_data` und gehören nicht zum Repository.

Stoppen:

```bash
docker compose down
```

Stoppen und lokale Anwendungsdaten löschen:

```bash
docker compose down -v
```

## Lokaler Start ohne Docker

```bash
python3 -m app
```

Optional können `PORT` und `DATA_DIR` als Umgebungsvariablen gesetzt werden.

## Tests

```bash
python3 -m unittest discover -s tests -v
node --check app/static/app.js
```

## Handbuch

Das vollständige Benutzerhandbuch mit Installation, Kontostand-Logik, Prognosen, Excel-Export, Datensicherung und Fehlerbehebung steht in [HANDBUCH.md](HANDBUCH.md).

## Datenschutz

Das Repository enthält keine Kontostände, Transaktionen, Haushaltsnamen, privaten Netzwerkadressen oder Zugangsdaten. Persönliche Anwendungsdaten entstehen erst beim lokalen Betrieb und werden unter `DATA_DIR` beziehungsweise im Docker-Volume gespeichert.

Vor einer Veröffentlichung eigener Änderungen sollten insbesondere Datenbanken, Backups, Screenshots, Protokolle und `.env`-Dateien ausgeschlossen bleiben.

## Releases

Ein Tag im Format `v*` startet den enthaltenen GitHub-Workflow. Er führt die Tests aus, erstellt ein Quellpaket des markierten Stands und veröffentlicht daraus ein GitHub-Release.

Der Excel-Export wird in der Anwendung unter **Einstellungen** gestartet. Der Zeitraum ist auf höchstens 24 Monate begrenzt; alle eingegebenen Einnahmen und Ausgaben werden unabhängig vom Prognosezeitraum vollständig in eigenen Tabellenblättern ausgegeben.

## Autor und Unterstützung

Entwickelt von **Lrd.Tiberius**. Wer das Projekt unterstützen möchte, findet den „Buy me a coffee“-Link direkt in der Anwendung.
