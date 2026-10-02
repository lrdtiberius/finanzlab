# Handbuch zum Haushaltsplaner

Gültig für Version **2.1.1**

Der Haushaltsplaner ist eine lokal betriebene Webanwendung für die tagesgenaue Liquiditätsplanung. Er verbindet historisierte Kontostände mit geplanten Einnahmen, Ausgaben und Umbuchungen. Zusätzlich verwaltet er Kredite mit eigener Zahlungshistorie. Daraus entstehen Tages- und Monatsvorschauen für Konten sowie eine davon getrennte Kreditsimulation.

## 1. Grundprinzip

Die Anwendung unterscheidet zwischen:

- **gespeicherten Kontoständen** als bestätigten Ausgangspunkten,
- **Einnahmen und Ausgaben** mit Datum und Zahlungsrhythmus,
- **Umbuchungen** zwischen eigenen Konten,
- **Krediten und Tilgungen** mit einer eigenen Historie,
- **berechneten Kontoständen** und separat simulierten Kreditsalden für zukünftige Tage.

Ein gespeicherter Kontostand wird nicht durch eine Berechnung überschrieben. Neue Kontostände werden als weitere Einträge in der Historie gespeichert. Für eine Berechnung verwendet die Anwendung je Konto den jüngsten geeigneten Stand vor oder am gewählten Stichtag.

## 2. Installation

Eine vollständige Schritt-für-Schritt-Anleitung für Portainer, Docker Compose, Ersteinrichtung, Sicherung, Wiederherstellung und Updates steht in **[INSTALLATION.md](INSTALLATION.md)**. Die folgenden Abschnitte fassen den Schnellstart zusammen.

### 2.1 Docker Compose

Voraussetzungen:

- Docker Engine
- Docker Compose
- ein freier Port `8798`

Repository laden und Anwendung starten:

```bash
git clone https://github.com/lrdtiberius/finanzlab.git
cd finanzlab
docker compose up --build -d
```

Danach ist die Anwendung auf dem Docker-Rechner erreichbar:

```text
http://localhost:8798
```

Von einem anderen Gerät im selben Netzwerk wird `localhost` durch den Namen oder die IP-Adresse des Docker-Rechners ersetzt:

```text
http://<SERVER-IP>:8798
```

Status prüfen:

```bash
docker compose ps
```

Protokoll anzeigen:

```bash
docker compose logs -f haushaltsplaner
```

Anwendung stoppen:

```bash
docker compose down
```

> `docker compose down -v` löscht zusätzlich das Daten-Volume. Dieser Befehl darf nur verwendet werden, wenn die gespeicherten Haushaltsdaten wirklich entfernt werden sollen.

### 2.2 Portainer

Für eine Portainer-Installation wird das fertig gebaute Docker-Image aus dem GitHub-Release verwendet.

Vorgehen:

1. unter **Images → Import** das GitHub-Release-Archiv `finanzlab-image-v2.1.1-amd64.tar.gz` importieren,
2. unter **Stacks → Add stack** einen Stack mit dem Inhalt aus [`portainer-stack.yaml`](portainer-stack.yaml) anlegen,
3. den Stack bereitstellen,
4. den Zustand des Containers `finanzlab` kontrollieren,
5. Port `8798` im Browser öffnen.

Die Image-TAR enthält das direkt ladbare Docker-Image `finanzlab:2.1.1` für `linux/amd64`. Das Quellarchiv `finanzlab-v2.1.1.tar.gz` ist kein Docker-Image und darf nicht unter **Images → Import** verwendet werden. Ebenso darf das Image nicht auf der Portainer-Seite **Build a new image** hochgeladen werden.

Das Volume wird im Container unter `/data` eingebunden. Dort liegt insbesondere die Datenbankdatei `planner.db`.

## 3. Erster Start

Beim ersten Start öffnet sich der Einrichtungsdialog.

1. Namen des Haushalts eingeben.
2. Einzelperson oder Paar auswählen.
3. Namen der Person beziehungsweise der beiden Personen eingeben.
4. Optional direkt das erste Konto anlegen.
5. Kontostand und Datum des Kontostands eintragen.
6. Festlegen, ob die Buchungen dieses Tages bereits im Kontostand enthalten sind.

Weitere Haushalte können später unter **Einstellungen** angelegt werden.

## 4. Navigation

Die Anwendung enthält folgende Seiten:

| Seite | Zweck |
| --- | --- |
| Dashboard | Gesamtüberblick zum gewählten Stichtag |
| Vorschau | Tagesliste und Kontostände eines vollständigen Monats |
| Konten | Konten, Disporahmen und Kontostand-Historie |
| Einnahmen | Regelmäßige und einmalige Einnahmen, Archiv und historische Betragsänderungen |
| Ausgaben | Manuelle und aus EnergyLab synchronisierte Ausgaben, optional mit einem Kredit und Tilgungsanteil verknüpft |
| Kredite | Kreditstammdaten, offene Salden und vollständige Tilgungshistorie |
| Zinsen | Auswertung bisheriger und geplanter Kreditzinsen sowie erfasster Girokontozinsen |
| Umbuchungen | Geldbewegungen zwischen eigenen Konten |
| Einstellungen | Haushalte, Personen, EnergyLab-Verbindung, Excel-Export und Datenprüfung |

## 5. Konten und Kontostände

### 5.1 Konto anlegen

Unter **Konten** auf **+ Konto** klicken und folgende Angaben erfassen:

- Kontoname
- Besitzer
- optionaler Disporahmen
- optional: als Standardkonto verwenden
- Kontostand
- Datum des Kontostands
- Status der Tagesbuchungen

### 5.2 Standardkonto

