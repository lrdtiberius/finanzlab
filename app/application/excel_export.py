from dataclasses import dataclass
from datetime import date, datetime, timezone
from io import BytesIO
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile


CATEGORY_LABELS = {
    "salary": "Gehalt", "pension": "Rente", "benefit": "Leistung",
    "family": "Familie", "other_income": "Sonstige Einnahme",
    "housing": "Wohnen", "energy": "Energie", "insurance": "Versicherung",
    "food": "Lebensmittel", "mobility": "Mobilität", "consumer_credit": "Konsumkredit",
    "credit": "Kredit", "borrowed": "Geliehen",
    "leisure": "Freizeit", "other_expense": "Sonstige Ausgabe", "other": "Sonstiges",
}
RECURRENCE_LABELS = {
    "weekly": "Wöchentlich", "monthly": "Monatlich", "quarterly": "Vierteljährlich",
    "semiannual": "Halbjährlich", "yearly": "Jährlich", "once": "Einmalig",
}
MOVEMENT_LABELS = {
    "income": "Einnahme", "expense": "Ausgabe",
    "transfer_in": "Umbuchung Eingang", "transfer_out": "Umbuchung Ausgang",
}
LIFECYCLE_LABELS = {"current": "Aktuell", "upcoming": "Zukünftig", "ended": "Beendet"}
CREDIT_TYPE_LABELS = {"consumer_credit": "Konsumkredit", "credit": "Kredit", "borrowed": "Geliehen"}


@dataclass(frozen=True)
class Column:
    key: str
    title: str
    kind: str = "text"
    width: float = 16


@dataclass(frozen=True)
class FormulaValue:
    formula: str
    cached: object
    kind: str = "number"


@dataclass(frozen=True)
class StyledValue:
    value: object
    kind: str = "text"
    style: str | None = None


@dataclass
class TableSheet:
    name: str
    title: str
    description: str
    columns: list[Column]
    records: list[dict]


def euro(cents):
    return None if cents is None else int(cents) / 100


def yes_no(value):
    return "Ja" if value else "Nein"


def month_date(value):
    return f"{value}-01" if value else None


def _owner_name(account, people):
    if account.get("owner_scope") == "joint":
        return "Gemeinsam"
    return people.get(account.get("owner_person_id"), "Nicht zugeordnet")


