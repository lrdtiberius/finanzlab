# Installation und Ersteinrichtung

Diese Anleitung beschreibt die vollständige Installation und Ersteinrichtung des **Haushaltsplaners / FinanzLab**.

Gültig für Version **0.13.5**.

Die Anwendung ist für den lokalen Betrieb vorgesehen und speichert ihre Daten ausschließlich lokal in einer SQLite-Datenbank im Docker-Volume beziehungsweise unter dem konfigurierten `DATA_DIR`.

## Inhaltsverzeichnis

- [1. Welche Installationsart soll ich verwenden?](#1-welche-installationsart-soll-ich-verwenden)
- [2. Voraussetzungen](#2-voraussetzungen)
- [3. Daten und Persistenz](#3-daten-und-persistenz)
- [4. Installation mit Docker Compose](#4-installation-mit-docker-compose)
- [5. Installation mit Portainer](#5-installation-mit-portainer)
- [6. Standalone-Image selbst bauen](#6-standalone-image-selbst-bauen)
- [7. Erster Start und Grundeinrichtung](#7-erster-start-und-grundeinrichtung)
- [8. Empfohlene Reihenfolge der Einrichtung](#8-empfohlene-reihenfolge-der-einrichtung)
- [9. Port und Netzwerk anpassen](#9-port-und-netzwerk-anpassen)
- [10. Installation prüfen](#10-installation-prüfen)
- [11. Aktualisieren auf eine neue Version](#11-aktualisieren-auf-eine-neue-version)
- [12. Datensicherung und Wiederherstellung](#12-datensicherung-und-wiederherstellung)
- [13. Fehlerbehebung](#13-fehlerbehebung)
- [14. Deinstallation](#14-deinstallation)
- [15. Sicherheitshinweise](#15-sicherheitshinweise)
- [16. Kurzcheck nach der Einrichtung](#16-kurzcheck-nach-der-einrichtung)

---

## 1. Welche Installationsart soll ich verwenden?

Es gibt mehrere Möglichkeiten, den Haushaltsplaner zu betreiben.

### Docker Compose

Empfohlen, wenn Docker direkt über die Kommandozeile verwaltet wird.

Vorteile:

- einfachster Weg für Installation und Updates,
- Dockerfile, Port, Volume und Healthcheck sind bereits vorbereitet,
- der aktuelle Quellstand kann direkt neu gebaut werden.

### Portainer mit fertigem Docker-Image

Empfohlen, wenn Container hauptsächlich über Portainer verwaltet werden.

Vorteile:

- kein eigener Build notwendig,
- das Image kann direkt aus einem GitHub-Release importiert werden,
- anschließend wird nur noch ein Stack beziehungsweise Container auf dieses Image gesetzt.

Das von GitHub erzeugte Release-Image ist für **linux/amd64** vorgesehen.

### Portainer mit eigenem Standalone-Build

Geeignet, wenn das Image direkt auf dem eigenen Docker-Host gebaut werden soll.

Wichtig: Der offizielle Dockerfile ist eine **Standalone-Variante**. Er beginnt mit `python:3.13-slim` und benötigt **kein vorhandenes älteres FinanzLab-Image**.

Ein Build darf deshalb nicht auf Konstruktionen wie

```dockerfile
FROM finanzlab:0.13.4
```

angewiesen sein. Ein altes Image darf für die Installation einer neuen Version vollständig entbehrlich sein.

---

## 2. Voraussetzungen

Für den Docker-Betrieb werden benötigt:

- Docker Engine,
- Docker Compose Plugin für die Compose-Variante,
- ausreichend freier Speicher für Image und Datenbank,
- standardmäßig ein freier TCP-Port `8798`.

Für das vorgefertigte Release-Image wird ein **linux/amd64**-Docker-Host benötigt.

Wird das Image selbst aus dem Repository gebaut, übernimmt Docker die Plattform des verwendeten Basisimages. Dadurch ist ein lokaler Build auch die bevorzugte Variante, wenn kein amd64-System verwendet wird.

### Netzwerk

Standardmäßig wird die Anwendung auf Port `8798` veröffentlicht.

Auf dem Docker-Rechner:

```text
http://localhost:8798
```

Von einem anderen Gerät im gleichen Netzwerk:

```text
http://<SERVER-IP>:8798
```

Beispiel:

```text
http://192.168.1.50:8798
```

---

## 3. Daten und Persistenz

Die Anwendung speichert ihre Nutzdaten unter:

```text
/data
```

Die zentrale Datenbankdatei lautet:

```text
/data/planner.db
```

Die mitgelieferte `compose.yaml` verwendet dafür das benannte Docker-Volume:

```text
finanzlab_data
```

Dadurch bleiben die Daten erhalten, wenn der Container neu erstellt oder das Docker-Image ersetzt wird.

### Wichtig

Ein normales

```bash
docker compose down
```

löscht die gespeicherten Finanzdaten **nicht**.

Der Befehl

```bash
docker compose down -v
```

löscht dagegen zusätzlich das zugehörige Volume. Er sollte nur verwendet werden, wenn die gespeicherten Daten wirklich entfernt werden sollen.

---

## 4. Installation mit Docker Compose

### 4.1 Repository laden

```bash
git clone https://github.com/lrdtiberius/finanzlab.git
cd finanzlab
```

### 4.2 Anwendung bauen und starten

```bash
docker compose up --build -d
```

Docker baut dabei das Image aus dem Dockerfile des Repositorys und startet anschließend den Container.

### 4.3 Status prüfen

```bash
docker compose ps
```

Nach erfolgreichem Start sollte der Dienst `haushaltsplaner` beziehungsweise der Container `finanzlab` laufen.

### 4.4 Protokoll anzeigen

```bash
docker compose logs -f haushaltsplaner
```

Beenden mit `Ctrl+C` beendet nur die Loganzeige, nicht den Container.

### 4.5 Anwendung öffnen

```text
http://<SERVER-IP>:8798
```

### 4.6 Anwendung stoppen

```bash
docker compose down
```

Die Daten im Volume `finanzlab_data` bleiben erhalten.

### Alternative: Installationsskript

Im Repository befindet sich zusätzlich `install.sh`.

```bash
chmod +x install.sh
./install.sh
```

Das Skript führt den Docker-Build aus und startet die Anwendung anschließend im Hintergrund.

---

## 5. Installation mit Portainer

Es gibt zwei sinnvolle Portainer-Wege: ein fertiges Release-Image importieren oder das Image vollständig selbst bauen.

### 5.1 Variante A: fertiges Release-Image importieren

GitHub-Releases enthalten ein bereits gebautes Docker-Image im Format:

```text
finanzlab-image-v<VERSION>-amd64.tar.gz
```

Beispiel:

```text
finanzlab-image-v0.13.5-amd64.tar.gz
```

Dieses Image wurde mit `docker save` erzeugt und anschließend komprimiert.

#### Schritt 1: Release-Datei herunterladen

Auf der GitHub-Seite [Releases](https://github.com/lrdtiberius/finanzlab/releases/latest) den gewünschten Release öffnen und das Docker-Image herunterladen.

Für Version 0.13.5 werden für die Portainer-Installation diese Dateien angeboten:

```text
finanzlab-image-v0.13.5-amd64.tar.gz
finanzlab-image-v0.13.5-amd64.tar.gz.sha256
```

Die Datei `finanzlab-v0.13.5.tar.gz` enthält dagegen den Quellcode und ist **kein importierbares Docker-Image**.

Optional kann die Prüfsumme vor dem Import kontrolliert werden:

```bash
# Linux
sha256sum finanzlab-image-v0.13.5-amd64.tar.gz

# macOS
shasum -a 256 finanzlab-image-v0.13.5-amd64.tar.gz
```

Der ausgegebene Wert muss mit dem Wert in der heruntergeladenen `.sha256`-Datei übereinstimmen.

#### Schritt 2: bei Bedarf entpacken

Einige Portainer-Versionen akzeptieren die komprimierte `.tar.gz`-Datei direkt. Falls der Import fehlschlägt, die Datei vorher zu einer normalen `.tar` entpacken.

Linux/macOS:

```bash
gunzip finanzlab-image-v0.13.5-amd64.tar.gz
```

Danach liegt vor:

```text
finanzlab-image-v0.13.5-amd64.tar
```

#### Schritt 3: Image in Portainer importieren

In Portainer:

1. **Images** öffnen.
2. **Import** wählen.
3. die Image-TAR auswählen.
4. Import starten.
5. anschließend kontrollieren, ob `finanzlab:0.13.5` in der Image-Liste vorhanden ist.

> **Nicht verwechseln:** Ein Docker-Image-TAR gehört zu **Images → Import**. Ein Quell-/Build-TAR mit Dockerfile gehört dagegen zu **Images → Build image → Upload**.

Die Seite **Build a new image** darf für `finanzlab-image-v0.13.5-amd64.tar` nicht verwendet werden. Dort sucht Portainer nach einem Dockerfile und meldet deshalb bei einer Image-TAR `Cannot locate Dockerfile`.

### 5.2 Portainer-Stack für ein bereits vorhandenes Image

Nachdem das Image `finanzlab:0.13.5` vorhanden ist, kann die fertige Datei **[`portainer-stack.yaml`](portainer-stack.yaml)** verwendet werden. Sie enthält folgenden Stack:

```yaml
services:
  haushaltsplaner:
    image: finanzlab:0.13.5
    container_name: finanzlab
    ports:
      - "8798:8798"
    environment:
      DATA_DIR: /data
      PORT: "8798"
    volumes:
      - finanzlab_data:/data
    init: true
    security_opt:
      - no-new-privileges:true
    healthcheck:
      test:
        - CMD
        - python
        - -c
        - "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8798/health', timeout=2)"
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s
    logging:
      driver: json-file
      options:
        max-size: 10m
        max-file: "3"
    restart: unless-stopped

volumes:
  finanzlab_data:
```

In Portainer:

1. **Stacks** öffnen.
2. **Add stack** wählen.
3. einen Namen vergeben, zum Beispiel `finanzlab`.
4. die YAML einfügen.
5. **Deploy the stack** ausführen.
6. anschließend unter **Containers** prüfen, ob `finanzlab` läuft und `healthy` wird.

Bei einer über einen Portainer Agent angebundenen Docker-Umgebung müssen Image und Stack in derselben Zielumgebung angelegt werden.

### 5.3 Variante B: Standalone-Image in Portainer bauen

Unter:

**Images → Build image → Upload**

muss ein vollständiger Docker-Build-Kontext hochgeladen werden.

Im Root dieses TAR-Archivs müssen mindestens enthalten sein:

```text
Dockerfile
requirements.txt
app/
```

Beim Build:

```text
Name: finanzlab:0.13.5
Dockerfile path: Dockerfile
```

Der Dockerfile des Projekts baut die Anwendung vollständig aus `python:3.13-slim`. Ein vorhandenes `finanzlab:0.13.4` oder anderes Vorgänger-Image ist nicht erforderlich.

Nach erfolgreichem Build kann derselbe Stack aus Abschnitt 5.2 verwendet werden.

---

## 6. Standalone-Image selbst bauen

Wer das Image ohne Docker Compose erzeugen möchte, kann direkt im geklonten Repository bauen.

```bash
docker build -t finanzlab:0.13.5 .
```

Danach kann ein Container manuell gestartet werden:

```bash
docker volume create finanzlab_data

docker run -d \
  --name finanzlab \
  --restart unless-stopped \
  -p 8798:8798 \
  -e DATA_DIR=/data \
  -e PORT=8798 \
  -v finanzlab_data:/data \
  finanzlab:0.13.5
```

Status prüfen:

```bash
docker ps
```

Logs anzeigen:

```bash
docker logs -f finanzlab
```

---

## 7. Erster Start und Grundeinrichtung

Beim ersten Aufruf erkennt die Anwendung, dass noch kein Haushalt vorhanden ist, und öffnet die Ersteinrichtung.

### 7.1 Haushalt anlegen

Folgende Angaben werden abgefragt:

1. **Name des Haushalts**
2. **Haushaltsmodell**
   - Einzelperson
   - Paar
3. **Name der Person A**
4. bei einem Paar zusätzlich **Name der Person B**

Die Namen dienen nur der internen Zuordnung von Konten, Einnahmen und Ausgaben.

### 7.2 Erstes Konto

Bereits während der Ersteinrichtung kann ein erstes Konto angelegt werden.

Empfohlen sind:

- eindeutiger Kontoname, zum Beispiel `Girokonto`,
- aktueller Kontostand,
- Datum, zu dem dieser Kontostand gilt,
- optional ein Disporahmen als positiver Betrag; `0` bedeutet kein hinterlegter Dispo.

### 7.3 Tagesbuchungen korrekt kennzeichnen

Beim Erfassen eines Kontostands gibt es die Option:

**„Zahlungen an diesem Tag sind im Kontostand bereits enthalten“**

Diese Einstellung ist für eine korrekte Prognose wichtig.

Beispiel:

Der Kontostand wurde abends aus dem Onlinebanking übernommen und alle Buchungen dieses Tages sind bereits darin enthalten. Dann sollte die Option aktiviert werden.

Wurde der Stand dagegen morgens vor den für diesen Tag erwarteten Buchungen übernommen, bleibt die Option deaktiviert.

So werden Einnahmen und Ausgaben am Tag des gespeicherten Kontostands nicht versehentlich doppelt berücksichtigt.

---

## 8. Empfohlene Reihenfolge der Einrichtung

Nach dem ersten Start empfiehlt sich folgende Reihenfolge.

### 8.1 Konten vollständig anlegen

Unter **Konten** alle verwendeten Konten erfassen.

Für jedes Konto können unter anderem eingestellt werden:

- Bezeichnung,
- Besitzer,
- aktueller beziehungsweise historischer Kontostand,
- Standardkonto,
- optionaler Disporahmen.

Das am häufigsten verwendete Girokonto sollte als Standardkonto markiert werden. Es wird dadurch beim Anlegen neuer Einnahmen und Ausgaben automatisch vorausgewählt.

### 8.2 Kontostände prüfen

Vor dem Anlegen vieler Zahlungspositionen sollten die gespeicherten Ausgangsstände kontrolliert werden.

Besonders wichtig:

- korrektes Datum,
- korrekter Betrag,
- richtige Einstellung für bereits enthaltene Tagesbuchungen.

### 8.3 Einnahmen anlegen

Typische Beispiele:

- Gehalt,
- Rente,
- Leistungen,
- sonstige regelmäßige Einnahmen.

Je Position werden insbesondere Betrag, Rhythmus, Fälligkeit und Konto festgelegt.

### 8.4 Ausgaben anlegen

Typische Beispiele:

- Wohnen,
- Energie,
- Versicherungen,
- Lebensmittel,
- Mobilität,
- Freizeit,
- Kreditraten.

Ausgaben können einmalig oder wiederkehrend angelegt werden. Für Ausgaben steht zusätzlich ein wöchentlicher Rhythmus zur Verfügung.

### 8.5 Kredite anlegen

Unter **Kredite** können drei Arten verwaltet werden:

- Konsumkredit,
- Kredit,
- Geliehen.

Nach dem Anlegen eines Kredits kann eine entsprechende Ausgabe mit diesem Kredit verknüpft werden. Dabei lassen sich Abbuchungsbetrag und tatsächlicher Tilgungsanteil getrennt behandeln.

Ein Kredit mit einem Saldo von `0,00 €` wird automatisch archiviert. Kredite können auch manuell archiviert werden. Archivierte Kredite werden aus der aktiven Berechnung und aus der Kreditauswahl der Vorschau entfernt.

### 8.6 Umbuchungen anlegen

Umbuchungen sind Bewegungen zwischen eigenen Konten.

Beispiel:

```text
Girokonto → Tagesgeld
```

Da eine Umbuchung den Gesamthaushalt nicht reicher oder ärmer macht, wird sie als Belastung des Quellkontos und Gutschrift des Zielkontos behandelt.

### 8.7 Vorschau kontrollieren

Unter **Vorschau** einen Monat öffnen und kontrollieren:

- stimmen die erwarteten Einnahmen?
- stimmen die erwarteten Ausgaben?
- erscheinen wiederkehrende Zahlungen an den richtigen Tagen?
- sind die richtigen Konten ausgewählt?
- werden nur aktive Kredite zur Kreditsimulation angeboten?
- stimmen die simulierten Kontostände?

Die Tagesansicht eignet sich besonders gut, um Fehler bei Fälligkeiten oder Kontozuordnungen zu erkennen.

### 8.8 Datenprüfung verwenden

Unter **Einstellungen** befindet sich die Datenprüfung.

Dort werden Positionen angezeigt, die beispielsweise wegen fehlender oder ungültiger Zuordnungen nicht vollständig berücksichtigt werden können.

Nach der Ersteinrichtung sollte die Datenprüfung möglichst keine offenen Fehler mehr anzeigen.

---

## 9. Port und Netzwerk anpassen

Der Standardport ist `8798`.

### Nur den externen Port ändern

Soll die Anwendung beispielsweise auf Port `8800` erreichbar sein, reicht bei Docker Compose:

```yaml
ports:
  - "8800:8798"
```

Die Anwendung ist danach erreichbar unter:

```text
http://<SERVER-IP>:8800
```

Der interne Container-Port bleibt in diesem Fall `8798`.

### Internen Port ebenfalls ändern

Wenn auch der interne Port geändert wird, müssen `PORT`, Port-Mapping und Healthcheck gemeinsam angepasst werden.

Für normale Installationen ist dies nicht notwendig.

---

## 10. Installation prüfen

### Health-Endpunkt

Die Anwendung stellt einen einfachen Health-Endpunkt bereit:

```text
http://<SERVER-IP>:8798/health
```

Eine funktionierende Installation liefert eine JSON-Antwort mit dem Status `ok`.

### Docker Compose

```bash
docker compose ps
```

### Docker direkt

```bash
docker ps --filter name=finanzlab
```

### Logs

Docker Compose:

```bash
docker compose logs --tail=100 haushaltsplaner
```

Docker direkt beziehungsweise Portainer-Container:

```bash
docker logs --tail=100 finanzlab
```

---

## 11. Aktualisieren auf eine neue Version

Vor einem Update ist eine Sicherung des Daten-Volumes empfehlenswert.

### 11.1 Docker Compose aus dem Git-Repository

Im Projektordner:

```bash
git pull
```

Danach das Image neu bauen und den Container ersetzen:

```bash
docker compose up --build -d
```

Das vorhandene Volume `finanzlab_data` wird erneut eingebunden. Die Nutzdaten bleiben erhalten.

### 11.2 Portainer mit neuem fertigem Image

1. neues Image importieren,
2. prüfen, ob das neue Tag vorhanden ist, zum Beispiel `finanzlab:0.13.6`,
3. den **bestehenden Stack unter demselben Namen** öffnen,
4. im Stack die `image:`-Zeile auf die neue Version ändern,
5. bei einem lokal importierten Image eine Portainer-Option zum erneuten Abrufen des Images nicht aktivieren,
6. Stack neu deployen,
7. prüfen, ob der neue Container korrekt läuft und `healthy` wird,
8. die Versionsanzeige im Fußbereich der Anwendung kontrollieren,
9. erst danach das alte, nicht mehr verwendete Image löschen.

Den Stack beim Update nicht unter einem neuen Namen anlegen und das vorhandene Daten-Volume nicht entfernen. So wird weiterhin dieselbe Datenbank unter `/data` eingebunden.

### Warum lässt sich ein altes Image manchmal nicht löschen?

Docker verhindert das Löschen eines Images, solange noch ein Container darauf basiert.

Deshalb immer zuerst:

1. neues Image bereitstellen,
2. Container oder Stack auf das neue Image umstellen,
3. neu deployen,
4. alten Container entfernen beziehungsweise ersetzen,
5. anschließend das alte Image löschen.

### Datenbankmigrationen

Notwendige Schemaerweiterungen werden von der Anwendung beim Start automatisch durchgeführt.

Das Docker-Volume sollte bei einem normalen Versionswechsel nicht gelöscht oder neu angelegt werden.

---

## 12. Datensicherung und Wiederherstellung

### 12.1 Backup des Docker-Volumes

Für eine konsistente Sicherung wird der Container zuerst gestoppt. Das folgende Beispiel übernimmt das tatsächlich am Container `finanzlab` eingebundene Volume. Dadurch funktioniert es auch, wenn Docker Compose oder Portainer dem Volume-Namen einen Projektpräfix vorangestellt hat.

```bash
docker stop finanzlab

docker run --rm \
  --volumes-from finanzlab \
  -v "$PWD":/backup \
  alpine \
  tar -czf /backup/finanzlab-backup.tar.gz -C /data .

docker start finanzlab
```

Die erzeugte Datei liegt anschließend im aktuellen Verzeichnis.

### 12.2 Backup kontrollieren

```bash
tar -tzf finanzlab-backup.tar.gz
```

Darin sollte unter anderem `planner.db` sichtbar sein.

### 12.3 Wiederherstellung

Vor einer Wiederherstellung die Anwendung stoppen:

```bash
docker stop finanzlab
```

Danach kann der gesicherte Inhalt wieder in genau das am Container eingebundene Volume geschrieben werden.

> Eine Wiederherstellung überschreibt den vorhandenen Datenbestand. Vorher sollte deshalb nach Möglichkeit zusätzlich eine Sicherung des aktuellen Zustands erstellt werden.

Beispiel:

```bash
docker run --rm \
  --volumes-from finanzlab \
  -v "$PWD":/backup \
  alpine \
  sh -c 'tar -xzf /backup/finanzlab-backup.tar.gz -C /data && chown -R 10001:10001 /data'
```

Anschließend wieder starten:

```bash
docker start finanzlab
```

---

## 13. Fehlerbehebung

### Portainer meldet „Cannot locate specified Dockerfile"

Das hochgeladene Archiv ist kein vollständiger Build-Kontext oder der Dockerfile liegt nicht an der eingestellten Position.

Bei

```text
Dockerfile path: Dockerfile
```

muss sich der Dockerfile direkt im Root des hochgeladenen TAR-Archivs befinden.

Ein reines Update-Archiv mit nur einzelnen geänderten Dateien reicht nicht zum Erstellen eines Standalone-Images.

### Portainer-Build meldet einen fehlenden Benutzer wie `appuser`

Ein solcher Fehler kann entstehen, wenn ein Update-Dockerfile auf einem bereits vorhandenen alten FinanzLab-Image basiert und anschließend Dateien mit `--chown=appuser:appuser` kopieren möchte, obwohl dieser Benutzer im Basisimage nicht vorhanden ist.

Der offizielle FinanzLab-Dockerfile vermeidet dieses Problem, weil er vollständig von `python:3.13-slim` aus baut und den benötigten Benutzer selbst anlegt.

Für normale Releases daher immer die Standalone-Variante verwenden.

### Altes Docker-Image kann nicht gelöscht werden

Mindestens ein Container verwendet das Image noch.

Prüfen:

```bash
docker ps -a --filter ancestor=finanzlab:0.13.4
```

Den Stack zuerst auf die neue Version umstellen und neu deployen. Danach kann das alte Image entfernt werden.

### Anwendung ist nicht erreichbar

Prüfen:

```bash
docker ps
```

Danach Logs kontrollieren:

```bash
docker logs finanzlab
```

Zusätzlich prüfen:

- ist der Container gestartet?
- ist Port `8798` korrekt veröffentlicht?
- wird der Port bereits von einem anderen Dienst benutzt?
- blockiert eine Firewall den Zugriff?
- wird die richtige IP-Adresse des Docker-Hosts verwendet?

### Container startet ständig neu

Logs anzeigen:

```bash
docker logs --tail=200 finanzlab
```

Außerdem kontrollieren, ob das Daten-Volume korrekt eingebunden ist und der Container auf `/data` schreiben kann.

### Nach dem Update sind scheinbar alte Dateien aktiv

Bei einem selbst gebauten Image sicherstellen, dass wirklich das neue Tag verwendet wird.

Beispiel:

```text
finanzlab:0.13.5
```

In Portainer anschließend den Stack ausdrücklich neu deployen. Nur das Erstellen eines neuen Images ersetzt keinen bereits laufenden Container automatisch.

### Nach dem Update sind die bisherigen Daten nicht sichtbar

Keine neuen Daten eingeben. Zuerst prüfen, ob der Stack versehentlich unter einem anderen Namen neu angelegt oder ein neues Volume eingebunden wurde. Das ursprüngliche Volume ist häufig weiterhin unter **Volumes** vorhanden und kann wieder unter `/data` eingebunden werden.

---

## 14. Deinstallation

### Container und Stack entfernen, Daten behalten

Docker Compose:

```bash
docker compose down
```

Das Volume bleibt erhalten.

### Anwendung einschließlich aller Daten löschen

```bash
docker compose down -v
```

Danach sind die Daten aus `finanzlab_data` gelöscht.

Optional kann das Image entfernt werden:

```bash
docker image rm finanzlab:0.13.5
```

### Portainer

1. Stack entfernen.
2. gewünschtes Image unter **Images** löschen.
3. nur wenn wirklich alle FinanzLab-Daten entfernt werden sollen: unter **Volumes** auch `finanzlab_data` löschen.

---

## 15. Sicherheitshinweise

FinanzLab ist für den privaten lokalen Betrieb gedacht.

Empfehlungen:

- Anwendung nicht ungeschützt direkt aus dem Internet erreichbar machen,
- Docker-Host und Portainer regelmäßig aktualisieren,
- Daten-Volume regelmäßig sichern,
- Backups nicht öffentlich ablegen,
- keine `planner.db`, Backups, Screenshots mit persönlichen Finanzdaten oder Zugangsdaten in das GitHub-Repository einchecken,
- bei externem Zugriff einen geeigneten Reverse Proxy mit TLS und zusätzlichem Zugriffsschutz verwenden.

Das öffentliche Repository enthält keine persönlichen Finanzdaten. Diese entstehen erst beim Betrieb der eigenen Installation.

---

## 16. Kurzcheck nach der Einrichtung

Nach Abschluss der Installation sollten folgende Punkte geprüft werden:

- [ ] Container `finanzlab` läuft.
- [ ] Healthcheck ist erfolgreich.
- [ ] Weboberfläche ist auf Port `8798` erreichbar.
- [ ] Haushalt wurde angelegt.
- [ ] alle benötigten Konten sind vorhanden.
- [ ] ein sinnvolles Standardkonto ist gesetzt.
- [ ] aktuelle Kontostände und deren Datum stimmen.
- [ ] Tagesbuchungen beim Kontostand sind korrekt gekennzeichnet.
- [ ] regelmäßige Einnahmen sind angelegt.
- [ ] regelmäßige und einmalige Ausgaben sind angelegt.
- [ ] vorhandene Kredite und Tilgungsanteile sind korrekt verknüpft.
- [ ] Umbuchungen zwischen eigenen Konten sind erfasst.
- [ ] die Monatsvorschau wurde kontrolliert.
- [ ] unter Einstellungen zeigt die Datenprüfung keine unerwarteten Fehler.
- [ ] ein erstes Backup des Volumes wurde erstellt.

Für die Bedienung der einzelnen Funktionen siehe zusätzlich [HANDBUCH.md](HANDBUCH.md).