Genau ein Konto kann als Standardkonto markiert sein. Beim Anlegen einer Einnahme oder Ausgabe wird dieses Konto vorausgewählt. Die Auswahl kann im jeweiligen Dialog jederzeit geändert werden.

### 5.3 Kontostand-Historie

Jeder neu gespeicherte Kontostand wird als eigener historischer Eintrag abgelegt. Dadurch kann beispielsweise heute ein Stand für heute und morgen ein neuer Stand für morgen erfasst werden.

Beim Öffnen des Kontodialogs wird das aktuell in der Anwendung gewählte Stichtagsdatum für den neuen Eintrag vorbelegt. Nach dem Speichern wechselt die Ansicht auf dieses Datum, damit der übernommene Kontostand sofort kontrolliert werden kann. Existiert für das gewählte Datum bereits ein Eintrag, wird genau dieser aktualisiert; andere Tage der Historie bleiben erhalten.

Die Historie ist im Bearbeitungsdialog des Kontos sichtbar. Manuell erfasste Einträge können gelöscht werden, solange mindestens ein verwendbarer Kontostand für das Konto erhalten bleibt.

### 5.4 Checkbox für Tagesbuchungen

Die Checkbox **Zahlungen an diesem Tag sind im Kontostand bereits enthalten** beeinflusst die Berechnung am Datum des Kontostands. Der Hinweis unter der Checkbox zeigt ihre aktuelle Wirkung sofort an:

- **aktiviert:** Einnahmen, Ausgaben und Umbuchungen dieses Tages werden nicht noch einmal auf den gespeicherten Stand gerechnet;
- **nicht aktiviert:** die an diesem Tag fälligen Bewegungen werden ab dem gespeicherten Stand berücksichtigt.

Damit werden doppelte Berechnungen vermieden, wenn ein Kontostand bereits den vollständigen Buchungstag abbildet.

### 5.5 Disporahmen

Der Disporahmen wird als positiver Betrag eingegeben. Beispiel: `800,00 €` erlaubt einen Kontostand bis `−800,00 €`.

Sinkt ein simulierter Stand unter diesen Wert, zeigt die Anwendung eine Warnung mit dem überschrittenen Betrag. Die Warnung erscheint auch in der Monatsvorschau und im Excel-Export.

Eine automatische Berechnung von Dispozinsen ist nicht Bestandteil der Anwendung. Kreditzinsen und manuell erfasste Girokontozinsen werden auf der eigenen Seite **Zinsen** ausgewertet.

### 5.6 Konto löschen

Im Bearbeitungsdialog eines bestehenden Kontos steht **Konto löschen** zur Verfügung. Vor dem Löschen zeigt die Anwendung eine ausdrückliche Bestätigung mit den Folgen:

- die Kontostand-Historie des Kontos wird gelöscht,
- Umbuchungen mit diesem Konto werden gelöscht,
- Einnahmen und Ausgaben bleiben erhalten, verlieren aber ihre Kontozuordnung,
- ein verbleibendes Konto wird automatisch zum Standardkonto, falls das gelöschte Konto Standardkonto war.

Positionen ohne Konto erscheinen anschließend unter **Einstellungen → Datenprüfung** und können dort neu zugeordnet werden. Auch das letzte Konto eines Haushalts kann gelöscht werden; der Haushalt selbst bleibt bestehen.

## 6. Einnahmen

Unter **Einnahmen** können regelmäßige oder einmalige Zahlungseingänge angelegt werden.

Erforderliche Angaben:

- Bezeichnung
- Art
- Betrag
- Rhythmus
- erste beziehungsweise nächste Fälligkeit
- Konto
- bei einem Paar die Zuordnung zu einer Person oder gemeinsam

Verfügbare Rhythmen:

- monatlich
- vierteljährlich
- halbjährlich
- jährlich
- einmalig

Mit **In Berechnungen berücksichtigen** kann eine Einnahme vorübergehend deaktiviert werden, ohne sie zu löschen.

Im Kopf der Einnahmenkarte steht der positive Saldo aller angelegten Einnahmepositionen. Deaktivierte Positionen werden in diesem Bestandssaldo mitgezählt; für Vorschauen werden sie nicht berücksichtigt.

Über der Einnahmenliste stehen die Bereiche **Aktiv** und **Archiv**. Vergangene einmalige Einnahmen wechseln ab dem Tag nach ihrer Fälligkeit automatisch ins Archiv. Sie werden nicht gelöscht und können dort weiterhin geöffnet und bearbeitet werden.

Bei wiederkehrenden Einnahmen steht zusätzlich **Betrag ändern** zur Verfügung. Dort werden nur **Neuer Betrag ab** und **Neue Höhe** eingetragen. FinanzLab legt damit eine neue Version derselben Einnahme an: Frühere Fälligkeiten behalten den bisherigen Betrag, ab dem gewählten Datum gilt die neue Höhe. Bereits vorgemerkte zukünftige Änderungen werden direkt in der Einnahmenliste angezeigt.

Beispiel für eine Gehaltserhöhung:

- bisherige Einnahme: `2.500,00 €`, fällig jeweils am 25. des Monats;
- neuer Betrag ab: `01.10.2026`;
- neue Höhe: `2.650,00 €`.

Die Fälligkeiten bis September bleiben mit `2.500,00 €` gespeichert. Ab der Oktober-Fälligkeit verwendet Dashboard, Vorschau und Excel-Export `2.650,00 €`. Als Änderungsdatum sollte ein Datum gewählt werden, das spätestens auf der ersten Fälligkeit mit dem neuen Betrag liegt.

Für reine Betragsänderungen immer **Betrag ändern** verwenden. **Bearbeiten** ist für Bezeichnung, Art, Rhythmus, Fälligkeit, Konto, Zuordnung und Aktivstatus vorgesehen. Eine bereits eingetragene zukünftige Betragsänderung wird in der Zeile der Einnahme mit Datum und neuer Höhe angekündigt.