def build_forecast_workbook(payload):
    """Build a styled, dependency-free XLSX workbook as bytes."""
    household = payload["household"]
    people = {item["id"]: item["display_name"] for item in household["persons"]}
    last_account_month = {
        item["account_id"]: item for item in payload["account_months"]
        if item["month"] == payload["through_month"]
    }

    months = [{
        "month": month_date(item["month"]), "from": item["from"], "through": item["through"],
        "opening": euro(item["opening_balance_cents"]), "income": euro(item["income_cents"]),
        "expense": euro(item["expense_cents"]), "transfers": euro(item["transfer_volume_cents"]),
        "delta": euro(item["delta_cents"]), "closing": euro(item["closing_balance_cents"]),
        "warnings": item["warning_count"],
    } for item in payload["months"]]

    account_months = [{
        "month": month_date(item["month"]), "account": item["account_name"],
        "opening": euro(item["opening_balance_cents"]), "change": euro(item["month_delta_cents"]),
        "closing": euro(item["closing_balance_cents"]), "minimum": euro(item["minimum_balance_cents"]),
        "overdraft": euro(item["overdraft_limit_cents"]),
        "exceeded": yes_no(item["overdraft_exceeded"]), "overage": euro(item["overdraft_overage_cents"]),
    } for item in payload["account_months"]]

    days = [{
        "date": item["date"], "account": item["account_name"],
        "balance": euro(item["projected_balance_cents"]),
        "overdraft": euro(item["overdraft_limit_cents"]),
        "overage": euro(item["overdraft_overage_cents"]),
        "status": StyledValue("Dispo überschritten", style="warning") if item["overdraft_exceeded"] else "Im Rahmen",
    } for item in payload["days"]]

    movements = [{
        "date": item["date"], "kind": MOVEMENT_LABELS.get(item.get("kind"), item.get("kind") or "Bewegung"),
        "label": item.get("label") or "Ohne Bezeichnung", "account": item["account_name"],
        "amount": euro(item.get("amount_cents")),
        "applied": yes_no(item.get("applied_to_projection", True)),
        "completed": yes_no(item.get("completed", False)),
        "origin": "Gebucht" if item.get("origin") == "actual" else ("Umbuchung" if item.get("origin") == "transfer" else "Geplant"),
        "note": ("Entfällt – Kredit bereits getilgt" if item.get("skip_reason") == "credit_repaid"
                 else (f"Restbetrag {euro(item.get('final_residual_added_cents')):.2f} € in Schlussrate enthalten"
                       if item.get("final_residual_added_cents")
                       else (f"Auf Restschuld begrenzt; ursprünglich {euro(item.get('planned_amount_cents')):.2f} €"
                             if item.get("credit_adjusted") else ""))),
    } for item in payload["movements"]]

    accounts = []
    for item in payload["accounts"]:
        forecast = last_account_month.get(item["id"], {})
        warning = bool(forecast.get("overdraft_exceeded"))
        accounts.append({
            "name": item["name"], "owner": _owner_name(item, people), "default": yes_no(item.get("is_default")),
            "balance": euro(item.get("balance_cents")), "anchor_date": item.get("anchor_date"),
            "bookings": "Tagesbuchungen enthalten" if item.get("bookings_applied") else "Tagesbuchungen noch berechnen",
            "overdraft": euro(item.get("overdraft_limit_cents")), "forecast": euro(forecast.get("closing_balance_cents")),
            "status": StyledValue("Dispo überschritten", style="warning") if warning else "Im Rahmen",
        })

    def flow_record(item, expense=False):
        return {
            "name": item.get("name") or "Ohne Bezeichnung",
            "category": CATEGORY_LABELS.get(item.get("category"), item.get("category") or "Sonstiges"),
            "amount": -euro(item.get("amount_cents")) if expense else euro(item.get("amount_cents")),
            "recurrence": RECURRENCE_LABELS.get(item.get("recurrence"), item.get("recurrence") or ""),
            "due_date": item.get("due_date"), "end_date": item.get("end_date") if expense else None,
            "duration": item.get("duration_months") if expense else None,
            "account": item.get("account_name") or "Nicht zugeordnet",
            "owner": item.get("owner_name") or "Nicht zugeordnet",
            "active": yes_no(item.get("configured_active")),
            "status": LIFECYCLE_LABELS.get(item.get("lifecycle_status"), item.get("lifecycle_status") or ""),
            "version_from": item.get("version_from"),
            "credit": item.get("credit_name") if expense else None,
            "credit_reduction": euro(item.get("credit_reduction_cents")) if expense and item.get("credit_id") else None,
        }

    incomes = [flow_record(item) for item in payload["incomes"]]
    expenses = [flow_record(item, True) for item in payload["expenses"]]
    transfers = [{
        "name": item["name"], "source": item["source_account_name"], "target": item["target_account_name"],
        "amount": euro(item["amount_cents"]),
        "recurrence": RECURRENCE_LABELS.get(item.get("recurrence"), item.get("recurrence") or ""),
        "due_date": item.get("due_date"), "end_date": item.get("end_date"),
        "count": item.get("occurrence_count"), "active": yes_no(item.get("active")),
    } for item in payload["transfers"]]
    history = [{
        "account": item["account_name"], "date": item["anchor_date"], "balance": euro(item["balance_cents"]),
        "bookings": "Tagesbuchungen enthalten" if item.get("bookings_applied") else "Tagesbuchungen noch berechnen",
        "source": "Manuell" if item.get("source") == "manual" else "Historischer Altbestand",
        "created": item.get("created_at"),
    } for item in payload["balance_history"]]
    credits = [{
        "name": item["name"], "type": CREDIT_TYPE_LABELS.get(item["credit_type"], item["credit_type"]),
        "opening": euro(item["opening_balance_cents"]), "paid": euro(item["paid_cents"]),
        "remaining": euro(item["remaining_balance_cents"]), "future": euro(item["future_payment_cents"]),
        "note": item.get("note") or "",
    } for item in payload.get("credits", [])]
    credit_payments = [{
        "credit": item["credit_name"], "type": CREDIT_TYPE_LABELS.get(item["credit_type"], item["credit_type"]),
        "date": item["date"], "planned": euro(item.get("planned_amount_cents")),
        "amount": euro(item.get("effective_reduction_cents")),
        "account_amount": euro(item.get("account_amount_cents")) if item["source"] == "expense" else None,
        "source": "Verknüpfte Ausgabe" if item["source"] == "expense" else "Manuell",
        "label": item["label"],
        "status": ("Entfällt – Kredit bereits getilgt" if item.get("skipped")
                   else (StyledValue(
                            f"Restbetrag {euro(item.get('final_residual_added_cents')):.2f} € zugeschlagen",
                            style="warning") if item.get("final_residual_added_cents")
                         else (StyledValue("Auf Restschuld begrenzt", style="warning") if item.get("adjusted")
                               else (StyledValue("Zukünftig – noch nicht saldowirksam", style="warning")
                                     if item.get("future") else "Im Saldo berücksichtigt")))),
    } for item in payload.get("credit_payments", [])]
    credit_months = [{
        "month": month_date(item["month"]), "credit": item["credit_name"],
        "type": CREDIT_TYPE_LABELS.get(item["credit_type"], item["credit_type"]),
        "opening": euro(item["opening_balance_cents"]), "reduction": euro(item["reduction_cents"]),
        "closing": euro(item["closing_balance_cents"]),
    } for item in payload.get("credit_months", [])]

    month_last_row = 4 + len(months)
    count_formula = lambda sheet_name, count: (f"COUNTA('{sheet_name}'!A5:A{4 + count})" if count else "0")
    overview = [
        {"area": "Export", "metric": "Haushalt", "value": household["name"], "note": "Aktiver Haushalt"},
        {"area": "Export", "metric": "Zeitraum von", "value": StyledValue(payload["from_date"], "date"), "note": "Erster Prognosetag"},
        {"area": "Export", "metric": "Zeitraum bis", "value": StyledValue(payload["through_date"], "date"), "note": "Letzter Prognosetag"},
        {"area": "Bestand", "metric": "Konten", "value": FormulaValue(count_formula("Konten", len(accounts)), len(accounts), "integer"), "note": "Alle Konten"},
        {"area": "Bestand", "metric": "Einnahmen", "value": FormulaValue(count_formula("Einnahmen", len(incomes)), len(incomes), "integer"), "note": "Aktiv, inaktiv, zukünftig und beendet"},
        {"area": "Bestand", "metric": "Ausgaben", "value": FormulaValue(count_formula("Ausgaben", len(expenses)), len(expenses), "integer"), "note": "Aktiv, inaktiv, zukünftig und beendet"},
        {"area": "Bestand", "metric": "Umbuchungen", "value": FormulaValue(count_formula("Umbuchungen", len(transfers)), len(transfers), "integer"), "note": "Alle angelegten Umbuchungen"},
        {"area": "Bestand", "metric": "Kredite", "value": FormulaValue(count_formula("Kredite", len(credits)), len(credits), "integer"), "note": "Konsumkredite, Kredite und Geliehen"},
        {"area": "Bestand", "metric": "Offener Kreditsaldo", "value": FormulaValue(f"SUM('Kredite'!E5:E{4 + len(credits)})" if credits else "0", sum(item["remaining"] or 0 for item in credits), "currency"), "note": "Zukünftige Tilgungen sind noch nicht abgezogen"},
        {"area": "Vorschau", "metric": "Monate", "value": StyledValue(payload["month_count"], "integer"), "note": "Tagesgenau simuliert"},
        {"area": "Vorschau", "metric": "Einnahmen gesamt", "value": FormulaValue(f"SUM('Monatsvorschau'!E5:E{month_last_row})", sum(item["income"] or 0 for item in months), "currency"), "note": "Fälligkeiten im Exportzeitraum"},
        {"area": "Vorschau", "metric": "Ausgaben gesamt", "value": FormulaValue(f"SUM('Monatsvorschau'!F5:F{month_last_row})", sum(item["expense"] or 0 for item in months), "currency"), "note": "Fälligkeiten im Exportzeitraum"},
        {"area": "Vorschau", "metric": "Endstand", "value": FormulaValue(f"'Monatsvorschau'!I{month_last_row}", months[-1]["closing"] if months else 0, "currency"), "note": f"Stand zum {payload['through_date']}"},
        {"area": "Hinweis", "metric": "Berechnungsbasis", "value": "Historisierte Kontostände", "note": "Nur tatsächlich fällige Positionen; Tagesbuchungs-Checkbox wird beachtet"},
    ]

    sheets = [
        TableSheet("Übersicht", "Haushaltsplaner – Excel-Export", "Strukturierter Überblick über Stammdaten und die tagesgenaue Vorschau.", [
            Column("area", "Bereich", width=15), Column("metric", "Kennzahl", width=24),
            Column("value", "Wert", width=24), Column("note", "Erläuterung", width=58),
        ], overview),
        TableSheet("Monatsvorschau", "Monatsvorschau", "Haushaltsweite Summen aus allen tatsächlichen Fälligkeiten des jeweiligen Monats.", [
            Column("month", "Monat", "month", 17), Column("from", "Von", "date", 13), Column("through", "Bis", "date", 13),
            Column("opening", "Anfangsstand", "currency", 18), Column("income", "Einnahmen", "currency", 17),
            Column("expense", "Ausgaben", "currency", 17), Column("transfers", "Umbuchungsvolumen", "currency", 20),
            Column("delta", "Veränderung", "currency", 17), Column("closing", "Endstand", "currency", 18),
            Column("warnings", "Dispowarnungen", "integer", 16),
        ], months),
        TableSheet("Kontovorschau", "Monatliche Kontovorschau", "Anfang, Veränderung, Ende und niedrigster Stand je Konto und Monat.", [
            Column("month", "Monat", "month", 17), Column("account", "Konto", width=25),
            Column("opening", "Anfangsstand", "currency", 18), Column("change", "Veränderung", "currency", 17),
            Column("closing", "Endstand", "currency", 18), Column("minimum", "Niedrigster Stand", "currency", 20),
            Column("overdraft", "Disporahmen", "currency", 17), Column("exceeded", "Dispo überschritten", width=19),
            Column("overage", "Überschreitung", "currency", 18),
        ], account_months),
        TableSheet("Tagesvorschau", "Tagesvorschau", "Simulierter Kontostand für jeden Tag und jedes Konto im Exportzeitraum.", [
            Column("date", "Datum", "date", 13), Column("account", "Konto", width=25),
            Column("balance", "Simulierter Kontostand", "currency", 22), Column("overdraft", "Disporahmen", "currency", 17),
            Column("overage", "Überschreitung", "currency", 18), Column("status", "Status", width=22),
        ], days),
        TableSheet("Bewegungen", "Prognostizierte Bewegungen", "Alle geplanten, erledigten und gebuchten Bewegungen im gewählten Zeitraum.", [
            Column("date", "Datum", "date", 13), Column("kind", "Art", width=21), Column("label", "Bezeichnung", width=34),
            Column("account", "Konto", width=25), Column("amount", "Betrag", "currency", 17),
            Column("applied", "Eingerechnet", width=15), Column("completed", "Vorgang erledigt", width=18),
            Column("origin", "Quelle", width=15), Column("note", "Berechnungshinweis", width=40),
        ], movements),
        TableSheet("Konten", "Konten", f"Kontostände und Prognosewerte zum Ende des Exportzeitraums ({payload['through_date']}).", [
            Column("name", "Kontoname", width=25), Column("owner", "Besitzer", width=21), Column("default", "Standardkonto", width=16),
            Column("balance", "Gespeicherter Stand", "currency", 21), Column("anchor_date", "Stand vom", "date", 13),
            Column("bookings", "Tagesbuchungen", width=29), Column("overdraft", "Disporahmen", "currency", 17),
            Column("forecast", "Vorschau Endstand", "currency", 21), Column("status", "Status", width=22),
        ], accounts),
        TableSheet("Einnahmen", "Alle Einnahmen", "Alle eingegebenen Einnahmen – unabhängig vom aktuellen Aktivitätsstatus.", [
            Column("name", "Bezeichnung", width=30), Column("category", "Art", width=21), Column("amount", "Betrag", "currency", 17),
            Column("recurrence", "Rhythmus", width=17), Column("due_date", "Erste / nächste Fälligkeit", "date", 22),
            Column("account", "Konto", width=24), Column("owner", "Zuordnung", width=20), Column("active", "Berücksichtigen", width=16),
            Column("status", "Lebenszyklus", width=16), Column("version_from", "Konfiguration ab", "date", 17),
        ], incomes),
        TableSheet("Ausgaben", "Alle Ausgaben", "Alle eingegebenen Ausgaben – einschließlich Kredit, Enddatum und Dauer.", [
            Column("name", "Bezeichnung", width=30), Column("category", "Art", width=21), Column("amount", "Betrag", "currency", 17),
            Column("recurrence", "Rhythmus", width=17), Column("due_date", "Erste / nächste Fälligkeit", "date", 22),
            Column("end_date", "Enddatum inkl.", "date", 17), Column("duration", "Dauer Monate", "integer", 15),
            Column("credit", "Verknüpfter Kredit", width=27), Column("credit_reduction", "Davon Tilgung", "currency", 18),
            Column("account", "Konto", width=24), Column("owner", "Zuordnung", width=20), Column("active", "Berücksichtigen", width=16),
            Column("status", "Lebenszyklus", width=16), Column("version_from", "Konfiguration ab", "date", 17),
        ], expenses),
        TableSheet("Kredite", "Kredite", "Alle Kreditstammdaten mit dem heute wirksamen offenen Saldo.", [
            Column("name", "Bezeichnung", width=30), Column("type", "Art", width=19),
            Column("opening", "Anfangssaldo", "currency", 18), Column("paid", "Bisher getilgt", "currency", 18),
            Column("remaining", "Offener Saldo", "currency", 18), Column("future", "Zukünftige Tilgung", "currency", 20),
            Column("note", "Notiz", width=42),
        ], credits),
        TableSheet("Kreditzahlungen", "Kredit-Historie", "Manuelle und durch Ausgaben geplante Tilgungen. Zukünftige Zahlungen sind noch nicht saldowirksam.", [
            Column("credit", "Kredit", width=29), Column("type", "Art", width=19), Column("date", "Datum", "date", 13),
            Column("planned", "Geplante Tilgung", "currency", 19), Column("amount", "Wirksame Tilgung", "currency", 19),
            Column("account_amount", "Wirksame Kontobelastung", "currency", 24), Column("source", "Quelle", width=22),
            Column("label", "Bezeichnung / Notiz", width=38), Column("status", "Status", width=33),
        ], credit_payments),
        TableSheet("Kreditvorschau", "Monatliche Kreditvorschau", "Separat simulierte Kreditstände; sie verändern niemals die Kontensumme.", [
            Column("month", "Monat", "month", 17), Column("credit", "Kredit", width=29), Column("type", "Art", width=19),
            Column("opening", "Anfangssaldo", "currency", 18), Column("reduction", "Tilgung im Monat", "currency", 19),
            Column("closing", "Endsaldo", "currency", 18),
        ], credit_months),
        TableSheet("Umbuchungen", "Alle Umbuchungen", "Quell- und Zielkonto sowie die optionalen Begrenzungen Ende und Anzahl.", [
            Column("name", "Bezeichnung", width=28), Column("source", "Von Konto", width=24), Column("target", "An Konto", width=24),
            Column("amount", "Betrag", "currency", 17), Column("recurrence", "Rhythmus", width=17),
            Column("due_date", "Erste Fälligkeit", "date", 17), Column("end_date", "Ende inkl.", "date", 15),
            Column("count", "Anzahl", "integer", 12), Column("active", "Berücksichtigen", width=16),
        ], transfers),
        TableSheet("Kontostand-Historie", "Kontostand-Historie", "Alle gespeicherten Kontostände als nachvollziehbare Berechnungsbasis.", [
            Column("account", "Konto", width=25), Column("date", "Stand vom", "date", 13), Column("balance", "Kontostand", "currency", 18),
            Column("bookings", "Tagesbuchungen", width=29), Column("source", "Quelle", width=22), Column("created", "Erfasst am", "datetime", 21),
        ], history),
    ]
    return _write_xlsx(sheets, payload)


