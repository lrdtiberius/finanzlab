# Changelog

## 0.12.3

- Checkbox „Vorgang erledigt“ bei jeder geplanten Bewegung in der Monatsvorschau
- Erledigt-Status wird pro Position und Fälligkeitsdatum dauerhaft gespeichert und kann wieder aufgehoben werden
- erledigte Bewegungen bleiben sichtbar, verändern aber Kontostand, Tagesänderung und Monatssummen nicht mehr
- Umbuchungen werden immer für Ausgangs- und Zielkonto gemeinsam als erledigt behandelt
- Excel-Export weist Erledigt-Status und tatsächliche Einrechnung jeder Bewegung getrennt aus
- Persistenz, Rücknahme und Berechnung nach einem Neustart durch Regressionstests abgesichert

## 0.12.2

- neuer Rhythmus „Halbjährlich“ für Einnahmen und Ausgaben
- halbjährliche Fälligkeiten werden im festen Abstand von sechs Monaten berechnet und in Dashboard, Vorschau sowie Excel-Export korrekt berücksichtigt
- Umbuchungen unterstützen den halbjährlichen Rhythmus ebenfalls, einschließlich Prüfung von Ende und Ausführungsanzahl
- Regressionstest für zwei aufeinanderfolgende halbjährliche Fälligkeiten und einen dazwischenliegenden Monat ohne Buchung

## 0.12.1

- Konten können nun direkt im Bearbeitungsdialog gelöscht werden
- Kontostand-Historie und betroffene Umbuchungen werden nach ausdrücklicher Bestätigung entfernt
- verknüpfte Einnahmen und Ausgaben bleiben erhalten und werden zur sicheren Neuzuordnung auf „Kein Konto“ gesetzt
- beim Löschen des Standardkontos wird automatisch ein verbleibendes Konto als neues Standardkonto bestimmt
- Kontolöschung über die API sowie dauerhafte Speicherung nach einem Neustart durch Regressionstests abgesichert

## 0.12.0

- ungenutzte Seite „Prognose“ aus der Navigation und Oberfläche entfernt
- neue Seite „Kredite“ mit den Arten Konsumkredit, Kredit und Geliehen
- vollständige Kredit-Historie aus verknüpften Ausgaben und manuellen Tilgungen
- zukünftige Tilgungen werden grau angezeigt und erst an ihrem Datum saldowirksam
- Kontoabbuchung und tatsächlicher Tilgungsanteil können bei Annuitäten getrennt erfasst werden
- Dashboard zeigt Anzahl und offenen Gesamtsaldo je Kreditart
- Kredite lassen sich in der Monatsvorschau getrennt auswählen und simulieren, ohne die Kontensumme zu verändern
- Datenprüfung erkennt fehlende, gelöschte oder unpassende Kredit-Verknüpfungen
- Excel-Export um Kredite, Kreditzahlungen und eine separate monatliche Kreditvorschau erweitert

## 0.11.7

- beim Erfassen eines neuen Kontostands wird der aktuell gewählte Stichtag verwendet, statt unbemerkt einen älteren Historieneintrag zu überschreiben
- nach dem Speichern wechselt die Ansicht auf das Datum des gespeicherten Kontostands und zeigt den übernommenen Wert sofort an
- Betrag, Datum und Status der Tageszahlungen werden anhand der Serverantwort bestätigt
- die Checkbox „Zahlungen an diesem Tag sind im Kontostand bereits enthalten“ zeigt ihre Berechnungswirkung direkt im Dialog an
- zusätzlicher Neustarttest für die dauerhafte Speicherung beider Checkbox-Zustände

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