## 7. Ausgaben

Unter **Ausgaben** werden regelmäßige und einmalige Zahlungen verwaltet. Für Kreditraten stehen die Arten **Konsumkredit**, **Kredit** und **Geliehen** zur Verfügung. Nach der Auswahl muss ein Kredit derselben Art zugeordnet werden.

Erforderliche Angaben entsprechen grundsätzlich den Einnahmen. Zusätzlich können Ausgaben zeitlich begrenzt werden.

Als zusätzlicher Rhythmus steht bei Ausgaben **Wöchentlich** zur Verfügung. Die erste Fälligkeit bildet den festen Startpunkt; jede weitere Ausgabe wird exakt sieben Tage später berücksichtigt. Beispiel: Bei erster Fälligkeit am `19.08.2026` folgen `26.08.2026`, `02.09.2026`, `09.09.2026` und so weiter. Der Rhythmus gilt für Dashboard, Vorschau, Kreditverlauf und Excel-Export. Bei Einnahmen wird **Wöchentlich** nicht angeboten.

### 7.1 Enddatum

Das Enddatum gilt **einschließlich**. Eine an diesem Datum fällige Ausgabe wird noch berücksichtigt. Erst ab dem folgenden Tag darf sie nicht mehr in die Berechnung einfließen.

Beispiel:

- erste Fälligkeit: `15.08.2026`
- Enddatum: `15.11.2026`

Bei monatlichem Rhythmus werden die Fälligkeiten im August, September, Oktober und November berücksichtigt.

### 7.2 Dauer in Monaten

Alternativ kann eine Dauer angegeben werden. Eine Dauer von `12` setzt das Ende auf ein Jahr nach dem Startdatum.

Beispiel:

- erste Fälligkeit: `15.08.2026`
- Dauer: `12`
- berechnetes Enddatum: `15.08.2027`

Das berechnete Enddatum ist ebenfalls einschließlich gültig. Werden Enddatum und Dauer gemeinsam gesetzt, müssen beide Angaben zum selben Ergebnis führen.

### 7.3 Saldo aller Ausgaben

Im Kopf der Ausgabenkarte steht der negative Saldo aller angelegten Ausgabenpositionen. Archivierte und deaktivierte Positionen werden in diesem Bestandssaldo mitgezählt, aber nur zum gewählten Monat passende aktive Fälligkeiten fließen in Dashboard und Vorschauen ein.

Über der Ausgabenliste stehen die Bereiche **Aktiv** und **Archiv**. Die jeweilige Zahl zeigt, wie viele Positionen enthalten sind:

- **Aktiv:** wiederkehrende Ausgaben ohne Enddatum sowie Ausgaben, deren End- oder einmaliges Fälligkeitsdatum heute oder in der Zukunft liegt;
- **Archiv:** Ausgaben, deren Enddatum vor dem heutigen Datum liegt, sowie einmalige Ausgaben mit einer vergangenen Fälligkeit.

Das Enddatum bleibt einschließlich gültig. Eine Ausgabe mit Enddatum `24.08.2026` steht deshalb am 24.08. noch unter **Aktiv** und wechselt erst am 25.08. automatisch ins **Archiv**. Bei einer einmaligen Ausgabe übernimmt die Fälligkeit diese Funktion: Eine einmalige Ausgabe vom `18.08.2026` wird ab dem 19.08. im Archiv angezeigt. Wird das Enddatum einer archivierten wiederkehrenden Ausgabe verlängert oder entfernt, erscheint sie wieder unter **Aktiv**. Es werden keine Daten gelöscht; beide Bereiche bleiben vollständig bearbeitbar.

Beim Bearbeiten gilt die gespeicherte Konfiguration ab dem aktuellen Tag für alle folgenden Fälligkeiten. Nicht mehr sichtbare Zukunftsversionen aus älteren Programmständen werden beim ersten Start von Version 0.13.0 automatisch entfernt. Historische Konfigurationen vor dem aktuellen Tag und bereits gesetzte Erledigt-Markierungen bleiben erhalten.

### 7.4 Kontoabbuchung und Tilgung

Bei einer verknüpften Kredit-Ausgabe werden zwei Beträge unterschieden:

- **Betrag:** vollständige Abbuchung vom Bankkonto;
- **Davon Tilgung:** Anteil, der den offenen Kreditsaldo verringert.

Beispiel für ein Annuitätendarlehen: Bei einer Rate von `400,00 €` und einem Tilgungsanteil von `320,00 €` werden `400,00 €` vom Konto abgezogen, aber nur `320,00 €` in der Kredit-Historie gutgeschrieben. Die übrigen `80,00 €` werden nicht als Tilgung behandelt. Ein Tilgungswert von `0,00 €` erlaubt, den tatsächlich festgestellten Tilgungsanteil später manuell beim Kredit zu erfassen.

## 8. Kredite

Unter **Kredite** werden drei Arten verwaltet:

- Konsumkredit
- Kredit
- Geliehen

Beim Anlegen werden Bezeichnung, Art, Anfangssaldo, Zahlungsplan und optional der Sollzinssatz gespeichert. Bei einem Konsumkredit können zusätzlich Anbieter, Produktpreis, Finanzierungspreis und Ratenaufpreis eingetragen werden. Ein Klick auf den Kredit öffnet den aktuellen Saldo und die vollständige Zahlungshistorie.