STYLE_IDS = {"default": 0, "title": 1, "subtitle": 2, "header": 3, "text": 4,
             "date": 5, "currency": 6, "integer": 7, "boolean": 8, "warning": 9,
             "accent": 10, "month": 11, "datetime": 12}


def _column_name(index):
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _excel_date(value):
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time())
    else:
        text = str(value or "").replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            parsed = datetime.combine(date.fromisoformat(text[:10]), datetime.min.time())
    if parsed.tzinfo:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    epoch = datetime(1899, 12, 30)
    return (parsed - epoch).total_seconds() / 86400


def _cell_xml(reference, value, kind="text", style=None):
    if isinstance(value, StyledValue):
        kind, style, value = value.kind, value.style or style, value.value
    formula = None
    if isinstance(value, FormulaValue):
        formula, kind, value = value.formula, value.kind, value.cached
    style_name = style or kind if (style or kind) in STYLE_IDS else "text"
    style_id = STYLE_IDS[style_name]
    if value is None or value == "":
        return f'<c r="{reference}" s="{style_id}"/>'
    if kind in ("date", "month", "datetime"):
        numeric = _excel_date(value)
        body = f"<v>{numeric:.10f}</v>"
    elif kind in ("currency", "number", "integer") and not isinstance(value, bool):
        body = f"<v>{float(value):.10f}</v>" if kind != "integer" else f"<v>{int(value)}</v>"
    elif kind == "boolean" or isinstance(value, bool):
        body = f"<v>{1 if value else 0}</v>"
        return f'<c r="{reference}" s="{style_id}" t="b">{body}</c>'
    else:
        text = escape(str(value))
        body = f'<is><t xml:space="preserve">{text}</t></is>'
        return f'<c r="{reference}" s="{style_id}" t="inlineStr">{body}</c>'
    formula_xml = f"<f>{escape(formula)}</f>" if formula else ""
    return f'<c r="{reference}" s="{style_id}">{formula_xml}{body}</c>'


