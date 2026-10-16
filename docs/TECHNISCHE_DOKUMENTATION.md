# FinanzLab – Technische Dokumentation

**Stand:** 2.4.0 · 10. Oktober 2026

**Projektkennzeichnung:** by Lrd.Tiberius

> Öffentliche Dokumentationsfassung. Sie enthält keine privaten Konten, konkreten Haushaltsdaten, lokalen Servernamen oder Zugangsdaten. Die Abschnitte 1–15 beruhen auf der technischen Beschreibung von 2.3.0; Abschnitt 16 ergänzt die Funktionen von 2.4.0.



| Bereich | Maßgebliche Quelle |
| --- | --- |
| Konten, Kredite, Prognosen, Umbuchungen | app/infrastructure/repository.py |
| Wiederholungen und Datumsanker | app/domain/recurrence.py |
| Basissimulation | app/domain/simulation.py |
| Darlehens- und Eingabehilfen | app/static/app.js, app/static/credit-archive.js |
| Archivierung | app/archive_support.py |
| EnergyLab-Schnittstelle | app/application/energylab_service.py + Repository |
| Excel-Ausgabe | app/application/excel_export.py + Repository |

1. Dokumentstatus und Rechenprinzipien

2. Datums-, Wiederholungs- und Buchungslogik

3. Kontostände, Anker und Projektionsengine

4. Einnahmen, Ausgaben und Bewegungsregeln

5. Umbuchungen und Rahmenkredit

6. Kredite, Zinsen und Tilgung

7. Darlehen / Hausfinanzierung

8. Monatsvorschau, Simulation und Liquiditätsvorschau

9. Dashboard-Kennzahlen

10. EnergyLab-Integration und Abrechnung

11. Kontoauszugsabgleich und Reconciliation

12. Excel-Export

13. Formelsammlung und Grenzwerte

14. Implementierungsgrenzen und bekannte Besonderheiten

15. Code-Quellenverzeichnis


## 1. Dokumentstatus und Rechenprinzipien


### 1.1 Autoritative Ebene

Für fachliche Ergebnisse gilt das Backend als verbindlich. JavaScript im Browser berechnet Vorschläge, Hinweise und Sofortvorschauen, darf aber eine serverseitige Validierung nicht ersetzen. Besonders wichtig ist das bei Rahmenkredit-Serien, Kreditzinsen und Darlehensraten.


| Ebene | Rolle | Verbindlichkeit |
| --- | --- | --- |
| Backend / Repository | Speichern, Projektion, Kredit-Timeline, Limits, Summen | Autoritativ |
| Domain | Wiederholungen, Datumsanker, elementare Simulation | Autoritativ |
| Frontend | Eingabehilfe, Vorschläge, UI-Hinweise | Nicht allein autoritativ |
| Excel-Export | Darstellung bereits berechneter Backend-Ergebnisse | Keine zweite Fachlogik |


### 1.2 Geldwerte und Rundung

FinanzLab speichert Geldwerte überwiegend als ganze Centbeträge. Damit werden klassische Gleitkommafehler in der Persistenz vermieden. Prozent- und Zinsrechnungen verwenden im Backend Decimal und runden auf ganze Cent mit ROUND_HALF_UP. Das Frontend wandelt Euro-Eingaben mit Math.round(Euro * 100) in Cent um.


> Euro nach Cent\
> cents = round(euro_value * 100)\
> Im Browser wird Math.round verwendet; Backend-APIs erwarten anschließend ganze Centwerte.\
> Beispiel: 123,45 EUR -> 12.345 Cent.


> Monatszins aus Jahres-Sollzins\
> interest_cents = ROUND_HALF_UP(balance_cents * annual_percent / 1200)\
> annual_percent ist ein Prozentwert, z. B. 6 für 6 % p. a. Division durch 1200 entspricht /12 und /100.\
> Beispiel: 10.000 EUR Restschuld bei 6 % -> 50,00 EUR Zins für den Monat.

Code-Fundstelle: repository.py: inferred_nominal_apr(), _credit_timelines(); app.js: euroCents().


### 1.3 Datenbank und Stichtagsprinzip

Die Datenbankdatei heißt planner.db. Der Ablageort wird über DATA_DIR bestimmt; im Containerbetrieb liegt die Datei unter dem gemounteten Datenverzeichnis. Nahezu alle Auswertungen arbeiten mit einem expliziten Stichtag (as_of). Dadurch kann derselbe Datenbestand historisch oder für zukünftige Prognosen betrachtet werden.


## 2. Datums-, Wiederholungs- und Buchungslogik


### 2.1 Verankerte Monatsfolge

Monatliche, quartalsweise, halbjährliche und jährliche Folgen bleiben immer am ursprünglichen Fälligkeitstag verankert. Ein kurzer Monat verschiebt die Serie nicht dauerhaft.


> Verankerter Zieltag\
> target_day = min(original_day, days_in_target_month)\
> Der Monatsabstand wird immer vom ursprünglichen first_due_date aus berechnet.\
> Beispiel: 31.01. -> 28.02. (oder 29.02.) -> 31.03.; die Serie driftet nicht dauerhaft auf den 28.


| Rhythmus | Intervall |
| --- | --- |
| Wöchentlich | 7 Tage; nur bei normalen Ausgaben vorgesehen |
| Monatlich | 1 Monat |
| Quartalsweise | 3 Monate |
| Halbjährlich | 6 Monate |
| Jährlich | 12 Monate |
| Einmalig | genau eine Ausführung |


### 2.2 Ende, Anzahl und Grenzen

Eine Anzahl bezeichnet die maximale Zahl vertraglicher Ausführungen ab der ersten Fälligkeit. Ein Enddatum begrenzt die wirksamen Ausführungen. Werden Ende und Anzahl gemeinsam angegeben, muss das Enddatum exakt dem berechneten Datum der letzten nummerierten Ausführung entsprechen.


> Letzte monatliche Ausführung\
> last_date = add_months_anchored(first_due, (count - 1) * interval_months)\
> Für wöchentliche Folgen gilt first_due + 7 * (count - 1) Tage.

Versionierungsgrenzen (active_from / active_to) und Stream-Grenzen (stream_start / stream_end) entscheiden nur, ob eine vertragliche Ausführung wirksam ist. Sie verschieben den ursprünglichen Rhythmus nicht.


### 2.3 Wochenendverschiebung