Über der Kreditliste stehen die Filter **Alle**, **Konsumkredit**, **Kredit** und **Geliehen**. Die Zahl im jeweiligen Filter zeigt, wie viele Kredite dieser Art vorhanden sind. Der gewählte Filter wirkt nur auf die Liste; die drei Summenkarten darüber zeigen weiterhin jederzeit Anzahl und offenen Gesamtsaldo aller Kreditarten.

Die Historie enthält:

- automatisch erzeugte Tilgungen aus verknüpften Ausgaben,
- manuell erfasste Tilgungen,
- Datum, Betrag, Bezeichnung und Quelle jeder Tilgung,
- geplante zukünftige Tilgungen in grauer Darstellung.

Zukünftige Tilgungen reduzieren den aktuellen Kreditsaldo nicht. Sie werden erst am eingetragenen Datum saldowirksam. Manuelle Tilgungen können aus der Historie wieder gelöscht werden; automatisch erzeugte Einträge werden über die zugehörige Ausgabe geändert.

Ist die letzte Tilgung höher als der noch offene Betrag, bleibt der angezeigte offene Saldo bei **0,00 €**. Der rechnerische Mehrbetrag wird nicht als Forderung des Haushalts dargestellt und erhöht weder Dashboard noch Kreditseite oder Vorschau.

Alle manuellen und über Ausgaben geplanten Tilgungen werden in Datumsreihenfolge verarbeitet. Eine manuelle Tilgung wird am selben Tag vor einer geplanten Rate berücksichtigt. Erreicht der Kredit dadurch vorzeitig **0,00 €**, werden alle späteren verknüpften Ausgaben automatisch aus der Kontoberechnung entfernt. Sie bleiben in der Vorschau als **„Entfällt – Kredit bereits getilgt“** sichtbar, verändern aber weder Konto noch Monatswerte oder Kreditsaldo.

Ist bei einer noch offenen Restschuld die nächste geplante Rate zu hoch, wird die letzte Kontobelastung automatisch auf die Restschuld begrenzt. Beispiel: Bei einer geplanten Rate von `400,00 €`, einem Tilgungsanteil von `320,00 €` und nur noch `100,00 €` Restschuld werden genau `100,00 €` vom Konto abgebucht und `100,00 €` getilgt. Ab diesem Termin beträgt der offene Kreditsaldo `0,00 €`; spätere Raten entfallen.

Ist für die verknüpfte Ausgabe ein Enddatum hinterlegt und verbleiben nach der letzten vorgesehenen Rate nur noch **0,01 € bis 2,99 €**, wird dieser Kleinbetrag automatisch der Schlussrate zugeschlagen. Bei einer geplanten Schlussrate von `84,64 €` und einer Restschuld von `84,66 €` werden deshalb `84,66 €` abgebucht und getilgt. Der Kredit endet bei `0,00 €`. Bei exakt `3,00 €` oder mehr sowie bei Zahlungsplänen ohne Enddatum erfolgt keine automatische Erhöhung.

### 8.1 Automatische Zins- und Tilgungsberechnung

Ist **Zins und Tilgung automatisch berechnen** aktiviert, ermittelt FinanzLab bei jeder Rate den Zinsanteil aus dem aktuellen offenen Saldo und dem Sollzinssatz. Der übrige Teil der Rate tilgt den Kredit. Bereits manuell erfasste Zins- oder Tilgungswerte bleiben beim Bearbeiten unverändert.

Bei Konsumkrediten wird der **Produktpreis** als verzinslicher Anfangssaldo verwendet. **Finanzierungspreis** und **Ratenaufpreis** sind Gesamt- und Kontrollwerte und werden nicht nochmals verzinst. FinanzLab vergleicht Monatsrate mal Zahlungsanzahl zuzüglich einer möglichen Schlussrate mit dem Finanzierungspreis. Übliche Abweichungen von wenigen Cent durch gerundete Monatsraten werden akzeptiert.

Beispiel für eine PayPal-Ratenzahlung:

- Produktpreis: `519,99 €`
- Finanzierungspreis: `586,29 €`
- Ratenaufpreis: `66,01 €`
- 24 Raten zu `24,43 €`
- Sollzins: `11,8033 %`

Der verzinsliche Anfangssaldo beträgt `519,99 €`. Die 24 Raten werden gegen den Finanzierungspreis plausibilisiert; der Finanzierungspreis selbst erhält keinen zweiten Zinsaufschlag.

### 8.2 Manuelle Tilgung und Kreditaufstockung

Eine positive manuelle Tilgung verringert die Restschuld. Ein negativer Betrag wird als **Kreditaufstockung** behandelt und erhöht die Restschuld. Das ist bei Konsumkrediten, Krediten und geliehenen Beträgen möglich. Nachfolgende automatisch berechnete Zinsen verwenden den dadurch geänderten Saldo.

Bei einer Konsumfinanzierung reduziert eine Sondertilgung zusätzlich die noch verzinsliche Produktpreis-Restbasis. Ist dieses eigentliche Kapital vollständig getilgt, werden noch nicht entstandene künftige Finanzierungskosten nicht als offene Restschuld weitergeführt. Eine am selben Tag eingetragene manuelle Korrektur wird vor der Ablösezahlung verarbeitet. Spätere Raten bleiben zur Nachvollziehbarkeit sichtbar, sind jedoch als **„Entfällt – Kredit bereits getilgt“** gekennzeichnet und belasten das Konto nicht.

### 8.3 Archivierte Kredite

Ein vollständig getilgter Kredit wird automatisch archiviert. Ein Kredit kann außerdem im Bearbeitungsdialog manuell archiviert und später wieder aktiviert werden. Archivierte Kredite werden nicht in aktive Kreditsummen oder die Kreditsimulation der Vorschau aufgenommen.

### 8.4 Zinsauswertung

Auf der Seite **Zinsen** stehen oben vier Werte:

- **Kreditzinsen:** bis heute berechnete Zinsen der ausgewählten Kredite;
- **Geplante Kreditzinsen:** noch erwartete Zinsen der ausgewählten aktiven Kredite;
- **Zinsen Girokonto:** als Kontoausgaben erfasste Girokontozinsen;
- **Zinsen gesamt:** bisherige Kreditzinsen der Auswahl zuzüglich Girokontozinsen.

Unter **Einbezogene Kredite** lassen sich aktive und archivierte Kredite einzeln auswählen. Beim Öffnen eines Haushalts sind die aktiven Kredite vorausgewählt. Archivierte Kredite tragen den Zusatz **Archiv** und werden erst nach dem Setzen ihres Hakens angezeigt und eingerechnet. Die Auswahl beeinflusst **Zinsen je Kredit**, **Kreditzinsen**, **Geplante Kreditzinsen** und den Kreditanteil von **Zinsen gesamt**. Girokontozinsen bleiben davon unabhängig.

Bei automatisch archivierten Krediten kann so die abgeschlossene Zinshistorie erneut betrachtet werden. Bei manuell archivierten Krediten werden die bis zur Archivierung entstandenen Zinsen gezeigt; nach der Archivierung werden keine weiteren geplanten Zinsen hochgerechnet.

Über **+ Girokontozinsen** wird ein positiver Zinsbetrag mit Datum und Konto erfasst. FinanzLab legt ihn als Ausgabe an und zeigt ihn in der Zinsauswertung als positiven Kostenwert.

## 9. Umbuchungen

Umbuchungen bilden Bewegungen zwischen eigenen Konten ab, ohne dafür getrennte Einnahmen und Ausgaben anzulegen.

Bei einer Umbuchung wird:

- der Betrag vom Quellkonto abgezogen,
- derselbe Betrag dem Zielkonto gutgeschrieben,
- der Gesamtstand des Haushalts nicht verändert.

Angaben:

- Bezeichnung
- Von-Konto
- An-Konto
- Betrag
- erste Fälligkeit
- Rhythmus
- optionales Ende
- optionale Anzahl der Ausführungen

Für Umbuchungen stehen dieselben Rhythmen einschließlich **halbjährlich** zur Verfügung. Das Ende ist einschließlich. Wenn Ende und Anzahl gemeinsam gesetzt werden, müssen beide Angaben dieselbe letzte Ausführung beschreiben. Beispiel: Eine monatliche Umbuchung mit erster Fälligkeit am 15.08.2026 und 12 Ausführungen endet am 15.07.2027. Abweichende Kombinationen werden mit dem passenden Enddatum angezeigt und nicht gespeichert.

Auch die Umbuchungsliste ist in **Aktiv** und **Archiv** aufgeteilt. Wiederkehrende Umbuchungen ohne Ende oder mit einem Ende ab heute stehen unter **Aktiv**. Liegt das Ende vor dem heutigen Datum, wird die Umbuchung automatisch im **Archiv** angezeigt. Bei einer einmaligen Umbuchung wird stattdessen das Fälligkeitsdatum verwendet. Eine Änderung des Enddatums verschiebt eine wiederkehrende Umbuchung entsprechend wieder zurück.

## 10. Dashboard

Das Dashboard zeigt den berechneten Gesamtstand aller Konten zum gewählten Stichtag. Über die Pfeile kann tageweise vor- oder zurückgesprungen werden.

Links im oberen Dashboard-Bereich stehen die Schnellaktionen **Ausgabe hinzufügen** und **Einnahme hinzufügen** bereit. Beide öffnen denselben Eingabedialog wie die jeweilige Verwaltungsseite. Gespeicherte Positionen erscheinen deshalb unmittelbar unter **Ausgaben** beziehungsweise **Einnahmen** und werden zugleich in Dashboard und Vorschau berücksichtigt.

Zusätzlich werden angezeigt:

- im Monat des gewählten Stichtags tatsächlich fällige Einnahmen
- im Monat des gewählten Stichtags tatsächlich fällige Ausgaben
- Differenz aus Einnahmen und Ausgaben
- Anzahl der Konten
- Verteilung der Positionen
- Kontostände und Dispowarnungen
- Anzahl und offener Gesamtsaldo getrennt nach Konsumkredit, Kredit und Geliehen

Wird auf dem Dashboard ein zukünftiger Stichtag gewählt, werden auch die Kreditsalden bis zu diesem Tag simuliert. Verknüpfte Tilgungsanteile und manuelle Tilgungen mit einem Datum bis einschließlich des Stichtags reduzieren dann den angezeigten Kreditsaldo. Noch spätere Zahlungen bleiben unberücksichtigt. Auf der eigentlichen Kreditseite bleibt ohne Zukunftssimulation weiterhin der heutige reale Saldo maßgeblich.

Vierteljährliche, halbjährliche und jährliche Positionen werden dabei mit ihrem vollständigen Betrag ausschließlich im tatsächlichen Fälligkeitsmonat berücksichtigt. Sie werden nicht rechnerisch auf andere Monate verteilt. Start, Ende, Versionszeitraum und Aktivstatus werden ausgewertet. Für die vollständige Auflistung der einzelnen Fälligkeiten ist die Seite **Vorschau** maßgeblich.

Die monatliche Aufteilung zeigt alle in diesem Monat fälligen Einnahmen und Ausgaben, absteigend nach Betrag sortiert. Die Liste wird nicht auf eine feste Anzahl von Positionen gekürzt. Dadurch stimmen die sichtbaren Positionen jederzeit mit den angezeigten Monatssummen überein.

## 11. Vorschau

Die Vorschau simuliert einen vollständigen Monat.

