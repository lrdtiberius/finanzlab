# Changelog

## 0.13.5

- Kredite, Konsumkredite und Geliehen werden automatisch archiviert, sobald ihr aktueller Saldo 0,00 € erreicht
- im Tab „Kredite“ gibt es einen eigenen Filter „Archiv“ für alle automatisch und manuell archivierten Kredite
- jeder Kredit kann über eine Checkbox manuell archiviert werden
- archivierte Kredite werden aus den Kredit-Summen und der Kreditauswahl in der Monatsvorschau entfernt
- bei manueller Archivierung werden verknüpfte Kredit-Ausgaben für die Berechnung deaktiviert; beim Reaktivieren wird ihr vorheriger Aktivstatus wiederhergestellt
- automatisch abbezahlte Kredite verwenden weiterhin die bestehende Schlussraten- und „bereits getilgt“-Logik und erzeugen keine weiteren Belastungen

## 0.13.4

- Ausgaben unterstützen zusätzlich den Rhythmus „Wöchentlich“
- ausgehend von der ersten Fälligkeit wird die Ausgabe exakt alle sieben Tage berücksichtigt
- wöchentliche Ausgaben fließen vollständig in Dashboard, Monatsvorschau, Kreditverlauf und Excel-Export ein
- ein gesetztes Enddatum bleibt einschließlich gültig; die letzte wöchentliche Fälligkeit am Enddatum wird noch gebucht
- bei Einnahmen und Umbuchungen bleibt der wöchentliche Rhythmus bewusst ausgeschlossen
- Regressionstests decken Monatswechsel, Enddatum, Archivierung, Dashboard-Summe, Excel-Export und die Ablehnung bei Einnahmen ab

## 0.13.3

- einmalige Ausgaben werden nach Ablauf ihres Fälligkeitsdatums automatisch archiviert, auch wenn kein separates Enddatum hinterlegt ist
- das Fälligkeitsdatum gilt bei einmaligen Ausgaben einschließlich: am Fälligkeitstag aktiv, ab dem Folgetag archiviert
- dieselbe Regel gilt für einmalige Umbuchungen
- die serverseitige Lebenszyklusprüfung kennzeichnet vergangene einmalige Ausgaben nun ebenfalls als beendet
- zusätzlicher Regressionstest prüft Vergangenheit, heutigen Grenztag und zukünftige einmalige Ausgaben

## 0.13.2

- Ausgaben werden automatisch in die Bereiche „Aktiv“ und „Archiv“ aufgeteilt
- Ausgaben mit einem Enddatum vor dem heutigen Tag erscheinen im Archiv; das Enddatum selbst zählt weiterhin als aktiver Tag
- Umbuchungen verwenden dieselbe automatische Aufteilung in „Aktiv“ und „Archiv“
- Anzahl der enthaltenen Positionen wird direkt in den beiden Statusfiltern angezeigt
- verlängerte oder entfernte Enddaten holen eine archivierte Position automatisch zurück in den aktiven Bereich
- die monatliche Aufteilung auf dem Dashboard zeigt jetzt sämtliche im gewählten Monat fälligen Einnahmen und Ausgaben statt höchstens acht Positionen
- Regressionstest mit zehn gleichzeitig fälligen Ausgaben stellt die vollständige Dashboard-Liste und deren Gesamtsumme sicher

## 0.13.1

- bei kreditverknüpften Ausgaben mit Enddatum wird ein nach der letzten planmäßigen Rate verbleibender Rest von weniger als 3,00 € automatisch der Schlussrate zugeschlagen
- Kontoabbuchung und Kredittilgung werden dabei gemeinsam erhöht, sodass der Kredit am angegebenen Ende exakt 0,00 € erreicht
- ohne Enddatum sowie bei einer Restschuld ab 3,00 € bleibt der reguläre Zahlungsplan unverändert
- Vorschau, Kredithistorie und Excel-Export kennzeichnen den automatisch in der Schlussrate enthaltenen Restbetrag
- die Schlussratenregel ist für Konsumkredit, Kredit und Geliehen sowie die Grenzwerte 2,99 € und 3,00 € getestet

## 0.13.0

- unsichtbare zukünftige Altversionen von Einnahmen und Ausgaben werden beim ersten Start automatisch bereinigt