Vertragliches Fälligkeitsdatum und tatsächlicher Plan-Buchungstag sind getrennt. Normale Einnahmen/Ausgaben sowie Darlehensraten werden bei Samstag/Sonntag auf den vorherigen Freitag verschoben. Nicht-Hypotheken-Kreditraten können dagegen auf den folgenden Montag verschoben werden, damit die Rate nicht in den Vormonat fällt. Umbuchungen verwenden die vertraglichen Fälligkeitstage ohne Wochenendverschiebung.


| Bewegung | Wochenendregel |
| --- | --- |
| Normale Einnahme / Ausgabe | vorheriger Freitag |
| Kreditrate, kein Darlehen | folgender Montag |
| Darlehensrate / mortgage | vorheriger Freitag |
| Umbuchung | keine Verschiebung |

Code-Fundstelle: domain/recurrence.py: add_months_anchored(), recurrence_dates(), planned_booking_dates().


## 3. Kontostände, Anker und Projektionsengine


### 3.1 Auswahl des Kontostandankers

Für jedes Konto wird zum gewählten Stichtag der jüngste bekannte Kontostand verwendet, dessen Ankerdatum nicht nach dem Stichtag liegt. Manuelle Anker und bestätigte Kontoauszugssalden werden gemeinsam betrachtet. Liegen beide am selben Tag, hat der Kontoauszug Vorrang; bei weiterer Gleichheit gewinnt der zuletzt aufgezeichnete Eintrag.


| Priorität | Regel |
| --- | --- |
| 1 | höchstes anchor_date <= Stichtag |
| 2 | bei gleichem Datum: statement vor manual |
| 3 | bei gleichem Typ: jüngster recorded_at |


### 3.2 Grundformel der Projektion


> Projizierter Kontostand\
> projected_balance = anchor_balance + sum(applied_event_amounts)\
> Es zählen nur Bewegungen nach dem wirksamen Anker bzw. Bewegungen am Ankertag, wenn bookings_applied=0.\
> Beispiel: Anker 1.000 EUR + Einkommen 500 EUR - Ausgabe 300 EUR = 1.200 EUR.

Für jede angewendete Bewegung wird der Kontostand fortgeschrieben. Positive Beträge erhöhen, negative Beträge vermindern den Kontostand. Die Engine kennzeichnet außerdem Ereignisanzahl, prognostizierte Einnahmen und prognostizierte Ausgaben.


### 3.3 Doppelzählung verhindern

FinanzLab kombiniert Planbewegungen mit echten Bankbuchungen. Bereits zugeordnete Planvorkommen werden nicht erneut materialisiert. Gleiches gilt für aus einer ungeklärten Kontoauszugsabbuchung erzeugte "Sonstige Zahlung": Die Bankbuchung bleibt die tatsächliche Wahrheit, der erzeugte Cashflow dient der Klassifizierung und wird nicht ein zweites Mal als Planbewegung addiert.

movement_completions: als erledigt markierte Planbewegungen bleiben sichtbar und werden nicht mehr erneut in die Kontostand-/Liquiditätsprojektion eingerechnet. Für die operativen Monatswerte bleiben sie Bestandteil der Einnahmen bzw. Ausgaben.

movement_amount_overrides: einzelne geplante Ausgaben können für genau ein Vorkommen betragsmäßig überschrieben werden. Dieser effektive Vorkommensbetrag wird auch in den operativen Monatswerten verwendet.

bookings_applied=1: Bewegungen am Ankertag gelten bereits als im Saldo enthalten und werden nicht erneut addiert.


### 3.4 Dispo- und Limitprüfung


> Limitüberschreitung\
> exceeded = (limit > 0) and (projected_balance < -limit)


> Überschreitungsbetrag\
> overage = max(0, -limit - projected_balance)


> Wichtig\
> Das historische overdraft_apr-Feld bleibt aus Kompatibilitätsgründen in SQLite, ist aber nicht Teil des aktuellen Planungsmodells. Girokonto-Dispozinsen werden nicht automatisch aus Kontostand und APR berechnet.

Code-Fundstelle: repository.py: household_detail(), projected_account_balances(), overdraft_values().


## 4. Einnahmen, Ausgaben und Bewegungsregeln


### 4.1 Cashflows

Cashflows bestehen aus Betrag, Rhythmus, erster Fälligkeit, optionalem Enddatum bzw. einer Dauer/Anzahl, Konto und Kategorie. Beträge werden als positive Centwerte gespeichert; die Bewegungsrichtung ergibt sich aus kind=income oder kind=expense.


| Regel | Umsetzung |
| --- | --- |
| Einnahme | +amount_cents auf dem Konto |
| Ausgabe | -amount_cents auf dem Konto |
| Wöchentlich | nur für Ausgaben zulässig |
| Ende + Anzahl | müssen rechnerisch konsistent sein |
| Rahmenkredit als Konto | für Cashflows nicht zulässig; nur über Umbuchungen |


### 4.2 Kreditgebundene Ausgaben

Eine Kreditrate ist zugleich eine Kontoausgabe und ein Ereignis in der Kredit-Timeline. Der Kontobetrag kann deshalb vom tatsächlichen Tilgungsanteil abweichen. FinanzLab nutzt bei der Kontoprojektion account_amount_cents aus der Kredit-Timeline, während balance_reduction_cents den Kreditsaldo reduziert.


> Allgemeine Trennung\
> account_debit = Zinsanteil + Tilgungsanteil (+ ggf. Abschlusskorrektur)

credit_reduction_cents darf nicht größer als der Kontobetrag sein. Fehlt der Wert in einem manuellen/legacy Plan, wird der Kontobetrag als Tilgungsvorgabe verwendet.


### 4.3 Einzelne Bewegungen abschließen oder überschreiben

Ein geplantes Vorkommen wird eindeutig durch occurrence_key identifiziert. Der Schlüssel enthält Typ, Objekt-ID und Datum. Eine Abschlussmarkierung nimmt das Vorkommen aus der erneuten Kontoprojektion, nicht aber aus der operativen Monatsrechnung. Bei geplanten Ausgaben kann zusätzlich nur der Betrag dieses einen Vorkommens überschrieben werden, ohne den zugrunde liegenden Dauerauftrag zu verändern. Ist das Vorkommen bereits erledigt, verändert ein nachträglicher Override deshalb den operativen Monatswert, nicht jedoch nochmals die Liquiditätsprojektion.

Code-Fundstelle: repository.py: cash_flow_values(), set_movement_completion(), set_movement_amount().


## 5. Umbuchungen und Rahmenkredit


### 5.1 Normale Umbuchung

