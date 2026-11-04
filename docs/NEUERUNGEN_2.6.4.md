# FinanzLab – Neuerungen in Version 2.6.4

## Heutige Kontostände im Dashboard

Der grüne Kopfbereich des Dashboards zeigt zusätzlich die bis zum heutigen Tag berechneten Kontostände ausgewählter normaler Bankkonten. Die Anzeige bleibt auf dem heutigen Datum, auch wenn für die Monatsprognose ein anderer Monat gewählt wird.

Die Werte stammen aus derselben serverseitigen Tagesberechnung wie die Kontovorschau. Dadurch wirken sich insbesondere folgende Änderungen auch auf die neuen Kacheln aus:

- als **Vorgang erledigt** markierte Buchungen,
- über **Betrag ändern** korrigierte Ausgaben,
- mit **Entfällt** aus der Planung herausgenommene Vorgänge,
- geplante Einnahmen, Ausgaben und Umbuchungen bis einschließlich heute.

## Kontenauswahl in den Einstellungen

Der **Excel-Export** bleibt der oberste Bereich der Einstellungen. Direkt darunter können je Haushalt ein bis vier normale Bankkonten für die heutigen Kontostände ausgewählt werden. Die Auswahl wird im verwendeten Browser gespeichert. Gelöschte Konten werden automatisch aus der Auswahl entfernt; Rahmenkredite werden weiterhin separat dargestellt und nicht angeboten.

## Update

Vor dem Update eine externe Sicherung des Datenvolumes anlegen. Beim Austausch des Images müssen derselbe `/data`-Mount und dieselben Zugriffsrechte erhalten bleiben. Alte und neue Version dürfen nicht gleichzeitig dieselbe SQLite-Datenbank verwenden.
