# Changelog

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
- eine normale Bearbeitung ersetzt die sichtbare Position ab heute vollständig und kann nicht mehr unbemerkt von einer alten Zukunftsversion überschrieben werden
- wiederkehrende Kreditraten erscheinen dadurch zuverlässig an allen künftigen Fälligkeitstagen in Vorschau, Dashboard, Kreditverlauf und Excel-Export
- Cent-Restbeträge werden über die vorletzte volle Rate und eine automatisch gekürzte Schlussrate vollständig bis 0,00 € fortgeschrieben
- Regressionstests decken die reale Mobilezone-Konstellation, vorhandene Altversionen und alle drei Kreditarten ab

## 0.12.8

- Kreditverläufe werden strikt chronologisch berechnet; manuelle Tilgungen wirken am selben Tag vor geplanten Raten
- erreicht ein Kredit durch eine vorzeitige Tilgung 0,00 €, werden alle späteren verknüpften Ausgaben nicht mehr in Konto, Dashboard, Vorschau oder Excel-Prognose eingerechnet
- ist die nächste geplante Rate höher als die Restschuld, werden Kontobelastung und Tilgung automatisch auf die tatsächliche Restschuld begrenzt
- entfallene und gekürzte Raten bleiben in Vorschau, Kreditplanung und Excel-Export mit einem eindeutigen Berechnungshinweis sichtbar

## 0.12.7

- Kreditsalden auf dem Dashboard folgen jetzt dem dort gewählten Stichtag
- bei zukünftigen Stichtagen werden verknüpfte Tilgungsanteile und manuelle Tilgungen bis einschließlich dieses Tages simuliert
- Zahlungen nach dem gewählten Stichtag beeinflussen den angezeigten Kreditsaldo nicht
- die normale Kreditseite zeigt weiterhin den realen Saldo zum heutigen Datum
- übersteigt eine Schlussrate den Restbetrag, wird der offene Kreditsaldo auf 0,00 € begrenzt und niemals als Forderung dargestellt

## 0.12.6

- zwei links angeordnete Schnellaktionen für neue Ausgaben und Einnahmen direkt auf dem Dashboard
- die Schnellaktionen verwenden dieselben Dialoge, Prüfungen und Speicherwege wie die Verwaltungsseiten
- neu angelegte Positionen erscheinen sofort auf der jeweiligen Seite sowie in Dashboard und Vorschau

## 0.12.5

- Dashboard-Summen enthalten nur Einnahmen und Ausgaben, die im Monat des gewählten Stichtags tatsächlich fällig sind
- vierteljährliche, halbjährliche und jährliche Positionen erscheinen mit dem vollständigen Betrag ausschließlich in ihrem Fälligkeitsmonat
- Startdatum, Enddatum, Version und Aktivstatus werden bei der Monatszusammenfassung berücksichtigt
- Dashboard-Monatssummen und Monatsvorschau werden durch einen gemeinsamen Regressionstest abgeglichen

## 0.12.4

- Kreditseite um einen direkten Filter für Alle, Konsumkredit, Kredit und Geliehen erweitert
- jeder Filter zeigt die Anzahl der enthaltenen Kredite und aktualisiert Überschrift sowie Liste sofort
- nach dem Anlegen oder Ändern eines Kredits wird automatisch dessen Kreditart angezeigt
- Filterzustand und leere Trefferlisten sind eindeutig und barrierearm beschriftet

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