Eine Umbuchung erzeugt für jede Fälligkeit zwei Bewegungen gleichen Betrags: Quelle negativ, Ziel positiv. Sind beide Konten in derselben Liquiditätssumme enthalten, ist der Nettoeffekt auf die Gesamtsumme null; als Transfer-Volumen werden allerdings beide Bewegungsseiten gezählt.


> Umbuchung\
> source_event = -amount; target_event = +amount


### 5.2 Verknüpfung eines Rahmenkredits

Ein Rahmenkredit darf nur mit seinem hinterlegten Verrechnungskonto umgebucht werden. Direkte Umbuchungen zwischen zwei Rahmenkrediten sind verboten. Der Rahmenkredit wird außerdem aus der normalen Liquiditätssumme herausgehalten und separat als Finanzierung gezeigt.


### 5.3 Verfügbarer Kreditrahmen


> Nutzung\
> used = max(0, -projected_credit_line_balance)


> Verfügbarer Rahmen\
> available = max(0, limit - used)\
> Ein positiver Rahmenkredit-Kontostand verbraucht keinen Kreditrahmen.\
> Fiktives Beispiel: Limit 15.000 EUR, Prognosesaldo -13.000 EUR -> 13.000 EUR genutzt, 2.000 EUR verfügbar.


### 5.4 Prüfung zukünftiger Einzel- und Serienauszahlungen

Version 2.3.0 prüft eine Auszahlung nicht gegen den heutigen freien Rahmen, sondern gegen die Prognose am jeweiligen Fälligkeitstag. Wiederkehrende Auszahlungen müssen durch Enddatum oder Anzahl begrenzt sein. Der Server prüft jede einzelne Ausführung der Serie.

Für jede Fälligkeit die Konten bis zu diesem Datum projizieren; beim Bearbeiten die bestehende Umbuchung aus der Projektion ausschließen.

Frühere Ausführungen derselben neu anzulegenden Serie kumulativ berücksichtigen.

Verfügbaren Rahmen am jeweiligen Datum berechnen.

Nur speichern, wenn der Einzelbetrag bei jeder Ausführung <= verfügbarer Rahmen ist.


> Serienprüfung - Saldo vor Ausführung i\
> balance_before_i = projected_balance_at_date_i - amount * i\
> i beginnt bei 0. Die Projektion kennt die neu anzulegende Serie noch nicht; deshalb werden frühere Ausführungen der Kandidatenserie rechnerisch abgezogen.


> Serienprüfung - verfügbar\
> available_i = max(0, limit - max(0, -balance_before_i))


> Speicherbedingung\
> amount <= available_i  for every occurrence i


> UI-Hinweis\
> Der Dialog zeigt den prognostizierten Rahmen am gewählten ersten Fälligkeitstag. Bei Serien ist die serverseitige Prüfung jeder einzelnen späteren Ausführung maßgeblich.

Code-Fundstelle: repository.py: transfer_values(); app.js: refreshTransferCreditLineHint(), syncTransferCreditLine().


## 6. Kredite, Zinsen und Tilgung


### 6.1 Kreditarten und gemeinsame Grunddaten

FinanzLab unterscheidet Konsumkredit, Kredit, Geliehen und Darlehen (mortgage). Der offene Saldo startet mit opening_balance_cents. Eine vertragliche Restschuld / Schlussrate (balloon_payment_cents) kann die automatische Tilgung begrenzen; beim Darlehen wird dieses Backend-Feld bewusst auf 0 gesetzt.


| Begriff | Bedeutung |
| --- | --- |
| opening_balance_cents | für die Timeline maßgeblicher Anfangs-/Restsaldo |
| interest_rate | nominaler Sollzins p. a.; treibt die Zinsberechnung |
| automatic_interest | Zins- und Tilgungsanteile werden aus Rate und Saldo berechnet |
| balloon_payment_cents | vertraglich verbleibender Zielrest bei normalen Krediten |
| payment_count | 1 bis 1.200 Zahlungen |


### 6.2 Konsumkredit: Preiszusammenhänge

Beim Neuanlegen kann FinanzLab fehlende Vertragswerte aus den übrigen Angaben ableiten. Beim späteren Bearbeiten werden bestehende Vertragswerte bewusst nicht still neu berechnet.


> Finanzierungspreis aus Ratenplan\
> financing_price = installment * count + balloon


> Ratenaufschlag\
> surcharge = max(0, financing_price - product_price)


> Finanzierungspreis aus Produkt + Aufschlag\
> financing_price = product_price + surcharge


> Produktpreis aus Finanzierung - Aufschlag\
> product_price = max(0, financing_price - surcharge)

Ist der gespeicherte Anfangssaldo bei einem neuen Konsumkredit 0 und ein Finanzierungspreis vorhanden, wird der Anfangssaldo auf den Finanzierungspreis gesetzt.


### 6.3 UI-Vorschläge für Rate und Anzahl


> Vorschlagsbasis\
> base = max(0, (opening_balance or financing_price) - balloon)


> Anzahl aus Rate\
> suggested_count = ceil(base / installment)


> Rate aus Anzahl\
> suggested_installment = ceil(base / count)  [Cent]\
> Diese Werte sind Eingabehilfen. Die fachliche Kredit-Timeline wird serverseitig erzeugt.


### 6.4 Nominalzins aus Ratenplan rückrechnen

Fehlt bei aktivierter automatischer Zinsberechnung ein manueller Sollzins, versucht FinanzLab den nominalen Jahreszins aus einem begrenzten monatlichen Zahlungsplan zu bestimmen. Gesucht wird der Monatszins r, bei dem der Barwert aller Raten plus Schlussrate genau dem Kapital entspricht.


> Barwertgleichung\
> principal = SUM(k=1..n) payment / (1+r)^k + balloon / (1+r)^n


> Jahres-Sollzins\
> nominal_apr_percent = r * 1200\
> Die Nullstelle wird per Intervallsuche/Bisektion bestimmt (96 Iterationen) und auf 0,0001 Prozentpunkte ROUND_HALF_UP gerundet.

Wenn Rate * Anzahl + Schlussrate kleiner als das Kapital ist, existiert für dieses Modell kein nichtnegativer Zinssatz; das Ergebnis bleibt dann undefiniert. Bei exakter Gleichheit ist der abgeleitete Zinssatz 0 %.


### 6.5 Reihenfolge der Kreditereignisse