- Mit den Pfeilen wird monatsweise navigiert.
- **+2** springt zwei Monate vor.
- Die Kontenauswahl bestimmt, welche Konten angezeigt werden.
- Kredite können getrennt von den Konten ausgewählt werden.
- Jeder Tag enthält die simulierten Kontostände der gewählten Konten.
- Ein Klick auf einen Tag öffnet die dazugehörigen Bewegungen.
- Jede geplante Bewegung besitzt die Checkbox **Vorgang erledigt**.
- Dispoüberschreitungen werden am jeweiligen Tag hervorgehoben.

Anfangsstand, Einnahmen, Ausgaben und Monatsendstand basieren auf den tatsächlich in diesem Monat fälligen Positionen. Ausgewählte Kredite erscheinen mit Anfangssaldo, Tilgungen und Endsaldo in einem separaten Bereich. Kreditsalden werden niemals zur Kontensumme addiert oder von ihr abgezogen; nur die zugehörige Ausgabe beeinflusst das Bankkonto.

Wird **Vorgang erledigt** aktiviert, bleibt die konkrete Fälligkeit am betreffenden Tag sichtbar und wird als erledigt markiert. Sie wird danach nicht mehr in den simulierten Kontostand, die Tagesänderung oder die Monatssummen eingerechnet. Der Status wird dauerhaft gespeichert. Wird der Haken wieder entfernt, fließt die Bewegung erneut in alle Vorschauwerte ein. Bei einer Umbuchung gilt der Status immer gemeinsam für Abgang und Eingang, auch wenn nur eines der beteiligten Konten angezeigt wird.

## 12. Excel-Export

Der Excel-Export befindet sich unter **Einstellungen**.

1. **Excel erstellen** wählen.
2. Startmonat festlegen.
3. Endmonat festlegen.
4. **Excel herunterladen** wählen.

Der Vorschauzeitraum darf höchstens 24 Monate umfassen.

Die Arbeitsmappe enthält:

| Tabellenblatt | Inhalt |
| --- | --- |
| Übersicht | Zeitraum, Bestandszahlen und Prognosesummen |
| Monatsvorschau | Anfang, Einnahmen, Ausgaben, Veränderung und Ende pro Monat |
| Kontovorschau | Monatswerte und niedrigster Stand je Konto |
| Tagesvorschau | Simulierter Kontostand für jeden Tag und jedes Konto |
| Bewegungen | Alle im Zeitraum fälligen Einnahmen, Ausgaben und Umbuchungen einschließlich Erledigt-Status |
| Konten | Kontostände, Disporahmen und Endprognose |
| Einnahmen | Alle eingegebenen Einnahmen |
| Ausgaben | Alle eingegebenen Ausgaben einschließlich Enddatum und Dauer |
| Umbuchungen | Alle Umbuchungen einschließlich Ende und Anzahl |
| Kontostand-Historie | Alle gespeicherten Kontostände |
| Kredite | Kreditart, Anfangssaldo, bisherige Tilgung und offener Saldo |
| Kreditzahlungen | Vollständige manuelle und automatische Tilgungshistorie |
| Kreditvorschau | Monatlich separat simulierte Kreditstände |

Alle eingegebenen Einnahmen, Ausgaben und Kredite werden unabhängig vom gewählten Vorschauzeitraum exportiert. Das umfasst auch deaktivierte, zukünftige und beendete Positionen. In den Vorschaublättern erscheinen dagegen nur Bewegungen, die nach den gespeicherten Regeln tatsächlich berücksichtigt werden dürfen.

Die Arbeitsblätter besitzen Filter, fixierte Kopfzeilen sowie formatierte Datums- und Geldzellen. Dispoüberschreitungen werden farblich hervorgehoben.

## 13. EnergyLab-Verbindung

FinanzLab kann die in EnergyLab gepflegten Strom-, Gas-, Wasser- und Abwasserverträge automatisch als geplante Ausgaben übernehmen. Dabei werden ausschließlich die tatsächlich geplanten Zahlungen synchronisiert.

Nicht als FinanzLab-Ausgaben übernommen werden:

- Verbrauchskosten,
- Grundgebühr,
- hochgerechnete Kosten,
- Guthaben, Erstattung oder Nachzahlung,
- Zählerstände und Verbrauchswerte.

Diese Werte bleiben Bestandteil der Energieberechnung in EnergyLab. Dadurch wird der Energievertrag in FinanzLab nicht doppelt belastet.

### 13.1 Verbindung einrichten

1. In EnergyLab beim jeweiligen Vertrag unter **Zahlung** Zahlungsrhythmus, Zahlungstag, optional **Erste Zahlung** und den Namen des FinanzLab-Kontos hinterlegen.
2. In FinanzLab **Einstellungen → EnergyLab verbinden** öffnen.
3. Die EnergyLab-Adresse eintragen, beispielsweise `http://<SERVER-IP>:8090`.
4. Ein **Konto für die Abschläge** als Rückfallkonto auswählen.
5. Die automatische Synchronisation aktivieren.
6. **Verbindung speichern** wählen.
7. Mit **Jetzt synchronisieren** den ersten Lauf sofort ausführen.

`http://energylab:8090` funktioniert, wenn beide Container in einem gemeinsamen Docker-Netzwerk liegen und der EnergyLab-Container dort `energylab` heißt. Bei getrennten Portainer-Stacks wird gewöhnlich die IP-Adresse des Docker-Hosts mit dem veröffentlichten EnergyLab-Port verwendet. `localhost` ist für einen anderen Container nicht geeignet.

Der Status unter den Schaltflächen zeigt, wie viele Verträge geprüft, neu angelegt oder aktualisiert wurden. Bei aktivierter Verbindung erfolgt ein Abgleich direkt nach dem Start von FinanzLab und anschließend standardmäßig alle sechs Stunden.

