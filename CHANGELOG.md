# Changelog

## 0.11.6

- Enddatum und Ausführungsanzahl einer Umbuchung müssen dieselbe letzte Ausführung beschreiben
- klare Fehlermeldung mit dem zur Anzahl passenden Enddatum
- einmalige Umbuchungen erlauben nur genau eine Ausführung
- fehlende erste Fälligkeiten werden nicht mehr unbemerkt durch das heutige Datum ersetzt
- ungültige Kontostandsdaten beim ersten Konto werden vor dem Speichern abgewiesen
- verbliebene, ungenutzte Zinsberechnung aus der Domänenlogik entfernt

## 0.11.5

- strukturierter Excel-Export unter Einstellungen
- Monats- und Tagesprognose aus den tatsächlichen Fälligkeiten des gewählten Zeitraums
- eigene Tabellenblätter für Bewegungen, Konten, Einnahmen, Ausgaben, Umbuchungen und Kontostand-Historie
- Saldo aller angelegten Einnahmen beziehungsweise Ausgaben im Kopf der jeweiligen Karte
- maximaler Exportzeitraum von 24 Monaten und vollständig formatierte Geld-, Datums- und Warnfelder
- vollständiges deutschsprachiges Handbuch für Installation, Bedienung, Berechnungslogik, Datensicherung und Fehlerbehebung

## 0.11.4

- getrennte Seiten für Konten und Einnahmen
- historisierte Kontostände und Standardkonto
- Dashboard, Tagesprognose und taggenaue Monatsvorschau
- Ausgaben mit optionalem, einschließlich geltendem Enddatum oder Dauer
- Ausgabeart „Kredit“
- Umbuchungen mit optionalem Enddatum und optionaler Ausführungsanzahl
- Warnungen bei Überschreitung des Disporahmens
- Datenprüfung für nicht berücksichtigte Positionen
- vollständige Entfernung der Importoberflächen
- Entfernung eigenständiger Kredit- und Zinsfunktionen