Die Kredit-Timeline verarbeitet manuelle Zahlungen und planmäßige Kreditraten chronologisch. Am selben Tag werden manuelle Kreditbewegungen vor verknüpften Ausgaben verarbeitet. Dadurch wirkt eine Sondertilgung oder Aufstockung zuerst auf den Kreditsaldo.


### 6.6 Manuelle Tilgung und Kreditaufstockung


> Positive manuelle Tilgung\
> effective = min(requested, remaining_before)


> Überzahlung\
> overpaid = max(0, requested - effective)

Ein negativer manueller Betrag stellt eine Kreditaufstockung dar und erhöht den offenen Saldo. Manuelle Kreditbewegungen erzeugen selbst keinen Kontoumsatz; account_amount_cents ist 0. Der Nutzer erfasst damit eine Saldoanpassung, nicht automatisch eine Bankbuchung.


### 6.7 Automatische Zins-/Tilgungsrechnung - Standardkredit


> Zinsanteil\
> interest = ROUND_HALF_UP(remaining_before * nominal_apr_percent / 1200)


> Planmäßiger Tilgungsanteil\
> scheduled_principal = max(0, planned_account_payment - interest)


> Maximal zulässige Tilgung\
> available_principal = max(0, remaining_before - contractual_residual)


> Wirksame Tilgung\
> effective_principal = min(scheduled_principal, available_principal)


> Neuer Kreditsaldo\
> remaining_after = max(0, remaining_before - balance_reduction)

Der Kontobetrag der Rate wird auf den tatsächlich noch notwendigen Betrag begrenzt. Ist die vertragliche Restschuld erreicht, werden weitere planmäßige Raten übersprungen.


### 6.8 Kleine Restbeträge am Planende

Bei der ausdrücklich letzten planmäßigen Rate sammelt das Backend einen verbleibenden Rest oberhalb der vertraglichen Restschuld automatisch ein, wenn dieser Rest kleiner als 3,00 EUR ist. Damit bleiben keine wenigen Cent Restschuld zurück.


> Abschlusskorrektur\
> final_residual_added = residual_above_target if 0 < residual_above_target < 300 cents else 0


> UI vs. Backend\
> Die Oberfläche kann bei Ratenvorschlägen mit einer deutlich größeren Hinweistoleranz arbeiten. Für die tatsächliche automatische Abschlusskorrektur ist ausschließlich die Backend-Grenze < 300 Cent maßgeblich.


### 6.9 Konsumfinanzierung mit Produkt- und Finanzierungspreis

Bei einer Konsumfinanzierung unterscheidet FinanzLab den offenen Finanzierungssaldo von der noch verzinslichen Produktpreis-Restbasis. Dadurch können noch nicht entstandene Finanzierungskosten entfallen, wenn das eigentliche Kapital vorzeitig vollständig getilgt wurde.


> Initiale verzinsliche Basis\
> interest_remaining = ROUND_HALF_UP(product_price * opening_balance / financing_price)


> Monatszins Konsumfinanzierung\
> interest = ROUND_HALF_UP(interest_remaining * nominal_apr_percent / 1200)


> Finanzierungssaldo-Reduktion\
> balance_reduction = min(planned_account_payment, remaining_before - contractual_residual)


> Angezeigte Kapitaltilgung\
> effective_principal = min(max(0, account_payment - interest), interest_remaining)

Sinkt interest_remaining auf 0, wird der Finanzierungssaldo mindestens bis zur ausdrücklich vereinbarten Restschuld heruntergesetzt. Nicht entstandene zukünftige Finanzierungskosten bleiben somit nicht als Phantom-Restschuld bestehen.


### 6.10 Legacy-/manuelle Pläne ohne automatische Zinsrechnung

Wenn ein alter oder manuell gepflegter Plan sowohl Kontobetrag als auch tatsächliche Tilgungsreduktion enthält, wird die Differenz als einziger verlässlich verfügbarer Zinsanteil interpretiert.


> Abgeleiteter Zins bei manuellem Plan\
> interest = max(0, account_payment - effective_principal)


### 6.11 Kreditübersichten

Die Listenansicht kann entweder auf den heutigen Ist-Stichtag begrenzt sein oder bei simulate_future=True gezielt einen Zukunftsstichtag verwenden. Für jeden Kredit werden bisherige und zukünftige Tilgung, bisherige und zukünftige Zinsen, offene Restschuld, Überzahlung sowie der voraussichtliche Tilgungszeitpunkt berechnet.


> Wirksam getilgt bis Stichtag\
> effective_paid = sum(balance_reduction for event_date <= cutoff)


> Restschuld\
> remaining = max(0, opening_balance - effective_paid)


> Konsumkredit-Anzahlung / bereits enthalten\
> initial_paid = max(0, financing_total - opening_balance)


> Angezeigt getilgt\
> paid = min(max(opening_balance, financing_total), initial_paid + effective_paid)


### 6.12 Zinsübersicht

Die Zinsübersicht trennt berechnete Kreditzinsen, geplante künftige Kreditzinsen und manuell als Ausgabe erfasste Girokonto-Zinsen. Manuelle Girokonto-Zinsen sind normale Ausgaben der Kategorie interest; sie werden nicht aus dem Girokontostand berechnet.


> Erwartete Kreditzinsen gesamt\
> expected_total_interest = interest_to_cutoff + future_interest

Code-Fundstelle: repository.py: credit_values(), inferred_nominal_apr(), _credit_timelines(), list_credits(), list_interest(); credit-archive.js: syncConsumerFieldsV15().


## 7. Darlehen / Hausfinanzierung


### 7.1 Eingabemodell

Darlehen werden intern als Kredit mit mortgage-Untertyp behandelt. Gespeichert werden ursprüngliche Darlehenssumme, aktueller Rest-/Anfangssaldo, Stichtag dieses Saldos, nominaler Sollzins, effektiver Jahreszins, Tilgungssatz, Ende der Zinsbindung und Sondertilgungsprozentsatz. Für Berechnungen ist der nominale Sollzins maßgeblich; der effektive Jahreszins wird gespeichert und angezeigt, aber nicht zur Tilgungssimulation verwendet.


### 7.2 Automatische Monatsrate aus Sollzins + Tilgung


> Monatsrate\
> monthly_payment = round(original_principal * (nominal_interest_percent + repayment_percent) / 1200)\
> Die Startformel verwendet die ursprüngliche Darlehenssumme, nicht die aktuelle Restschuld.\
> Beispiel: 200.000 EUR, 3 % Sollzins, 2 % Tilgung -> ca. 833,33 EUR pro Monat.

