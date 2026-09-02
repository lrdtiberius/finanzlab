# Haushaltsplaner

Lokale Webanwendung zur tagesgenauen Liquiditätsplanung für private Haushalte.

Die Anwendung verwaltet Konten mit historisierten Kontoständen, regelmäßige und einmalige Einnahmen und Ausgaben, Kredite mit Zahlungshistorie sowie Umbuchungen zwischen eigenen Konten. Die Monatsvorschau berechnet die daraus entstehenden Kontobewegungen und getrennt davon simulierte Kreditstände pro Tag.

## Dokumentation

- **[Ausführliche Installations- und Einrichtungsanleitung](INSTALLATION.md)** – Docker Compose, Portainer, Standalone-Build, Ersteinrichtung, Updates, Backup/Restore und Fehlerbehebung
- **[Fertige Portainer-Stack-Datei](portainer-stack.yaml)** – für das zuvor importierte Release-Image
- **[Benutzerhandbuch](HANDBUCH.md)** – Bedienung, Kontostände, Einnahmen, Ausgaben, Kredite, Vorschau und Excel-Export
- **[Changelog](CHANGELOG.md)** – Änderungen der einzelnen Versionen

## Funktionen

- mehrere Haushalte und Konten
- Konten können mit Bestätigung gelöscht werden; Zahlungspositionen bleiben zur Neuzuordnung erhalten
- historisierte Kontostände mit Kennzeichnung bereits enthaltener Tagesbuchungen
- Standardkonto für neue Einnahmen und Ausgaben
- Einnahmen und Ausgaben mit monatlichem, vierteljährlichem, halbjährlichem, jährlichem oder einmaligem Rhythmus und optionalem Enddatum
- zusätzlicher wöchentlicher Rhythmus für Ausgaben mit einer Fälligkeit alle sieben Tage
- automatische Bereinigung unsichtbarer Zukunftsversionen aus älteren Programmständen
- Saldo aller angelegten Positionen direkt auf den Einnahmen- und Ausgabenseiten
- automatische Aufteilung von Ausgaben und Umbuchungen in Aktiv und Archiv
- einmalige Positionen wechseln nach ihrem Fälligkeitsdatum automatisch ins Archiv
- eigene Kreditverwaltung für Konsumkredit, Kredit und Geliehen
- Kreditliste mit direktem Filter und Anzahl je Kreditart
- automatische Archivierung vollständig getilgter Kredite bei 0,00 € Restschuld
- manuelle Kreditarchivierung mit Ausschluss aus aktiver Berechnung und Vorschau
- stichtagsbezogene Kreditsalden bei der Zukunftsbetrachtung auf dem Dashboard
- vollständige Kredit-Historie aus verknüpften Ausgaben und manuellen Tilgungen
- getrennter Abbuchungs- und Tilgungsbetrag für Annuitäten
- zukünftige Tilgungen werden angezeigt, wirken aber erst ab ihrem Datum auf den Kreditsaldo
- überzahlte Kredite bleiben bei einem offenen Saldo von 0,00 € und werden nicht als Forderung dargestellt
- vorzeitig vollständig getilgte Kredite stoppen automatisch alle späteren verknüpften Ausgaben
- eine zu hohe Schlussrate wird bei Kontobelastung und Tilgung automatisch auf die verbleibende Restschuld begrenzt
- Restschulden unter 3,00 € werden bei einem hinterlegten Enddatum automatisch der letzten Rate zugeschlagen
- Umbuchungen mit Rhythmus, optionalem Enddatum und optionaler Ausführungsanzahl
- Dashboard-Summen aus den im gewählten Monat tatsächlich fälligen Einnahmen und Ausgaben
- vollständige Dashboard-Aufteilung ohne Begrenzung auf acht Positionen
- Schnellaktionen zum Anlegen neuer Einnahmen und Ausgaben direkt auf dem Dashboard
- taggenaue Monatsvorschau für Konten sowie separat auswählbare Kreditsimulation
- dauerhaft gespeicherter Erledigt-Status je konkreter Bewegung; erledigte Vorgänge bleiben sichtbar und werden nicht erneut simuliert
- strukturierter Excel-Export mit Monats-/Tagesvorschau, Krediten, Tilgungshistorie, Bewegungen und sämtlichen Eingaben
- Warnung bei Überschreitung eines hinterlegten Disporahmens
- Datenprüfung für nicht berücksichtigte oder unvollständige Positionen

Importfunktionen und Zinsberechnungen sind nicht Bestandteil dieser Version.

## Schnellstart mit Docker

Voraussetzungen: Docker Engine mit Docker Compose.

```bash
git clone https://github.com/lrdtiberius/finanzlab.git
cd finanzlab
docker compose up --build -d
```

Danach ist die Anwendung auf dem lokalen Rechner erreichbar:

```text
http://localhost:8798
```

Von einem anderen Gerät im Netzwerk wird `localhost` durch die IP-Adresse oder den Hostnamen des Docker-Rechners ersetzt.

Der Port kann in `compose.yaml` angepasst werden. Die Anwendungsdaten liegen ausschließlich im Docker-Volume `finanzlab_data` und gehören nicht zum Repository.

Für Portainer, Standalone-Builds, Updates, Datensicherung und eine vollständige Ersteinrichtung siehe **[INSTALLATION.md](INSTALLATION.md)**.

Stoppen:

```bash
docker compose down
```

Stoppen und lokale Anwendungsdaten löschen:

```bash
docker compose down -v
```

> Achtung: `docker compose down -v` löscht zusätzlich das Daten-Volume und damit die gespeicherten Haushaltsdaten.

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

Das vollständige Benutzerhandbuch mit Kontostand-Logik, Krediten, Vorschau, Excel-Export und Fehlerbehebung steht in [HANDBUCH.md](HANDBUCH.md).

## Datenschutz

Das Repository enthält keine Kontostände, Transaktionen, Haushaltsnamen, privaten Netzwerkadressen oder Zugangsdaten. Persönliche Anwendungsdaten entstehen erst beim lokalen Betrieb und werden unter `DATA_DIR` beziehungsweise im Docker-Volume gespeichert.

Vor einer Veröffentlichung eigener Änderungen sollten insbesondere Datenbanken, Backups, Screenshots, Protokolle und `.env`-Dateien ausgeschlossen bleiben.

## Releases

Ein Tag im Format `v*` startet den enthaltenen GitHub-Workflow. Er führt die Tests aus und veröffentlicht ein GitHub-Release mit:

- dem vollständigen Quellpaket,
- einem direkt mit `docker load` oder über **Portainer → Images → Import** ladbaren Docker-Image für `linux/amd64`,
- SHA-256-Prüfsummen für beide Dateien.

Für Portainer gilt: Das fertige Docker-Image gehört zu **Images → Import**. Ein Quell-/Build-TAR mit Dockerfile gehört dagegen zu **Images → Build image → Upload**.

Der Excel-Export wird in der Anwendung unter **Einstellungen** gestartet. Der Zeitraum ist auf höchstens 24 Monate begrenzt; alle eingegebenen Einnahmen, Ausgaben, Kredite und Tilgungen werden unabhängig vom Vorschauzeitraum vollständig in eigenen Tabellenblättern ausgegeben.

## Autor und Unterstützung

Entwickelt von **Lrd.Tiberius**. Wer das Projekt unterstützen möchte, findet den „Buy me a coffee“-Link direkt in der Anwendung.