def _worksheet_xml(sheet):
    last_column = _column_name(len(sheet.columns))
    last_row = 4 + max(1, len(sheet.records))
    rows = []
    title_cells = [_cell_xml("A1", sheet.title, style="title")]
    subtitle_cells = [_cell_xml("A2", sheet.description, style="subtitle")]
    rows.append(f'<row r="1" ht="30" customHeight="1">{"".join(title_cells)}</row>')
    rows.append(f'<row r="2" ht="24" customHeight="1">{"".join(subtitle_cells)}</row>')
    headers = [_cell_xml(f"{_column_name(i)}4", column.title, style="header") for i, column in enumerate(sheet.columns, 1)]
    rows.append(f'<row r="4" ht="25" customHeight="1">{"".join(headers)}</row>')
    if sheet.records:
        for row_number, record in enumerate(sheet.records, 5):
            cells = []
            for column_number, column in enumerate(sheet.columns, 1):
                value = record.get(column.key)
                style = "warning" if isinstance(value, StyledValue) and value.style == "warning" else None
                cells.append(_cell_xml(f"{_column_name(column_number)}{row_number}", value, column.kind, style))
            rows.append(f'<row r="{row_number}" ht="20" customHeight="1">{"".join(cells)}</row>')
    else:
        rows.append(f'<row r="5" ht="22" customHeight="1">{_cell_xml("A5", "Keine Daten vorhanden", style="text")}</row>')
    columns = "".join(f'<col min="{i}" max="{i}" width="{column.width}" customWidth="1"/>' for i, column in enumerate(sheet.columns, 1))
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<dimension ref="A1:{last_column}{last_row}"/>
<sheetViews><sheetView showGridLines="0" workbookViewId="0"><pane ySplit="4" topLeftCell="A5" activePane="bottomLeft" state="frozen"/><selection pane="bottomLeft" activeCell="A5" sqref="A5"/></sheetView></sheetViews>
<sheetFormatPr defaultRowHeight="18"/><cols>{columns}</cols><sheetData>{''.join(rows)}</sheetData>
<autoFilter ref="A4:{last_column}{last_row}"/><mergeCells count="2"><mergeCell ref="A1:{last_column}1"/><mergeCell ref="A2:{last_column}2"/></mergeCells>
<pageMargins left="0.3" right="0.3" top="0.6" bottom="0.6" header="0.2" footer="0.2"/>
<pageSetup orientation="landscape" fitToWidth="1" fitToHeight="0"/>
</worksheet>'''


def _styles_xml():
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="2"><numFmt numFmtId="164" formatCode="#,##0.00 &quot;€&quot;;[Red]-#,##0.00 &quot;€&quot;;-"/><numFmt numFmtId="166" formatCode="mmmm yyyy"/></numFmts>
<fonts count="4"><font><sz val="11"/><color rgb="FF17342F"/><name val="Aptos"/><family val="2"/></font><font><b/><sz val="18"/><color rgb="FFFFFFFF"/><name val="Aptos Display"/></font><font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Aptos"/></font><font><b/><sz val="11"/><color rgb="FFB34338"/><name val="Aptos"/></font></fonts>
<fills count="7"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF17342F"/><bgColor indexed="64"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFE8F2ED"/><bgColor indexed="64"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFF7E9DE"/><bgColor indexed="64"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFF9E8E4"/><bgColor indexed="64"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFCF6B38"/><bgColor indexed="64"/></patternFill></fill></fills>
<borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border><border><left/><right/><top/><bottom style="thin"><color rgb="FFE1DACE"/></bottom><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="13"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment vertical="center"/></xf><xf numFmtId="0" fontId="0" fillId="3" borderId="0" xfId="0" applyFill="1" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf><xf numFmtId="0" fontId="2" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf><xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf><xf numFmtId="14" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1" applyAlignment="1"><alignment vertical="center"/></xf><xf numFmtId="164" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1" applyAlignment="1"><alignment horizontal="right" vertical="center"/></xf><xf numFmtId="3" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1" applyAlignment="1"><alignment horizontal="right" vertical="center"/></xf><xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf><xf numFmtId="0" fontId="3" fillId="5" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf><xf numFmtId="0" fontId="2" fillId="6" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/><xf numFmtId="166" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1"/><xf numFmtId="22" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1"/></cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles><dxfs count="0"/><tableStyles count="0" defaultTableStyle="TableStyleMedium2" defaultPivotStyle="PivotStyleLight16"/>
</styleSheet>'''