Die Monatsrate kann im Frontend manuell überschrieben werden. Die Oberfläche zeigt dann zusätzlich, welche Rate nach der Automatikformel entstanden wäre.


### 7.3 Anzahl Raten bis Zinsbindungsende


> Monatsanzahl inkl. Startmonat\
> count = (end_year - start_year) * 12 + (end_month - start_month) + 1

Die Oberfläche setzt die Zahlungsanzahl bei Darlehen automatisch aus erster Rate und Ende der Zinsbindung.


### 7.4 Voraussichtliche Restschuld am Zinsbindungsende

Die UI berechnet die Restschuld iterativ aus aktuellem Rest-/Anfangssaldo, Monatsrate und nominalem Sollzins. Pro Monat wird zuerst der Zinsanteil aus dem aktuellen Restsaldo berechnet und anschließend der verbleibende Ratenanteil getilgt.


> Monat i - Zins\
> interest_i = round(remaining_i * nominal_interest_percent / 1200)


> Monat i - Tilgung\
> principal_i = monthly_payment - interest_i


> Monat i - Restschuld\
> remaining_(i+1) = max(0, remaining_i - principal_i)

Wenn der Tilgungsanteil <= 0 wird, bricht die Vorschau ab. Das im Darlehensformular angezeigte Feld "voraussichtliche Restschuld" ist eine UI-Berechnung; das Backend speichert bei mortgage keine vertragliche balloon_payment_cents, sondern lässt die Restschuld aus dem begrenzten Ratenplan entstehen.


### 7.5 Sondertilgungsgrenze


> Jährlicher Sondertilgungsrahmen\
> special_limit = ROUND_HALF_UP(original_principal * special_repayment_percent / 100)


> Implementierungsstand\
> Der jährliche Sondertilgungsrahmen wird berechnet und angezeigt. Im vorliegenden 2.3.0-Code ist keine harte serverseitige Sperre zu sehen, die manuelle Kredit-Zahlungen gegen dieses Jahreslimit summiert und ablehnt.

Code-Fundstelle: app.js: bindMortgagePlanV200(); repository.py: credit_values(), list_credits().


## 8. Monatsvorschau, Simulation und Liquiditätsvorschau


### 8.1 Tagesbasierte Kontosimulation

Die elementare Domain-Simulation führt einen Kontostand Tag für Tag ab einem Anker fort. In der Repository-Projektion wird dieselbe Grundidee um Versionen, reale Bankbuchungen, Kreditkorrekturen, Abschlüsse und Overrides erweitert.


> Tagesfortschreibung\
> balance_day = balance_previous + sum(events_on_day)


### 8.2 Simulations-Dashboard

Für eine ad-hoc Simulation können bis zu vier Konten gewählt werden. FinanzLab projiziert den Stichtag und das Monatsende. Die Tagesdifferenz basiert auf angewendeten Ereignissen exakt am Stichtag; der Monatsrest berücksichtigt Bewegungen nach dem Stichtag bis Monatsende.


> Tagesdelta\
> day_delta = day_income - day_expense


> Restmonat-Delta\
> period_delta = period_income - period_expense


> Projizierte Gesamtsumme\
> projected_total = sum(projected_balance of selected accounts)


### 8.3 Monatsvorschau

Die Monatsvorschau beginnt mit dem projizierten Kontostand am Tag vor Monatsbeginn und führt alle angewendeten Ereignisse des Monats fort. Wenn während des Monats keine Anker-/Versionskonstellation einen täglichen Neuaufbau erzwingt, verwendet FinanzLab einen schnelleren Pfad; andernfalls fällt es auf eine bewiesene Tagesberechnung zurück.


> Kontodelta im Monat\
> month_delta = closing_balance - opening_balance


> Minimaler Monatsstand\
> minimum_balance = min(opening_balance, all_daily_balances)


> Monatliche Limitüberschreitung\
> monthly_overage = max(0, -limit - minimum_balance)  if minimum_balance < -limit


> Monatssumme Konten\
> opening_total = sum(account_opening); closing_total = sum(account_closing)


> Gesamtdelta\
> delta = closing_total - opening_total

Die Monatsvorschau summiert Einnahmen nur aus positiven income-Ereignissen und Ausgaben als Betrag der negativen expense-Ereignisse. Transfer-Volumen ist die Summe der Absolutbeträge aller transfer_in/transfer_out-Beine. Werden beide Seiten einer internen Umbuchung ausgewählt, erscheint der Betrag daher zweimal im Volumen, obwohl der Nettoeffekt null ist.


### 8.4 Kreditwerte in der Monatsvorschau

Für ausgewählte Kredite wird die kumulierte balance_reduction_cents aus der Kredit-Timeline verwendet. Aufstockungen können diese kumulierte Tilgung negativ verändern. Die Restschuld wird nie kleiner als 0 dargestellt.


> Kredit-Restschuld am Tag\
> credit_remaining = max(0, opening_credit_balance - cumulative_balance_reduction)


### 8.5 Liquiditätsvorschau 6 Monate

Die Liquiditätsvorschau kann 1 bis 12 Folgemonate berechnen; die Oberfläche nutzt standardmäßig sechs. Gezeigt werden der 15. und der Monatsletzte. Rahmenkredite sind ausdrücklich ausgeschlossen; es werden höchstens vier normale Bankkonten verwendet.


> Stichtagssumme\
> liquidity_point_total = sum(projected_balance of selected non-credit-line accounts)

Der erste Vorschaupunkt liegt im Monat nach dem gewählten Basismonat. Pro Monat werden Kontostände getrennt je Konto sowie die Summen am 15. und Monatsende zurückgegeben.

Code-Fundstelle: repository.py: simulation_dashboard(), monthly_preview(), _monthly_preview_daily(), liquidity_outlook(); domain/simulation.py.


## 9. Dashboard-Kennzahlen


### 9.1 Bankliquidität und Rahmenkredit getrennt

Das Dashboard projiziert alle Konten zum gewählten Stichtag, trennt anschließend normale Bankkonten von Rahmenkrediten und bildet die Bankliquidität nur aus den normalen Konten. Das verhindert, dass eine Kreditlinie als positives liquides Vermögen erscheint.


> Bankliquidität\
> balance_cents = sum(projected_balance of non-credit-line accounts)


### 9.2 Monatliche Einnahmen und Ausgaben

