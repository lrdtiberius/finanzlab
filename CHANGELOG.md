# Changelog

## 1.7.1

- Quellstand mit dem am 26. September 2026 gebauten und auf dem AM06 laufenden Produktionsimage synchronisiert.
- Sondertilgungen bei Konsumfinanzierungen reduzieren jetzt zusätzlich die noch verzinsliche Produktpreis-Restbasis.
- Wird das eigentliche Kapital durch Korrektur und Ablöse vollständig getilgt, bleiben keine zukünftigen Finanzierungskosten als Phantom-Restsaldo stehen.
- Nach vollständiger Ablösung werden alle späteren Raten weiterhin angezeigt, aber als `credit_repaid` weder dem Konto noch dem Kredit belastet.
- Monatsvorschau und Kreditverlauf verwenden dieselbe chronologische Behandlung manueller Tilgungen und geplanter Raten.
- Zwei Regressionstests decken Kreditvorschau und vollständige Ablösung durch Sondertilgung ab.
- Bestehende Regressionstests bleiben vollständig erhalten; neun veraltete Erwartungen sind als bekannte Abweichungen markiert.
- README, Benutzerhandbuch und Installationsanleitung beschreiben die integrierten Datenbanksicherungen, Prüfsummen- und SQLite-Integritätskontrolle sowie `/data/backups`.
- Sicherungen im selben Docker-Volume werden ausdrücklich nicht als Ersatz für ein externes Volume-Backup dargestellt.

## 1.6.2 bis 1.6.14

- Beim Bearbeiten bestehender Konsumkredite bleiben Anbieter-, Preis-, Aufpreis-, Saldo- und Zahlungsplanwerte erhalten.
- Altverträge mit Gebühren, abweichenden Raten oder nur noch verbleibenden Zahlungen werden nicht mehr automatisch auf eine theoretische Vertragsrechnung zurückgesetzt.
- Zahlungsanzahl, Vorschau und Speicherprüfung wurden über mehrere Korrekturen stabilisiert.
- Die Kreditverwaltung wird als eigene JavaScript-Datei ausgeliefert; der Standalone-Container ist nicht von einem vorher zusammengefügten Skript abhängig.

## 1.6.1

- In der Zinsauswertung lassen sich aktive und archivierte Kredite einzeln auswählen.
- Nur ausgewählte Kredite werden unter „Zinsen je Kredit“ angezeigt und in „Kreditzinsen“, „Geplante Kreditzinsen“ sowie „Zinsen gesamt“ eingerechnet.
- Aktive Kredite sind beim Öffnen eines Haushalts vorausgewählt; archivierte Kredite können bei Bedarf zugeschaltet werden.
- Girokontozinsen bleiben von der Kreditauswahl unabhängig und werden weiterhin in „Zinsen gesamt“ berücksichtigt.
- Installationsanleitung und Benutzerhandbuch beschreiben Version 1.6.1 einschließlich Kredit-, Archiv- und Zinslogik.

## 1.6.0

- Automatisch berechnete Konsumkredite verwenden den Produktpreis als verzinslichen Anfangssaldo; der Finanzierungspreis wird nicht erneut verzinst.
- Monatsrate, Zahlungsanzahl und Schlussrate werden gegen den Finanzierungspreis plausibilisiert, übliche Cent-Rundungsdifferenzen werden toleriert.
- Die Zinsauswertung zeigt „Kreditzinsen“, „Geplante Kreditzinsen“, „Zinsen Girokonto“ und „Zinsen gesamt“; die frühere Anzeige „Gebuchte Zinsen“ entfällt.
- Girokontozinsen lassen sich direkt aus der Zinsauswertung als Kontoausgabe erfassen.
- Negative manuelle Tilgungen werden als Kreditaufstockung behandelt, erhöhen die Restschuld und fließen in folgende Zinsberechnungen ein.
- Bestehende manuelle Kreditdaten und Zinswerte bleiben kompatibel.
- Wochenendfälligkeiten werden weiterhin auf den vorherigen Freitag verschoben.

## 1.0.2

- ein in EnergyLab ausdrücklich gesetztes Datum „Erste Zahlung“ wird als tatsächlicher Beginn des Zahlungsrhythmus übernommen

## 1.0.1

- EnergyLab-Abwasserverträge werden als eigene Ausgaben übernommen
- monatliche, quartalsweise, halbjährliche und jährliche Zahlungsrhythmen aus EnergyLab bleiben bei der Synchronisation erhalten
- Betragsänderungen behalten auch bei nicht monatlichen Zahlungen den ursprünglichen Vertragstakt bei

## 1.0.0

- EnergyLab-Verträge für Strom, Gas und Wasser werden als monatliche Abschläge übernommen, ohne Verbrauchskosten, Grundgebühr, Hochrechnung oder Saldo doppelt zu buchen
- Vertragswechsel, geänderte Abschlagshöhen, Laufzeiten, Zahlungstage und Kontozuordnungen bleiben historisch korrekt und werden bei erneuter Synchronisation ohne Dubletten aktualisiert
- EnergyLab-Kontennamen und Zahlungstage werden je Vertrag übernommen; unbekannte Konten fallen mit einem sichtbaren Hinweis auf das Standardkonto zurück
- Einnahmen besitzen wie Ausgaben die Bereiche „Aktiv“ und „Archiv“; vergangene einmalige Einnahmen werden automatisch archiviert
- wiederkehrende Einnahmen wie Gehalt oder Rente können über „Betrag ändern“ ab einem frei wählbaren Datum aktualisiert werden, während frühere Zahlungen ihren alten Betrag behalten
- der Excel-Export steht in den Einstellungen als eigene Kachel neben der EnergyLab-Verbindung und bleibt auf kleineren Bildschirmen responsiv
- der Excel-Export enthält Vorschauen, Bewegungen, Konten, Einnahmen, Ausgaben, Kredite, Tilgungen, Umbuchungen und Kontostand-Historie
- Docker-, Healthcheck- und Versionsangaben wurden für das stabile Release 1.0.0 vereinheitlicht

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