### 13.2 Welche Daten übernommen werden

Für jeden Strom-, Gas-, Wasser- und Abwasservertrag entsteht eine mit **EnergyLab** gekennzeichnete Ausgabe. Übernommen werden:

- Energieart und Anbieter,
- Vertragsbeginn und Vertragsende,
- Betrag je Zahlung,
- Zahlungsrhythmus (monatlich, quartalsweise, halbjährlich oder jährlich),
- optionales Datum der ersten Zahlung als Rhythmusanker,
- jede spätere Abschlagsänderung mit ihrem Gültigkeitsbeginn,
- Zahlungstag,
- Kontoname.

Vertragswechsel bleiben getrennte Positionen mit ihren jeweiligen Laufzeiten. Ändert sich beispielsweise der Abschlag ab Juli, bleiben die Fälligkeiten bis Juni mit dem alten Betrag erhalten; ab Juli wird der neue Betrag verwendet. Vergangene Zeiträume werden bei einer erneuten Synchronisation nicht mit dem aktuellen Betrag überschrieben.

Ein Zahlungstag von 29, 30 oder 31 wird in einem kürzeren Monat automatisch auf dessen letzten Kalendertag gesetzt. Beginnt ein Vertrag erst nach dem vorgesehenen Zahlungstag, liegt die erste Zahlung im folgenden passenden Monat. Ist in EnergyLab eine erste Zahlung eingetragen, beginnt der Rhythmus exakt mit diesem Datum.

### 13.3 Konto und Zahlungstag korrigieren

Stimmt der in EnergyLab hinterlegte Kontoname exakt mit einem FinanzLab-Konto überein, wird dieses Konto automatisch verwendet; Groß- und Kleinschreibung sind unerheblich. Andernfalls verwendet FinanzLab das in den Verbindungseinstellungen gewählte Rückfallkonto und zeigt nach der Synchronisation einen Hinweis. Zahlungsrhythmus und ein ausdrücklich gesetztes Datum **Erste Zahlung** bestimmen gemeinsam die tatsächlichen Fälligkeiten.

Unter **Ausgaben** besitzt jede synchronisierte Position die Schaltfläche **Konto & Zahlungstag**. Dort können Konto und Buchungstag für diesen Vertrag korrigiert werden. Die Änderung wird unmittelbar auf alle historischen und zukünftigen Versionen der Position angewendet.

Beim nächsten Abgleich bleibt das manuell gewählte Konto erhalten, wenn EnergyLab keinen passenden Kontonamen liefert. Enthält der EnergyLab-Vertrag einen passenden Kontonamen, ist diese Angabe maßgeblich. Entsprechend bleibt ein manuell gewählter Zahlungstag erhalten, solange EnergyLab keinen gültigen Zahlungstag zwischen 1 und 31 liefert. Damit können Konto und Zahlungstag dauerhaft zentral in EnergyLab gepflegt oder ersatzweise in FinanzLab korrigiert werden.

Abschlagsbetrag, Laufzeit und Anbieter werden weiterhin in EnergyLab gepflegt. Eine synchronisierte Position kann deshalb in FinanzLab nicht über den normalen Ausgabendialog geändert oder gelöscht werden.

### 13.4 Bestehende manuelle Abschläge

Vor der Verbindung bereits manuell angelegte Energieausgaben bleiben unverändert erhalten. FinanzLab löscht oder verbindet sie nicht automatisch, weil eine sichere Zuordnung ohne gemeinsame Vertragskennung nicht möglich ist.

Nach der ersten Synchronisation:

1. Betrag, Laufzeit, Konto und Zahlungstag der neuen EnergyLab-Position kontrollieren.
2. In der Monatsvorschau prüfen, ob der Abschlag doppelt erscheint.
3. Die bisherige manuelle Ausgabe gegebenenfalls deaktivieren, beenden oder löschen.
4. Die mit **EnergyLab** gekennzeichnete Position beibehalten.

Spätere Synchronisationen erkennen bereits übernommene Verträge und erzeugen keine weiteren Duplikate. Verträge, die EnergyLab nicht mehr liefert, werden in FinanzLab deaktiviert; abgeschlossene Vertragszeiträume bleiben historisch erhalten.

## 14. Datenprüfung

Unter **Einstellungen** zeigt die Datenprüfung Einnahmen und Ausgaben, die nicht oder nicht vollständig berücksichtigt werden können.

Typische Hinweise:

- kein Konto zugeordnet
- ungültige Fälligkeit
- Betrag ist `0,00 €`
- Position ist deaktiviert
- zugeordnete Person oder Konto existiert nicht mehr

Über **Bearbeiten** kann die betroffene Position direkt geöffnet werden.

## 15. Datensicherung

Alle Anwendungsdaten liegen im konfigurierten Docker-Volume unter `/data`. Die zentrale Datei ist:

```text
/data/planner.db
```

### 15.1 Integrierte Sicherungen

Unter **Einstellungen → Sicherungen** stehen die von FinanzLab verwalteten Datenbanksicherungen. Mit **Jetzt sichern** wird eine konsistente SQLite-Kopie der laufenden Datenbank erstellt. Der Container muss dafür nicht angehalten werden.

FinanzLab erstellt außerdem automatisch:

- einmalig vor der ersten Datenbankmigration einer neuen Anwendungsversion eine Sicherung, sofern bereits eine Datenbank vorhanden ist;
- vor jeder Wiederherstellung eine zusätzliche Sicherheitssicherung des aktuellen Zustands.

Die Liste zeigt Dateiname, Grund, Zeitpunkt, Größe und gegebenenfalls den Zeitpunkt einer Wiederherstellung. **Wiederherstellen** ersetzt den aktuellen Datenbankinhalt durch die ausgewählte Sicherung. Vorher verlangt die Oberfläche eine Bestätigung.