Die Monatswerte werden occurrence-basiert aus den zum Monat wirksamen Cashflow-Versionen gebildet. Einzelne Betragsüberschreibungen werden berücksichtigt; kreditgebundene Ausgaben können durch die Kredit-Timeline auf ihren effektiven Kontobetrag angepasst werden. Für „Operativ frei“ gilt damit der effektive Betrag des Vorkommens (Override, falls vorhanden, sonst Planbetrag) unabhängig vom Erledigt-Status. „Erledigt“ verhindert ausschließlich die erneute Anwendung auf den Kontostand und nimmt die Ausgabe bzw. Einnahme nicht aus der operativen Monatsrechnung.


> Operativer Überschuss\
> operating_surplus = monthly_income - monthly_expenses


### 9.3 Liquiditäts- und Finanzierungseffekt

Das Dashboard vergleicht den operativen Überschuss mit der tatsächlichen Veränderung der normalen Bankkonten. Umbuchungen zwischen normalen Bankkonten heben sich dabei netto auf. Bewegungen zwischen Rahmenkredit und Verrechnungskonto verändern dagegen die normale Bankliquidität.


> Liquiditätsdelta\
> liquidity_delta = sum(applied movements touching liquid accounts)


> Finanzierungseffekt\
> financing_effect = liquidity_delta - operating_surplus

Damit kann das Dashboard sichtbar machen, welcher Teil der Liquiditätsänderung nicht aus laufenden Einnahmen/Ausgaben, sondern beispielsweise aus Kreditaufnahme, Tilgung oder anderen Finanzierungsvorgängen stammt.


### 9.4 Rahmenkredit-Kennzahlen


> Genutzter Rahmen\
> credit_used = max(0, -projected_balance)


> Freier Rahmen\
> credit_available = max(0, credit_limit - credit_used)


> Nutzungsquote\
> usage_percent = min(100, credit_used / credit_limit * 100)  [bei limit > 0]


### 9.5 Dashboard-Monatsauswahl

Seit Version 2.3.0 verwendet die Dashboard-Monatsauswahl ein sichtbares HTML-select statt eines transparent überlagerten input[type=month]. Die Optionen umfassen standardmäßig 120 Monate vor und 120 Monate nach dem aktuellen Monat; liegt ein bereits gewählter Monat außerhalb, wird der Bereich um diesen Wert erweitert. Ein Wechsel lädt das Dashboard über loadDashboardMonth() mit dem Monatsletzten als as_of neu. Die Pfeile und „Aktueller Monat“ verwenden dieselbe Ladefunktion. Dashboard-Monat und Vorschau-Monat sind getrennte Zustände (dashboardMonth bzw. previewMonth); für einen direkten Vergleich müssen daher bewusst dieselben Monate gewählt werden.

Code-Fundstelle: repository.py: dashboard(); archive_support.py: Dashboard-Wrapper für Kredit-/Darlehensdarstellung; app.js: dashboardMonthOptions(), updateDashboardMonthControl(), loadDashboardMonth().


## 10. EnergyLab-Integration und Abrechnung


### 10.1 Was FinanzLab übernimmt

Die EnergyLab-Schnittstelle überführt vertragliche Abschläge in FinanzLab-Cashflows. Verbrauchskosten, Grundgebühren, Zählerstände und Abrechnungssalden werden nicht als zusätzliche Plan-Ausgaben dupliziert. Unterstützt sind u. a. Strom, Gas, Wasser und Abwasser-Vertragssegmente.


### 10.2 Euro-/Cent-Normalisierung


> EnergyLab-Wert in Cent\
> cents = ROUND_HALF_UP(Decimal(value) * 100)

Negative Plan-Abschläge werden nicht akzeptiert. Ereignisse können dagegen je nach Ereignistyp ein positives oder negatives tatsächliches Vorzeichen erhalten.


### 10.3 Erste Fälligkeit ohne Rhythmusdrift

Aus Vertragsstart, Zahlungstag und Rhythmus wird die erste wirksame Fälligkeit bestimmt. Liegt der Zahlungstag im Startmonat bereits vor dem Vertragsbeginn, wird um ein vollständiges Rhythmusintervall weitergeschaltet. Auch spätere Versionsgrenzen ändern den ursprünglichen Takt nicht.


> Zahlungstag im Monat\
> due_day = min(configured_payment_day, days_in_month)


### 10.4 Abschlagsänderungen und Pausen

Betragsänderungen erzeugen Versionen mit Wirksamkeitsgrenzen. Pausen werden als inaktive Zeitabschnitte modelliert; eine Wiederaufnahme erzeugt wieder eine aktive Version. Die ursprüngliche vertragliche Fälligkeitsverankerung bleibt erhalten, sodass ein 31.-Rhythmus nach Februar wieder auf den 31. zurückkehrt.


### 10.5 Ist-Zahlungen

Tatsächliche Zahlungen können aus bestätigten EnergyLab-Ereignissen oder bestätigten Kontoauszugszuordnungen stammen. Zahlungen werden als positiver Betrag, Erstattung/Chargeback als negativer Betrag geführt. Pending oder ignorierte Ereignisse zählen nicht in einen finalen Abrechnungssnapshot.


### 10.6 Plan-/Ist-Abrechnungssnapshot


> Geplanter Gesamtabschlag\
> planned_total = SUM(active_version: number_of_planned_dates_in_period * amount_cents)


> Tatsächlicher Zahlungsbetrag\
> actual_total = SUM(confirmed actual_amount_cents in billing period)

Ein Abrechnungssnapshot friert Plan, Ist, Zahlungs-IDs und übergebene Abrechnungsdaten ein. Aus diesen Daten wird ein SHA-256-Hash gebildet. Ist der neu berechnete Hash identisch mit der jüngsten Revision, wird kein doppelter Snapshot erzeugt.

Code-Fundstelle: repository.py: energylab_first_due(), _normalize_energylab_payload(), actual_energylab_payments(), _planned_energylab_total(), create_energylab_billing_snapshot().


## 11. Kontoauszugsabgleich und Reconciliation


### 11.1 Kandidatenfenster

Für die automatische Zuordnung werden geplante Cashflow-Vorkommen in einem erweiterten Zeitraum von sieben Tagen vor bis sieben Tage nach dem Kontoauszugszeitraum betrachtet. Bereits bestätigte occurrence_keys werden nicht erneut angeboten.


### 11.2 Betragstoleranz


