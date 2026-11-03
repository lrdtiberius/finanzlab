# FinanzLab – Neuerungen von 2.6.0 bis 2.6.3

## Schnellere Berechnung und kleinerer Startumfang ab 2.6.0

- Wiederkehrende Fälligkeiten werden direkt zum relevanten Zeitraum vorgespult statt Tag für Tag durchlaufen.
- Kredit- und Zinsabfragen sind gebündelt; die Liquiditätsvorschau verwendet eine gemeinsame Kredit-Zeitachse und einen revisionsgebundenen Cache.
- Beim Start werden kompakte Kreditübersichten geladen. Vollständige Zahlungsdaten, Einstellungen, Diagnosen, Sicherungen, EnergyLab-Status und Zinsdaten folgen erst beim Öffnen des jeweiligen Bereichs.
- Text- und JavaScript-Dateien werden komprimiert übertragen; versionierte statische Dateien können langfristig zwischengespeichert werden.

## Sofortige Neuberechnung ab 2.6.1

Wird in der Monatsvorschau **Vorgang erledigt** geändert oder über **Betrag ändern** ein abweichender Betrag gespeichert, leert FinanzLab den Prognosecache und lädt Dashboard sowie die bereits sichtbare Vorschau neu. Tageswerte und Monatsendstand ändern sich ohne manuelles Neuladen.

## Einzelne Vorgänge entfallen lassen ab 2.6.2

Die Checkbox **Entfällt** lässt eine Vorschau-Position sichtbar, nimmt sie aber aus der Berechnung heraus. Das betrifft:

- den prognostizierten Kontostand,
- monatliche Einnahmen und Ausgaben,
- **Operativ frei**,
- **Liquiditätsänderung**,
- verknüpfte Kredit- und Umbuchungsfolgen.

**Vorgang erledigt** und **Entfällt** schließen sich gegenseitig aus. Eine spätere Rücknahme stellt die reguläre Berechnung wieder her.

## Kompaktere Einstellungen und Sicherungsaufbewahrung ab 2.6.3

- **Dispolimit und Sondertilgungen** nutzt die gesamte Breite.
- **Haushalt** und **Personen** stehen darunter nebeneinander.
- Die Oberfläche zeigt höchstens zwölf Sicherungen in drei Spalten und vier Zeilen.
- Auch Sicherungsdateien und Registereinträge werden auf die zwölf neuesten oder zuletzt wiederhergestellten Einträge begrenzt.
- Vor jeder Wiederherstellung entsteht weiterhin eine zusätzliche Sicherheitssicherung. Die ausgewählte Sicherung bleibt bis zum Abschluss geschützt.

## Update

Vor dem Update eine externe Sicherung des Datenvolumes anlegen. Beim Austausch des Images müssen derselbe `/data`-Mount und dieselben Zugriffsrechte erhalten bleiben. Alte und neue Version dürfen nicht gleichzeitig dieselbe SQLite-Datenbank verwenden.
