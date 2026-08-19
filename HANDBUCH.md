# Handbuch zum Haushaltsplaner

Gültig für Version **0.12.3**

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

Für eine Portainer-Installation kann entweder das Repository als Git-Stack verwendet oder das bereitgestellte Portainer-Paket des Releases genutzt werden.

Beim Portainer-Paket:

1. die enthaltene Build-TAR als Image importieren,
2. sicherstellen, dass das externe Volume `finanzlab` vorhanden ist,
3. die enthaltene Stack-YAML in Portainer anlegen,
4. den Stack starten,
5. Port `8798` im Browser öffnen.

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
| Einnahmen | Alle regelmäßigen und einmaligen Einnahmen |
| Ausgaben | Alle Ausgaben, optional mit einem Kredit und Tilgungsanteil verknüpft |
| Kredite | Kreditstammdaten, offene Salden und vollständige Tilgungshistorie |
| Umbuchungen | Geldbewegungen zwischen eigenen Konten |
| Einstellungen | Haushalte, Personen, Datenprüfung und Excel-Export |

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

Zins- und Dispozinsberechnungen sind nicht Bestandteil der Anwendung.

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

## 7. Ausgaben

Unter **Ausgaben** werden regelmäßige und einmalige Zahlungen verwaltet. Für Kreditraten stehen die Arten **Konsumkredit**, **Kredit** und **Geliehen** zur Verfügung. Nach der Auswahl muss ein Kredit derselben Art zugeordnet werden.

Erforderliche Angaben entsprechen grundsätzlich den Einnahmen. Zusätzlich können Ausgaben zeitlich begrenzt werden.

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

Im Kopf der Ausgabenkarte steht der negative Saldo aller angelegten Ausgabenpositionen. Deaktivierte Positionen werden in diesem Bestandssaldo mitgezählt, aber nicht in Vorschauen eingerechnet.

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

Beim Anlegen werden Bezeichnung, Art, Anfangssaldo und optional eine Notiz gespeichert. Ein Klick auf den Kredit öffnet den aktuellen Saldo und die vollständige Zahlungshistorie.

Die Historie enthält:

- automatisch erzeugte Tilgungen aus verknüpften Ausgaben,
- manuell erfasste Tilgungen,
- Datum, Betrag, Bezeichnung und Quelle jeder Tilgung,
- geplante zukünftige Tilgungen in grauer Darstellung.

Zukünftige Tilgungen reduzieren den aktuellen Kreditsaldo nicht. Sie werden erst am eingetragenen Datum saldowirksam. Manuelle Tilgungen können aus der Historie wieder gelöscht werden; automatisch erzeugte Einträge werden über die zugehörige Ausgabe geändert.

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

## 10. Dashboard

Das Dashboard zeigt den berechneten Gesamtstand aller Konten zum gewählten Stichtag. Über die Pfeile kann tageweise vor- oder zurückgesprungen werden.

Zusätzlich werden angezeigt:

- monatliche Einnahmepositionen
- monatliche Ausgabenpositionen
- Differenz aus Einnahmen und Ausgaben
- Anzahl der Konten
- Verteilung der Positionen
- Kontostände und Dispowarnungen
- Anzahl und offener Gesamtsaldo getrennt nach Konsumkredit, Kredit und Geliehen

Für eine vollständige Auflistung der tatsächlich fälligen Bewegungen eines Monats ist die Seite **Vorschau** maßgeblich.

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

## 13. Datenprüfung

Unter **Einstellungen** zeigt die Datenprüfung Einnahmen und Ausgaben, die nicht oder nicht vollständig berücksichtigt werden können.

Typische Hinweise:

- kein Konto zugeordnet
- ungültige Fälligkeit
- Betrag ist `0,00 €`
- Position ist deaktiviert
- zugeordnete Person oder Konto existiert nicht mehr

Über **Bearbeiten** kann die betroffene Position direkt geöffnet werden.

## 14. Datensicherung

Alle Anwendungsdaten liegen im konfigurierten Docker-Volume unter `/data`. Die zentrale Datei ist:

```text
/data/planner.db
```

Für eine konsistente Sicherung sollte der Container vor dem Kopieren der Datenbank gestoppt werden.

Beispiel mit Docker Compose:

```bash
docker compose stop haushaltsplaner
```

Danach das Volume beziehungsweise die Datei `planner.db` mit der vorhandenen Backup-Lösung sichern und den Dienst wieder starten:

```bash
docker compose start haushaltsplaner
```

Das GitHub-Repository und die Release-Pakete enthalten keine persönlichen Haushaltsdaten.

## 15. Aktualisierung

Vor einer Aktualisierung wird eine Sicherung der Datenbank empfohlen.

Bei einer Installation aus dem Repository:

```bash
git pull
docker compose up --build -d
```

Die Anwendung führt notwendige Schemaanpassungen beim Start aus. Das persistente Daten-Volume darf beim Update nicht gelöscht werden.

## 16. Fehlerbehebung

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

## 17. Datenschutz und Funktionsumfang

Die Anwendung arbeitet lokal und benötigt für die Haushaltsplanung keine externe Finanzschnittstelle. Es gibt in dieser Version keinen Excel-, CSV-, PDF- oder Bankimport.

Nicht enthalten sind insbesondere:

- Online-Banking-Zugänge
- automatische Bankabfragen
- Zins- oder Dispozinsberechnungen
- Cloud-Synchronisierung persönlicher Haushaltsdaten

## 18. Autor und Unterstützung

Entwickelt von **Lrd.Tiberius**.

Der Link **Buy me a coffee** ist im Fußbereich der Anwendung erreichbar.