> Betragstoleranz\
> tolerance = max(100, min(500, round(abs(planned_amount) * 0.05)))  [Cent]\
> Mindestens 1,00 EUR, höchstens 5,00 EUR, ansonsten 5 % des Planbetrags.\
> Beispiel: Bei 50 EUR Planbetrag: 2,50 EUR Toleranz; bei 200 EUR: wegen Deckel maximal 5,00 EUR.

Kandidat und Bankbuchung müssen dasselbe Vorzeichen haben. Die Datumsdistanz darf höchstens sieben Tage betragen.


### 11.3 Matching-Score


> Betragsstrafe\
> amount_penalty = round(35 * amount_difference / max(1, tolerance))


> Score\
> score = clamp(0, 100, 100 - amount_penalty - 5 * date_distance + min(15, 5 * token_overlap))

Texttokens werden aus Gegenpartei, Verwendungszweck, Referenz und Planbezeichnung normalisiert. Tokens unter drei Zeichen sowie häufige generische Wörter werden ignoriert.


### 11.4 Automatischer Vorschlag

Ein Treffer wird nur dann automatisch vorgeschlagen, wenn der Betrag exakt übereinstimmt, die Datumsdistanz höchstens drei Tage beträgt und der Treffer eindeutig ist. Bei mehreren Kandidaten muss der beste Score mindestens 10 Punkte vor dem zweitbesten liegen. Tolerierte, aber nicht exakte Beträge bleiben immer im Review.


| Situation | Vorschlag |
| --- | --- |
| Eindeutiger exakter Treffer | match |
| Mehrdeutige Kandidaten | review |
| Unbekannte Abbuchung | other_expense |
| Unbekannte Gutschrift | actual_only |
| Bereits importierte Zeile | skip / duplicate |


### 11.5 Saldoreconciliation


> Abweichung zum Kontoauszug\
> delta = closing_balance_from_statement - projected_balance_before_reconciliation

Beim Abschluss eines Kontoauszugs wird der bestätigte Endsaldo als Reconciliation-Anker gespeichert. Ein bereits aktiver Anker am selben Datum wird auf superseded gesetzt. Dieser bestätigte Saldo wird bei späteren Projektionen als bevorzugter statement-Anker verwendet.

Code-Fundstelle: repository.py: planned_occurrences_for_matching(), save_bank_statement_preview(), commit_bank_statement_preview().


## 12. Excel-Export


### 12.1 Berechnungsquelle

Der XLSX-Export berechnet Finanzdaten nicht unabhängig neu. Das Repository erzeugt zunächst occurrence-basierte Monatsvorschauen für den gewünschten Zeitraum; die Exportlogik schreibt diese Ergebnisse in Tabellenblätter und ergänzt nur Darstellungs- bzw. Summenformeln.

Der Export ist auf maximal 24 Monate begrenzt. Enthalten sind unter anderem Tagesstände, Konten, Kredite, Bewegungen und Monatskennzahlen. Dadurch bleiben Bildschirm und Export auf derselben fachlichen Backend-Logik.


> Konsequenz\
> Wenn sich eine Rechenregel ändert, soll sie im Repository geändert werden. Eine zweite, abweichende Finanzlogik im Excel-Generator würde zu inkonsistenten Ergebnissen führen und ist im aktuellen Aufbau gerade nicht vorgesehen.

Code-Fundstelle: repository.py: excel_export_payload(); application/excel_export.py.


## 13. Formelsammlung und Grenzwerte


### 13.1 Schnellreferenz


| Berechnung | Formel / Regel |
| --- | --- |
| Kontoprognose | Ankersaldo + Summe angewendeter Ereignisse |
| Giro-Limitüberschreitung | projected_balance < -limit |
| Rahmenkredit genutzt | max(0, -projected_balance) |
| Rahmenkredit frei | max(0, limit - used) |
| Monatszins Kredit | round_half_up(restsaldo * Sollzins[%] / 1200) |
| Standard-Tilgung | min(max(0, Rate - Zins), Rest - Vertragsrest) |
| Kreditrest | max(0, Anfangssaldo - kumulierte balance_reduction) |
| Darlehensrate automatisch | round(Ursprungsdarlehen * (Sollzins + Tilgung) / 1200) |
| Sondertilgungsrahmen | round_half_up(Ursprungsdarlehen * Sondertilgung[%] / 100) |
| Monatsdelta Konto | Schlussstand - Anfangsstand |
| Operativer Überschuss | Monatseinnahmen - Monatsausgaben |
| Finanzierungseffekt | Liquiditätsdelta - operativer Überschuss |
| Matching-Toleranz | max(1 EUR, min(5 EUR, 5 % des Planbetrags)) |


### 13.2 Harte Grenzen


| Bereich | Grenze |
| --- | --- |
| Kredit-Zahlungsanzahl | 1 bis 1.200 |
| Umbuchungs-Anzahl | 1 bis 1.200 |
| Liquiditätsvorschau | 1 bis 12 Monate |
| Konten in Simulation / Liquiditätsvorschau | höchstens 4 |
| Excel-Prognose | höchstens 24 Monate |
| Kleine Abschlussrestschuld | < 300 Cent |
| Bankmatching Datumsabstand | <= 7 Tage; Auto-Vorschlag <= 3 Tage |
| Bankmatching Betragsabweichung | 1 bis 5 EUR Toleranzrahmen, aber Auto-Vorschlag nur bei exakt 0 Abweichung |


## 14. Implementierungsgrenzen und bekannte Besonderheiten


> 1. Effektiver Jahreszins\
> effective_interest_rate wird bei Darlehen gespeichert und angezeigt, treibt aber nicht die Tilgungssimulation. Dafür wird der nominale Sollzins interest_rate verwendet.


> 2. Dispozinsen Girokonto\
> Es existiert kein automatisches Dispozinsmodell. Das Legacy-APR-Feld wird auf 0 gehalten; Girokonto-Zinsen werden als einzelne Ausgaben der Kategorie interest erfasst.


> 3. Sondertilgungsprozentsatz\
> Der jährliche Betrag wird aus dem ursprünglichen Darlehen berechnet. Eine harte jährliche Summenprüfung manueller Sondertilgungen ist im geprüften 2.3.0-Code nicht implementiert.


> 4. Rahmenkredit-Hinweis bei Serien\
> Die UI zeigt den Rahmen am ersten gewählten Fälligkeitstag. Die endgültige Speichervalidierung prüft jede einzelne Ausführung der Serie und kann eine spätere Ausführung ablehnen.


> 5. UI-Vorschläge sind keine Kontenwahrheit\
> Raten-, Anzahl- und Restschuldvorschläge im Browser sind Komfortfunktionen. Persistierte Konten- und Kreditstände werden durch das Backend und die gespeicherten Ereignisse bestimmt.