def _write_xlsx(sheets, payload):
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        sheet_overrides = "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1, len(sheets) + 1))
        archive.writestr("[Content_Types].xml", f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>{sheet_overrides}<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/><Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/></Types>''')
        archive.writestr("_rels/.rels", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>''')
        sheets_xml = "".join(f'<sheet name="{escape(sheet.name)}" sheetId="{i}" r:id="rId{i}"/>' for i, sheet in enumerate(sheets, 1))
        archive.writestr("xl/workbook.xml", f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><bookViews><workbookView xWindow="0" yWindow="0" windowWidth="24000" windowHeight="15000"/></bookViews><sheets>{sheets_xml}</sheets><calcPr calcId="191029" fullCalcOnLoad="1" forceFullCalc="1"/></workbook>''')
        rels = "".join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1, len(sheets) + 1))
        archive.writestr("xl/_rels/workbook.xml.rels", f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{rels}<Relationship Id="rId{len(sheets)+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>''')
        archive.writestr("xl/styles.xml", _styles_xml())
        for index, sheet in enumerate(sheets, 1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", _worksheet_xml(sheet))
        titles = "".join(f"<vt:lpstr>{escape(sheet.name)}</vt:lpstr>" for sheet in sheets)
        archive.writestr("docProps/app.xml", f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>Haushaltsplaner</Application><DocSecurity>0</DocSecurity><ScaleCrop>false</ScaleCrop><HeadingPairs><vt:vector size="2" baseType="variant"><vt:variant><vt:lpstr>Arbeitsblätter</vt:lpstr></vt:variant><vt:variant><vt:i4>{len(sheets)}</vt:i4></vt:variant></vt:vector></HeadingPairs><TitlesOfParts><vt:vector size="{len(sheets)}" baseType="lpstr">{titles}</vt:vector></TitlesOfParts><Company>Lrd.Tiberius</Company><AppVersion>0.13.4</AppVersion></Properties>''')
        generated = str(payload.get("generated_at") or datetime.now(timezone.utc).isoformat()).replace("+00:00", "Z")
        archive.writestr("docProps/core.xml", f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>Haushaltsplaner Vorschau-Export</dc:title><dc:creator>Lrd.Tiberius</dc:creator><cp:lastModifiedBy>Haushaltsplaner</cp:lastModifiedBy><dcterms:created xsi:type="dcterms:W3CDTF">{escape(generated)}</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">{escape(generated)}</dcterms:modified></cp:coreProperties>''')
    return output.getvalue()