Vor der Wiederherstellung prüft FinanzLab:

- ob die Sicherungsdatei vorhanden ist,
- ob ihre SHA-256-Prüfsumme noch stimmt,
- ob die SQLite-Integritätsprüfung erfolgreich ist,
- ob die für FinanzLab erforderlichen Kerntabellen vorhanden sind.

Die Sicherungsdateien liegen unter `/data/backups` und damit im selben Docker-Volume wie die aktive Datenbank. Es gibt keine automatische Löschung alter Sicherungen. Der verfügbare Speicher sollte deshalb regelmäßig kontrolliert werden.

> Die integrierten Sicherungen helfen bei Bedienfehlern und fehlgeschlagenen Änderungen. Sie schützen nicht vor Verlust oder Beschädigung des gesamten Docker-Volumes. Deshalb zusätzlich regelmäßig ein externes Volume-Backup anlegen.

### 15.2 Externes Volume-Backup

Für eine konsistente externe Sicherung sollte der Container vor dem Kopieren des gesamten Volumes gestoppt werden.

Beispiel mit Docker Compose:

```bash
docker compose stop haushaltsplaner
```

Danach das gesamte Volume einschließlich `planner.db` und `backups` mit der vorhandenen Backup-Lösung sichern und den Dienst wieder starten:

```bash
docker compose start haushaltsplaner
```

Das GitHub-Repository und die Release-Pakete enthalten keine persönlichen Haushaltsdaten.

## 16. Aktualisierung

Vor einer Aktualisierung wird eine Sicherung der Datenbank empfohlen.

Bei einer Installation aus dem Repository:

```bash
git pull
docker compose up --build -d
```

Die Anwendung führt notwendige Schemaanpassungen beim Start aus. Das persistente Daten-Volume darf beim Update nicht gelöscht werden.

Bei Portainer wird das neue Image zuerst unter **Images → Import** eingespielt. Anschließend im bestehenden Stack die Zeile `image: finanzlab:2.1.1` setzen und den Stack neu bereitstellen. Der bestehende Stackname und das Volume müssen erhalten bleiben. Eine ausführliche Schrittfolge einschließlich Sicherung und Wiederherstellung steht in [INSTALLATION.md](INSTALLATION.md#11-aktualisieren-auf-eine-neue-version).

## 17. Fehlerbehebung

### Anwendung ist nicht erreichbar

```bash
docker compose ps
docker compose logs --tail=200 haushaltsplaner
```

Prüfen, ob Port `8798` bereits von einem anderen Dienst verwendet wird.

### Kontostand wirkt doppelt verändert

Beim letzten gespeicherten Kontostand prüfen, ob die Checkbox für bereits enthaltene Tagesbuchungen korrekt gesetzt ist.

### Eine Zahlung fehlt in der Vorschau

Prüfen:

1. Ist **In Berechnungen berücksichtigen** aktiviert?
2. Ist ein Konto zugeordnet?
3. Liegt die Fälligkeit im betrachteten Zeitraum?
4. Ist ein Enddatum bereits überschritten?
5. Enthält der gespeicherte Kontostand die Tagesbuchungen bereits?
6. Gibt es unter **Einstellungen → Datenprüfung** einen Hinweis?

### Excel-Export schlägt fehl

- Start- und Endmonat müssen gültig sein.
- Der Startmonat darf nicht nach dem Endmonat liegen.
- Der Zeitraum darf höchstens 24 Monate umfassen.
- Bei sehr großen Datenbeständen kann die Erstellung einige Sekunden dauern.

### EnergyLab ist nicht erreichbar

- prüfen, ob die eingetragene Adresse aus dem FinanzLab-Container erreichbar ist;
- bei getrennten Containern nicht `localhost` verwenden;
- Server-IP, Port `8090`, Docker-Netzwerk und Firewall kontrollieren;
- sicherstellen, dass EnergyLab unter `/api/personallab` Daten bereitstellt.

### EnergyLab-Abschlag verwendet das falsche Konto oder Datum

Unter **Ausgaben** bei der betreffenden, mit **EnergyLab** gekennzeichneten Position **Konto & Zahlungstag** öffnen. Die Korrektur bleibt beim nächsten Abgleich erhalten, wenn EnergyLab für das jeweilige Feld keinen eigenen gültigen Wert liefert. Für eine dauerhaft zentrale Vorgabe Kontoname und Zahlungstag direkt im EnergyLab-Vertrag anpassen.

### EnergyLab-Abschlag erscheint doppelt

Prüfen, ob zusätzlich noch eine ältere, manuell angelegte Energieausgabe aktiv ist. Diese nach der Kontrolle deaktivieren, beenden oder löschen. Die automatisch verwaltete Position ist am **EnergyLab**-Hinweis erkennbar.

## 18. Datenschutz und Funktionsumfang

Die Anwendung arbeitet lokal und benötigt keine Online-Banking- oder Cloud-Schnittstelle. Die optionale EnergyLab-Verbindung kommuniziert ausschließlich mit der vom Benutzer eingetragenen Adresse. Es gibt in dieser Version keinen Excel-, CSV-, PDF- oder Bankimport; der Excel-Export ist davon unabhängig verfügbar.

Nicht enthalten sind insbesondere:

- Online-Banking-Zugänge
- automatische Bankabfragen
- automatische Dispozinsberechnungen
- Cloud-Synchronisierung persönlicher Haushaltsdaten

## 19. Autor und Unterstützung

Entwickelt von **Lrd.Tiberius**.

Der Link **Buy me a coffee** ist im Fußbereich der Anwendung erreichbar.