> 6. Kontoauszugssaldo gewinnt\
> Ein bestätigter statement-Anker kann eine vorherige Planprognose ab diesem Datum ersetzen. Das ist beabsichtigt: reale Bankwahrheit korrigiert die Planung.


### 14.1 Empfohlene Regressionstests bei Rechenänderungen

31.-Rhythmus über Februar prüfen: 31.01. -> 28./29.02. -> 31.03.

Normale Ausgabe am Wochenende -> Freitag; Nicht-Darlehens-Kreditrate -> Montag.

Rahmenkredit-Einzelauszahlung auf zukünftig freien Rahmen testen.

Rahmenkredit-Serie testen, bei der erst eine spätere Ausführung das Limit überschreitet.

Standardkredit mit bekanntem Sollzins: Zins, Tilgung und Restschuld über mehrere Raten verifizieren.

Konsumfinanzierung mit vorzeitiger Sondertilgung: zukünftige Finanzierungskosten dürfen keinen Phantom-Rest erzeugen.

Darlehen: automatische Rate, manuelle Rate und Restschuld bis Zinsbindungsende vergleichen.

Kontoauszug mit exaktem Treffer, toleriertem Treffer, mehrdeutigem Treffer und unbekannter Abbuchung importieren.

Monatsvorschau vor/nach Reconciliation-Anker vergleichen.

Excel-Export gegen dieselbe Monatsvorschau in der API vergleichen.

Erledigte Bewegung mit Betrags-Override prüfen: Der Override muss „Operativ frei“ verändern; bei bereits erledigter Bewegung darf die Liquiditätsprojektion dadurch nicht nochmals verändert werden.

Dashboard-Monatsauswahl prüfen: Select, Zurück/Vor und „Aktueller Monat“ müssen den angeforderten Dashboard-Monat laden; die API-Monatszuordnung muss dem gewählten Monat entsprechen.


## 15. Code-Quellenverzeichnis

Die folgende Zuordnung dient als Wartungsindex. Bei einer späteren Version sollte zuerst geprüft werden, ob sich diese Funktionen fachlich geändert haben.


| Datei | Relevante Funktionen / Bereiche |
| --- | --- |
| app/domain/recurrence.py | add_months_anchored; last_occurrence_date; recurrence_dates; planned_booking_dates |
| app/domain/simulation.py | simulate_daily; transfer_events |
| app/infrastructure/repository.py | inferred_nominal_apr; credit_values; _credit_timelines; list_credits; list_interest |
| app/infrastructure/repository.py | cash_flow_values; transfer_values; household_detail; projected_account_balances |
| app/infrastructure/repository.py | simulation_dashboard; monthly_preview; liquidity_outlook; dashboard |
| app/infrastructure/repository.py | EnergyLab-Normalisierung, Ist-Zahlungen, Billing-Snapshots |
| app/infrastructure/repository.py | Kontoauszug Matching und Reconciliation |
| app/static/app.js | euroCents; Rahmenkredit-Hinweis; Darlehensrate und Restschuldvorschau |
| app/static/credit-archive.js | Konsumkredit-Eingabehilfen; Zinsanzeige; Kreditformular |
| app/archive_support.py | automatische/manuelle Kreditarchivierung; Kreditfilter |
| app/application/excel_export.py | XLSX-Darstellung der Backend-Prognosen |


### 15.1 Versionsnotiz

Dokumentiert ist der dokumentierte Anwendungssnapshot FinanzLab 2.3.0 vom 5. Oktober 2026. Gegenüber 2.2.2 wurde die Dashboard-Monatsauswahl auf ein echtes Select umgestellt; die fachliche Backend-Rechenlogik blieb unverändert. Vor der Produktivfreigabe wurden Dashboard-Invarianten über 24 Monate, Monatsvorschau-Smokes sowie die Override-/Erledigt-Regeln mit einer Kopie der Produktionsdaten geprüft. Änderungen nach diesem Snapshot sind nicht automatisch Bestandteil dieses Dokuments.


## 16. Erweiterungen in Version 2.4.0

### 16.1 Kontostand-Historie

Im Kontobearbeitungsdialog zeigt `app/static/app.js` die neuesten fünf Einträge unmittelbar an. Ältere Einträge werden in aufklappbaren Monatsgruppen dargestellt. Die Darstellung beeinflusst weder die vorhandenen Salden in SQLite noch die Projektion oder den Excel-Export.

### 16.2 Personenverwaltung

Die Tabelle `persons` enthält beständige Personen-IDs. Die frühere Slot-Beschränkung `CHECK(slot IN ('A','B'))` wird für bestehende Datenbanken vor der regulären Schemainitialisierung in einer transaktionalen Migration entfernt (`Repository._migrate_person_slots`). Die IDs bleiben bestehen; die Migration prüft referenzielle Integrität.

Die API stellt `POST /api/persons`, `PUT /api/persons/{id}` und `DELETE /api/persons/{id}` bereit. Das Frontend bietet einen Dialog zum Hinzufügen, Umbenennen und Löschen. Löschen ist bei noch bestehenden Konto-/Cashflow-Zuordnungen, einschließlich historischer Versionen, gesperrt; mindestens eine Person muss im Haushalt verbleiben.

Neue Personen verwenden stabile, eindeutige Slots; alte Slots A/B bleiben kompatibel. Die Konten- und Cashflow-Auswahl erfolgt über die aktuelle Personenliste, sodass mehr als zwei Personen unterstützt werden.

### 16.3 Update und Rückfall

Beim Start legt die Anwendung bei einem vorhandenen Datenbestand vor der Versionsmigration eine konsistente SQLite-Sicherung an, sofern noch kein Update-Marker für 2.4.0 vorhanden ist. Für einen Rückfall auf 2.3.0 ist das Vor-Update-Datenbankschema zu berücksichtigen. Niemals rückwärts in eine bereits migrierte Datenbank schreiben, ohne vorherige Prüfung und passende Sicherung.

### 16.4 Sicherheit bei öffentlicher Bereitstellung

FinanzLab hat keine integrierte Benutzeranmeldung. Der HTTP-Port darf nicht ungeschützt öffentlich zugänglich sein. Reale `planner.db`-Dateien, Kontoauszüge, Abrechnungen, Zugriffs-/API-Schlüssel, Exportdateien und lokale Konfigurationen gehören nicht in die Versionsverwaltung.
