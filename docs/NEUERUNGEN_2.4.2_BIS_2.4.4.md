# FinanzLab – Ergänzungen zu Version 2.4.2 bis 2.4.4

Diese Ergänzung dokumentiert Änderungen nach der technischen Basisdokumentation 2.3.0. Sie ersetzt nicht die Funktionsbeschreibung der bestehenden Kapitel zu Krediten, Tilgungen und Konten.

## 12-Monats-Prognosecache ab 2.4.2

FinanzLab bereitet den aktuellen und die folgenden elf Kalendermonate im Hintergrund vor. Vorschauen werden nach Haushalt, Monat und Konto-/Kreditauswahl zwischengespeichert. Der Browsercache wird nach erfolgreichen schreibenden Aufrufen ungültig. Ein serverseitiger Cache kann identische Monatsanfragen wiederverwenden, solange seine Datenstandprüfung keine relevante Änderung an SQLite-Haupt-/WAL-Dateien feststellt. Monate außerhalb des Zeitraums werden bei Bedarf berechnet. Der Excel-Export berechnet seinen ausgewählten Zeitraum weiterhin eigenständig, falls keine passende Cache-Kopie vorliegt.

Die Finanzformeln wurden für diese Cache-Verbesserung nicht verändert.

## Geänderte Rückzahlungspläne der Kreditart „Geliehen“ ab 2.4.3

Das bewusste Speichern eines neuen Ratenplans für einen bestehenden „Geliehen“-Kredit beendet ab dem Änderungsstichtag andere monatliche Zahlungsreihen, die mit diesem Kredit verknüpft sind. Frühere Zahlungen und einmalige Rückzahlungen bleiben historisch erhalten. Die neue Ratenhilfe verwendet den offenen Saldo statt ausschließlich des ursprünglichen Kreditbetrags. Eine zu hohe Schlussrate wird auf die offene Restschuld begrenzt.

Bereits gespeicherte, konkurrierende Altpläne werden nicht beim bloßen Start der Software automatisch verändert. Die Bereinigung wird erst durch bewusstes Speichern des betreffenden neuen Plans ausgelöst. Vorher Datenbanksicherung anlegen.

Bei anderen Kreditarten ändern Sondertilgungen den vertraglichen Ratenplan nicht automatisch.

## Einzelratenkorrekturen bei „Geliehen“ ab 2.4.4

Wird ein einzelner Zahlungstermin in der Tages-/Monatsvorschau manuell im Betrag verändert, berücksichtigt **nur die Kreditart „Geliehen“** diesen geänderten Betrag auch für „Alle Tilgungen“, offene Restschuld und Schlussrate. Eine geänderte Einzelrate ändert nicht automatisch die Monatsrate der folgenden Termine. Frühere Teil-/Einmalzahlungen werden nicht doppelt verrechnet. Andere Kreditarten behalten ihre bisherige Berechnung.

## Zinsseite ab 2.4.3 und 2.4.4

„Geliehen“ wird einschließlich seiner Rückzahlungen und Teilrückzahlungen nicht in der Zinsen-Seite oder deren Kredit-Zinssummen angezeigt. Die zugrunde liegenden Buchungen werden dabei nicht aus der Finanzdatenbank gelöscht. Bei den übrigen Kreditarten stehen aktive Kredite zuerst; vollständig getilgte oder archivierte Kredite erscheinen am Ende. Die historische Zinsauswertung bleibt erhalten.

## Regressionstests

- `tests/test_release_242.py` – Cache/Release aus 2.4.2
- `tests/test_loan_plan_243.py`, `tests/test_credit_plan_replacement_243.py` und `tests/test_credit_plan_frontend_243.cjs` – Planänderungen und Ratenhilfe
- `tests/test_borrowed_override_interest_244.py` – Einzelratenkorrektur, Tilgung und Zinsen-Sortierung

Alle Tests verwenden fiktive Beispieldaten. Das Produktionsvolume `/data` ist nicht Bestandteil des Quellcodes.
