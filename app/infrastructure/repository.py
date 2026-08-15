import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from threading import RLock
from uuid import uuid4

from app.domain.recurrence import add_months_anchored, recurrence_dates

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS households(
 id TEXT PRIMARY KEY, name TEXT NOT NULL, mode TEXT NOT NULL CHECK(mode IN('single','couple')),
 currency TEXT NOT NULL DEFAULT 'EUR', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS persons(
 id TEXT PRIMARY KEY, household_id TEXT NOT NULL REFERENCES households(id) ON DELETE CASCADE,
 slot TEXT NOT NULL CHECK(slot IN('A','B')), display_name TEXT NOT NULL,
 UNIQUE(household_id,slot));
CREATE TABLE IF NOT EXISTS accounts(
 id TEXT PRIMARY KEY, household_id TEXT NOT NULL REFERENCES households(id) ON DELETE CASCADE,
 name TEXT NOT NULL, owner_scope TEXT NOT NULL, owner_person_id TEXT REFERENCES persons(id),
 kind TEXT NOT NULL DEFAULT 'checking', currency TEXT NOT NULL DEFAULT 'EUR',
 overdraft_limit_cents INTEGER, overdraft_apr TEXT, is_default INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(household_id,name));
CREATE TABLE IF NOT EXISTS account_versions(
 id TEXT PRIMARY KEY, household_id TEXT NOT NULL REFERENCES households(id) ON DELETE CASCADE,
 account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
 name TEXT NOT NULL, owner_scope TEXT NOT NULL, owner_person_id TEXT REFERENCES persons(id),
 overdraft_limit_cents INTEGER NOT NULL, overdraft_apr TEXT NOT NULL,
 valid_from TEXT NOT NULL, valid_to TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS account_versions_current ON account_versions(account_id) WHERE valid_to IS NULL;
CREATE TABLE IF NOT EXISTS balance_anchors(
 id TEXT PRIMARY KEY, household_id TEXT NOT NULL REFERENCES households(id) ON DELETE CASCADE,
 account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE, anchor_date TEXT NOT NULL,
 balance_cents INTEGER NOT NULL, bookings_applied INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(account_id,anchor_date));
CREATE TABLE IF NOT EXISTS cash_flows(
 id TEXT PRIMARY KEY, household_id TEXT NOT NULL REFERENCES households(id) ON DELETE CASCADE,
 kind TEXT NOT NULL, name TEXT NOT NULL, owner_scope TEXT NOT NULL,
 owner_person_id TEXT REFERENCES persons(id), account_id TEXT REFERENCES accounts(id),
 source_key TEXT, category TEXT NOT NULL DEFAULT 'other', UNIQUE(household_id,source_key));
CREATE TABLE IF NOT EXISTS cash_flow_versions(
 id TEXT PRIMARY KEY, cash_flow_id TEXT NOT NULL REFERENCES cash_flows(id) ON DELETE CASCADE,
 amount_cents INTEGER NOT NULL, active INTEGER NOT NULL, version_from TEXT NOT NULL, version_to TEXT,
 stream_start TEXT, stream_end TEXT, due_date TEXT, source_reference TEXT,
 gross_amount_cents INTEGER, recurrence TEXT NOT NULL DEFAULT 'monthly', name TEXT, category TEXT,
 owner_scope TEXT, owner_person_id TEXT, account_id TEXT);
CREATE TABLE IF NOT EXISTS transfers(
 id TEXT PRIMARY KEY, household_id TEXT NOT NULL REFERENCES households(id) ON DELETE CASCADE,
 name TEXT NOT NULL, source_account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
 target_account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
 amount_cents INTEGER NOT NULL, recurrence TEXT NOT NULL DEFAULT 'once', due_date TEXT NOT NULL,
 end_date TEXT, occurrence_count INTEGER,
 active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS transfers_projection ON transfers(household_id,due_date,active);
CREATE TABLE IF NOT EXISTS schema_migrations(
 name TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS bank_statement_previews(
 id TEXT PRIMARY KEY, household_id TEXT NOT NULL REFERENCES households(id) ON DELETE CASCADE,
 account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
 sha256 TEXT NOT NULL, file_name TEXT NOT NULL, payload TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS bank_statement_imports(
 id TEXT PRIMARY KEY, household_id TEXT NOT NULL REFERENCES households(id) ON DELETE CASCADE,
 account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
 sha256 TEXT NOT NULL, file_name TEXT NOT NULL, period_from TEXT, period_to TEXT,
 closing_balance_cents INTEGER NOT NULL, balance_date TEXT NOT NULL,
 summary TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(account_id,sha256));
CREATE TABLE IF NOT EXISTS bank_transactions(
 id TEXT PRIMARY KEY, household_id TEXT NOT NULL REFERENCES households(id) ON DELETE CASCADE,
 account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
 import_id TEXT NOT NULL REFERENCES bank_statement_imports(id) ON DELETE CASCADE,
 booking_date TEXT NOT NULL, value_date TEXT, amount_cents INTEGER NOT NULL,
 currency TEXT NOT NULL DEFAULT 'EUR', counterparty TEXT, purpose TEXT,
 bank_reference TEXT, fingerprint_base TEXT NOT NULL, occurrence_no INTEGER NOT NULL,
 raw_payload TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(account_id,fingerprint_base,occurrence_no));
CREATE TABLE IF NOT EXISTS bank_transaction_matches(
 id TEXT PRIMARY KEY, transaction_id TEXT NOT NULL UNIQUE REFERENCES bank_transactions(id) ON DELETE CASCADE,
 target_type TEXT NOT NULL CHECK(target_type IN('cash_flow','loan')),
 target_id TEXT NOT NULL, planned_date TEXT NOT NULL, occurrence_key TEXT NOT NULL UNIQUE,
 match_method TEXT NOT NULL, score INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS account_reconciliations(
 id TEXT PRIMARY KEY, household_id TEXT NOT NULL REFERENCES households(id) ON DELETE CASCADE,
 account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
 import_id TEXT NOT NULL REFERENCES bank_statement_imports(id) ON DELETE CASCADE,
 balance_date TEXT NOT NULL, closing_balance_cents INTEGER NOT NULL,
 projected_before_cents INTEGER, delta_cents INTEGER, status TEXT NOT NULL DEFAULT 'active',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS bank_transactions_projection ON bank_transactions(household_id,account_id,booking_date);
CREATE INDEX IF NOT EXISTS account_reconciliations_active ON account_reconciliations(account_id,balance_date,status);
"""

def uid(): return str(uuid4())
def timestamp(): return datetime.now(timezone.utc).isoformat(timespec="microseconds")

def as_of_date(value=None):
    value=str(value or date.today().isoformat())
    try: return date.fromisoformat(value).isoformat()
    except ValueError: raise ValueError("Der Stichtag muss ein gültiges Datum sein.")

def duration_months_between(start_value,end_value):
    if not start_value or not end_value: return None
    try:
        start=date.fromisoformat(str(start_value)); end=date.fromisoformat(str(end_value))
    except ValueError:
        return None
    months=(end.year-start.year)*12+end.month-start.month
    return months if months>0 and add_months_anchored(start,months)==end else None

def overdraft_values(payload):
    try:
        limit=Decimal(str(payload.get("overdraft_limit_cents") if payload.get("overdraft_limit_cents") not in (None,"") else "0"))
    except (InvalidOperation,ValueError):
        raise ValueError("Das Dispolimit muss eine gültige Zahl sein.")
    if not limit.is_finite() or limit!=limit.to_integral_value():
        raise ValueError("Das Dispolimit muss centgenau angegeben werden.")
    if limit<0: raise ValueError("Das Dispolimit darf nicht negativ sein; 0 bedeutet kein Dispo.")
    # The legacy column remains in SQLite for backwards-compatible upgrades,
    # but interest is no longer part of the planning model.
    return int(limit),"0"

class Repository:
    def __init__(self, path=None):
        if path is None:
            data_dir=Path(os.environ.get("DATA_DIR","data")); data_dir.mkdir(parents=True,exist_ok=True); path=data_dir/"planner.db"
        else: Path(path).parent.mkdir(parents=True,exist_ok=True)
        self.path=str(path); self.lock=RLock(); self.initialize()
    @contextmanager
    def connect(self):
        con=sqlite3.connect(self.path); con.row_factory=sqlite3.Row; con.execute("PRAGMA foreign_keys=ON")
        try: yield con; con.commit()
        except Exception: con.rollback(); raise
        finally: con.close()
    def initialize(self):
        with self.lock,self.connect() as con:
            con.executescript(SCHEMA)
            self.ensure_column(con,"cash_flows","category","TEXT NOT NULL DEFAULT 'other'")
            self.ensure_column(con,"cash_flow_versions","gross_amount_cents","INTEGER")
            self.ensure_column(con,"cash_flow_versions","recurrence","TEXT NOT NULL DEFAULT 'monthly'")
            self.ensure_column(con,"cash_flow_versions","name","TEXT")
            self.ensure_column(con,"cash_flow_versions","category","TEXT")
            self.ensure_column(con,"cash_flow_versions","owner_scope","TEXT")
            self.ensure_column(con,"cash_flow_versions","owner_person_id","TEXT")
            self.ensure_column(con,"cash_flow_versions","account_id","TEXT")
            self.ensure_column(con,"accounts","is_default","INTEGER NOT NULL DEFAULT 0")
            self.ensure_column(con,"balance_anchors","created_at","TEXT")
            self.ensure_column(con,"balance_anchors","bookings_applied","INTEGER NOT NULL DEFAULT 1")
            self.ensure_column(con,"transfers","end_date","TEXT")
            self.ensure_column(con,"transfers","occurrence_count","INTEGER")
            con.execute("UPDATE balance_anchors SET created_at=COALESCE(created_at,CURRENT_TIMESTAMP)")
            con.execute("CREATE INDEX IF NOT EXISTS cash_flow_versions_dates ON cash_flow_versions(cash_flow_id,version_from,version_to)")
            migration=con.execute("SELECT 1 FROM schema_migrations WHERE name='v0.11-remove-loans-and-validity'").fetchone()
            if not migration:
                # Imported planning rows remain useful as ordinary income and
                # expenses, but their former Excel origin no longer matters.
                con.execute("UPDATE cash_flows SET source_key=NULL WHERE source_key LIKE 'excel:household-planning:%'")
                con.execute("UPDATE cash_flow_versions SET stream_end=NULL")
                con.execute("DELETE FROM bank_transaction_matches WHERE target_type='loan'")
                for table in (
                    "loan_documents","loan_pdf_previews","loan_csv_previews",
                    "loan_actual_payments","loan_schedule_rows","loan_terms","loans",
                    "private_receivable_events","private_receivables","import_runs","import_previews",
                ):
                    con.execute(f"DROP TABLE IF EXISTS {table}")
                con.execute("INSERT INTO schema_migrations(name) VALUES('v0.11-remove-loans-and-validity')")
            cleanup=con.execute("SELECT 1 FROM schema_migrations WHERE name='v0.11.1-remove-interest-and-gross'").fetchone()
            if not cleanup:
                con.execute("UPDATE accounts SET overdraft_apr='0'")
                con.execute("UPDATE account_versions SET overdraft_apr='0'")
                con.execute("UPDATE cash_flow_versions SET gross_amount_cents=NULL")
                con.execute("INSERT INTO schema_migrations(name) VALUES('v0.11.1-remove-interest-and-gross')")
            for household in con.execute("SELECT id FROM households").fetchall():
                if not con.execute("SELECT 1 FROM accounts WHERE household_id=? AND is_default=1",(household["id"],)).fetchone():
                    first=con.execute("SELECT id FROM accounts WHERE household_id=? ORDER BY created_at,id LIMIT 1",(household["id"],)).fetchone()
                    if first: con.execute("UPDATE accounts SET is_default=1 WHERE id=?",(first["id"],))
            con.execute("CREATE UNIQUE INDEX IF NOT EXISTS accounts_one_default ON accounts(household_id) WHERE is_default=1")
    @staticmethod
    def ensure_column(con,table,column,declaration):
        if column not in {row["name"] for row in con.execute(f"PRAGMA table_info({table})").fetchall()}:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")
    def list_households(self):
        with self.connect() as con:
            rows=con.execute("SELECT id,name,mode FROM households ORDER BY created_at").fetchall()
            return [dict(r) for r in rows]
    def create_household(self,payload):
        name=str(payload.get("name","")).strip(); mode=payload.get("mode")
        if not name or mode not in ("single","couple"): raise ValueError("Haushalt und Modell sind erforderlich.")
        people=[("A",str(payload.get("person_a","")).strip())]
        if not people[0][1]: raise ValueError("Person A ist erforderlich.")
        if mode=="couple":
            people.append(("B",str(payload.get("person_b","")).strip()))
            if not people[1][1]: raise ValueError("Person B ist erforderlich.")
        account=payload.get("account") or {}; account_name=str(account.get("name","")).strip()
        hid=uid(); person_ids={slot:uid() for slot,_ in people}
        with self.lock,self.connect() as con:
            con.execute("INSERT INTO households(id,name,mode) VALUES(?,?,?)",(hid,name,mode))
            con.executemany("INSERT INTO persons(id,household_id,slot,display_name) VALUES(?,?,?,?)",[(person_ids[s],hid,s,n) for s,n in people])
            if account_name:
                account_id=uid(); owner=account.get("owner","A"); scope="joint" if owner=="joint" else "person"
                if owner not in person_ids and owner!="joint": owner="A"
                overdraft_limit_cents,overdraft_apr=overdraft_values(account)
                created_at=timestamp(); owner_id=None if scope=="joint" else person_ids[owner]
                con.execute("INSERT INTO accounts(id,household_id,name,owner_scope,owner_person_id,overdraft_limit_cents,overdraft_apr,is_default) VALUES(?,?,?,?,?,?,?,1)",
                    (account_id,hid,account_name,scope,owner_id,overdraft_limit_cents,overdraft_apr))
                con.execute("INSERT INTO account_versions VALUES(?,?,?,?,?,?,?,?,?,?)",(uid(),hid,account_id,account_name,scope,owner_id,overdraft_limit_cents,overdraft_apr,created_at,None))
                con.execute("INSERT INTO balance_anchors(id,household_id,account_id,anchor_date,balance_cents,bookings_applied) VALUES(?,?,?,?,?,?)",
                    (uid(),hid,account_id,account.get("anchor_date") or date.today().isoformat(),int(account.get("balance_cents") or 0),1 if account.get("bookings_applied") else 0))
        return self.household_detail(hid)
    def create_account(self,payload):
        hid=payload.get("household_id"); name=str(payload.get("name","")).strip(); owner=payload.get("owner")
        if not hid or not name: raise ValueError("Haushalt und Kontoname sind erforderlich.")
        anchor_date=as_of_date(payload.get("anchor_date"))
        try: balance_cents=int(payload.get("balance_cents") or 0)
        except (TypeError,ValueError): raise ValueError("Der Kontostand muss ein gültiger Geldwert sein.")
        with self.lock,self.connect() as con:
            people={r["slot"]:r["id"] for r in con.execute("SELECT id,slot FROM persons WHERE household_id=?",(hid,)).fetchall()}
            if not people: raise ValueError("Haushalt nicht gefunden.")
            if owner=="joint": scope="joint"; owner_id=None
            elif owner in people: scope="person"; owner_id=people[owner]
            else: raise ValueError("Ungültiger Kontobesitzer.")
            if con.execute("SELECT 1 FROM accounts WHERE household_id=? AND name=?",(hid,name)).fetchone(): raise ValueError("Ein Konto mit diesem Namen existiert bereits.")
            account_id=uid(); overdraft_limit_cents,overdraft_apr=overdraft_values(payload)
            is_default=1 if payload.get("is_default") or not con.execute("SELECT 1 FROM accounts WHERE household_id=?",(hid,)).fetchone() else 0
            if is_default: con.execute("UPDATE accounts SET is_default=0 WHERE household_id=?",(hid,))
            con.execute("INSERT INTO accounts(id,household_id,name,owner_scope,owner_person_id,overdraft_limit_cents,overdraft_apr,is_default) VALUES(?,?,?,?,?,?,?,?)",(account_id,hid,name,scope,owner_id,overdraft_limit_cents,overdraft_apr,is_default))
            con.execute("INSERT INTO account_versions VALUES(?,?,?,?,?,?,?,?,?,?)",(uid(),hid,account_id,name,scope,owner_id,overdraft_limit_cents,overdraft_apr,timestamp(),None))
            con.execute("INSERT INTO balance_anchors(id,household_id,account_id,anchor_date,balance_cents,bookings_applied) VALUES(?,?,?,?,?,?)",(uid(),hid,account_id,anchor_date,balance_cents,1 if payload.get("bookings_applied") else 0))
        return self.household_detail(hid,anchor_date)
    def update_account(self,account_id,payload):
        hid=payload.get("household_id"); name=str(payload.get("name","")).strip(); owner=payload.get("owner")
        if not hid or not account_id or not name: raise ValueError("Haushalt, Konto und Kontoname sind erforderlich.")
        overdraft_limit_cents,overdraft_apr=overdraft_values(payload); changed_at=timestamp(); anchor_date=as_of_date(payload.get("anchor_date"))
        try: balance_cents=int(payload.get("balance_cents") or 0)
        except (TypeError,ValueError): raise ValueError("Der Kontostand muss ein gültiger Geldwert sein.")
        with self.lock,self.connect() as con:
            current=con.execute("SELECT * FROM accounts WHERE id=? AND household_id=?",(account_id,hid)).fetchone()
            if not current: raise ValueError("Konto nicht gefunden.")
            people={r["slot"]:r["id"] for r in con.execute("SELECT id,slot FROM persons WHERE household_id=?",(hid,)).fetchall()}
            if owner=="joint": scope="joint"; owner_id=None
            elif owner in people: scope="person"; owner_id=people[owner]
            else: raise ValueError("Ungültiger Kontobesitzer.")
            duplicate=con.execute("SELECT 1 FROM accounts WHERE household_id=? AND name=? AND id<>?",(hid,name,account_id)).fetchone()
            if duplicate: raise ValueError("Ein Konto mit diesem Namen existiert bereits.")
            open_version=con.execute("SELECT id FROM account_versions WHERE account_id=? AND valid_to IS NULL",(account_id,)).fetchone()
            if open_version:
                con.execute("UPDATE account_versions SET valid_to=? WHERE id=?",(changed_at,open_version["id"]))
            else:
                con.execute("INSERT INTO account_versions VALUES(?,?,?,?,?,?,?,?,?,?)",(uid(),hid,account_id,current["name"],current["owner_scope"],current["owner_person_id"],int(current["overdraft_limit_cents"] or 0),str(current["overdraft_apr"] or "0"),current["created_at"],changed_at))
            is_default=1 if payload.get("is_default") else int(current["is_default"] or 0)
            if is_default: con.execute("UPDATE accounts SET is_default=0 WHERE household_id=? AND id<>?",(hid,account_id))
            con.execute("UPDATE accounts SET name=?,owner_scope=?,owner_person_id=?,overdraft_limit_cents=?,overdraft_apr=?,is_default=? WHERE id=? AND household_id=?",(name,scope,owner_id,overdraft_limit_cents,overdraft_apr,is_default,account_id,hid))
            con.execute("INSERT INTO account_versions VALUES(?,?,?,?,?,?,?,?,?,?)",(uid(),hid,account_id,name,scope,owner_id,overdraft_limit_cents,overdraft_apr,changed_at,None))
            con.execute("UPDATE account_reconciliations SET status='superseded' WHERE account_id=? AND balance_date=? AND status='active'",(account_id,anchor_date))
            con.execute("""INSERT INTO balance_anchors(id,household_id,account_id,anchor_date,balance_cents,bookings_applied) VALUES(?,?,?,?,?,?)
                ON CONFLICT(account_id,anchor_date) DO UPDATE SET household_id=excluded.household_id,balance_cents=excluded.balance_cents,
                bookings_applied=excluded.bookings_applied,created_at=CURRENT_TIMESTAMP""",(uid(),hid,account_id,anchor_date,balance_cents,1 if payload.get("bookings_applied") else 0))
        return self.household_detail(hid,anchor_date)
    def list_balance_history(self,hid,account_id):
        with self.connect() as con:
            if not con.execute("SELECT 1 FROM accounts WHERE id=? AND household_id=?",(account_id,hid)).fetchone():
                raise ValueError("Konto nicht gefunden.")
            manual=[{**dict(row),"source":"manual"} for row in con.execute(
                "SELECT id,anchor_date,balance_cents,bookings_applied,created_at FROM balance_anchors WHERE account_id=? ORDER BY anchor_date DESC,created_at DESC",(account_id,)).fetchall()]
            statement=[{**dict(row),"bookings_applied":1,"source":"statement"} for row in con.execute(
                "SELECT id,balance_date AS anchor_date,closing_balance_cents AS balance_cents,created_at FROM account_reconciliations WHERE account_id=? AND status='active' ORDER BY balance_date DESC,created_at DESC",(account_id,)).fetchall()]
            return sorted(manual+statement,key=lambda item:(item["anchor_date"],item.get("created_at") or ""),reverse=True)
    def delete_balance_entry(self,hid,account_id,entry_id):
        with self.lock,self.connect() as con:
            row=con.execute("SELECT id,anchor_date FROM balance_anchors WHERE id=? AND account_id=? AND household_id=?",(entry_id,account_id,hid)).fetchone()
            if not row: raise ValueError("Kontostand nicht gefunden oder nicht manuell erfasst.")
            count=con.execute("SELECT COUNT(*) FROM balance_anchors WHERE account_id=?",(account_id,)).fetchone()[0]
            statements=con.execute("SELECT COUNT(*) FROM account_reconciliations WHERE account_id=? AND status='active'",(account_id,)).fetchone()[0]
            if count+statements<=1: raise ValueError("Der einzige Kontostand eines Kontos kann nicht gelöscht werden.")
            con.execute("DELETE FROM balance_anchors WHERE id=?",(entry_id,))
        return {"id":entry_id,"deleted":True}
    def delete_household(self,hid):
        if not hid: raise ValueError("Haushalt ist erforderlich.")
        with self.lock,self.connect() as con:
            household=con.execute("SELECT id,name FROM households WHERE id=?",(hid,)).fetchone()
            if not household: raise ValueError("Haushalt nicht gefunden.")
            con.execute("DELETE FROM households WHERE id=?",(hid,))
        return {"id":hid,"name":household["name"],"deleted":True}
    def list_cash_flows(self,hid,kind,as_of=None):
        if kind not in ("income","expense"): raise ValueError("Ungültige Zahlungsart.")
        selected_date=as_of_date(as_of)
        with self.connect() as con:
            if not con.execute("SELECT 1 FROM households WHERE id=?",(hid,)).fetchone(): raise ValueError("Haushalt nicht gefunden.")
            flows=con.execute("SELECT * FROM cash_flows WHERE household_id=? AND kind=? ORDER BY name",(hid,kind)).fetchall()
            result=[]
            for flow in flows:
                versions=[dict(row) for row in con.execute("SELECT * FROM cash_flow_versions WHERE cash_flow_id=? ORDER BY version_from,rowid",(flow["id"],)).fetchall()]
                for version in versions: version.pop("gross_amount_cents",None)
                current=[version for version in versions if version["version_from"]<=selected_date and (version["version_to"] is None or version["version_to"]>selected_date)]
                upcoming=[version for version in versions if version["version_from"]>selected_date]
                shown=(current[-1] if current else (upcoming[0] if upcoming else (versions[-1] if versions else {})))
                item=dict(flow)
                for field in ("name","category","owner_scope","owner_person_id","account_id"):
                    item[field]=shown.get(field) if shown.get(field) is not None else item.get(field)
                for field in ("amount_cents","active","version_from","version_to","stream_start","stream_end","due_date","recurrence"):
                    item[field]=shown.get(field)
                item["configured_active"]=int(bool(shown.get("active")))
                in_stream=(not item.get("stream_start") or item["stream_start"]<=selected_date) and (not item.get("stream_end") or item["stream_end"]>=selected_date)
                item["active"]=int(bool(current) and bool(item.get("active")) and in_stream)
                item["lifecycle_status"]="current" if current and in_stream else ("upcoming" if upcoming and not current else "ended")
                item["end_date"]=item.get("stream_end") if kind=="expense" else None
                item["duration_months"]=duration_months_between(item.get("due_date"),item.get("stream_end")) if kind=="expense" else None
                item["is_imported"]=str(flow["source_key"] or "").startswith("excel:household-planning:")
                item["versions"]=versions
                item["next_version"]=upcoming[0] if upcoming else None
                result.append(item)
            return result
    def cash_flow_diagnostics(self,hid,as_of=None):
        selected_date=as_of_date(as_of)
        detail=self.household_detail(hid,selected_date)
        if not detail: raise ValueError("Haushalt nicht gefunden.")
        account_ids={account["id"] for account in detail["accounts"]}
        person_ids={person["id"] for person in detail["persons"]}
        items=[]

        def valid_date(value):
            if not value: return False
            try: date.fromisoformat(str(value)); return True
            except (TypeError,ValueError): return False

        for kind in ("income","expense"):
            for flow in self.list_cash_flows(hid,kind,selected_date):
                issues=[]
                def add(code,severity,message): issues.append({"code":code,"severity":severity,"message":message})

                if not str(flow.get("name") or "").strip():
                    add("missing_name","error","Die Bezeichnung fehlt.")
                account_id=flow.get("account_id")
                if not account_id:
                    add("missing_account","error","Kein Konto zugeordnet; die Position kann keinen Kontostand verändern.")
                elif account_id not in account_ids:
                    add("invalid_account","error","Das zugeordnete Konto existiert in diesem Haushalt nicht mehr.")
                if not valid_date(flow.get("due_date")):
                    add("invalid_due_date","error","Die Fälligkeit fehlt oder ist ungültig.")
                if flow.get("recurrence") not in ("monthly","quarterly","yearly","once"):
                    add("invalid_recurrence","error","Der Zahlungsrhythmus ist ungültig.")
                if flow.get("owner_scope") not in ("person","joint"):
                    add("invalid_owner","error","Die Besitzerzuordnung ist ungültig.")
                elif flow.get("owner_scope")=="person" and flow.get("owner_person_id") not in person_ids:
                    add("missing_owner","error","Die zugeordnete Person existiert nicht mehr.")
                if int(flow.get("amount_cents") or 0)==0:
                    add("zero_amount","warning","Der Betrag ist 0,00 € und hat deshalb keine Auswirkung.")
                if not int(flow.get("configured_active") or 0):
                    add("inactive","warning","Die Position ist deaktiviert und wird derzeit nicht berücksichtigt.")
                if not issues: continue
                blocking=any(issue["severity"]=="error" for issue in issues)
                not_considered=blocking or any(issue["code"] in ("zero_amount","inactive") for issue in issues)
                items.append({
                    "id":flow["id"],"kind":kind,"name":flow.get("name") or "Ohne Bezeichnung",
                    "amount_cents":int(flow.get("amount_cents") or 0),"account_id":account_id,
                    "issues":issues,"not_considered":not_considered,
                })
        severity_counts={severity:sum(1 for item in items for issue in item["issues"] if issue["severity"]==severity)
            for severity in ("error","warning","info")}
        return {
            "as_of":selected_date,"items":items,
            "summary":{**severity_counts,"item_count":len(items),
                "not_considered_count":sum(1 for item in items if item["not_considered"])},
        }
    def cash_flow_values(self,con,payload,kind):
        hid=payload.get("household_id"); name=str(payload.get("name","")).strip(); category=str(payload.get("category") or "other").strip()
        if not hid or not name: raise ValueError("Haushalt und Bezeichnung sind erforderlich.")
        if kind not in ("income","expense"): raise ValueError("Ungültige Zahlungsart.")
        try:
            amount=int(payload.get("amount_cents") or 0)
        except (TypeError,ValueError): raise ValueError("Beträge müssen gültige Geldwerte sein.")
        if amount<0: raise ValueError("Beträge dürfen nicht negativ sein.")
        recurrence=str(payload.get("recurrence") or "monthly")
        if recurrence not in ("monthly","quarterly","yearly","once"): raise ValueError("Ungültiger Zahlungsrhythmus.")
        effective=str(payload.get("effective_from") or date.today().isoformat())
        due=str(payload.get("due_date") or "")
        try:
            date.fromisoformat(effective); date.fromisoformat(due)
        except ValueError: raise ValueError("Die Fälligkeit muss ein gültiges Datum sein.")
        stream_end=None; duration_months=None
        if kind=="expense":
            end_raw=payload.get("end_date") if payload.get("end_date") not in (None,"") else payload.get("stream_end")
            parsed_end=None
            if end_raw:
                try: parsed_end=date.fromisoformat(str(end_raw)).isoformat()
                except ValueError: raise ValueError("Das Enddatum muss ein gültiges Datum sein.")
            duration_raw=payload.get("duration_months")
            if duration_raw not in (None,""):
                try:
                    duration_months=int(duration_raw)
                except (TypeError,ValueError):
                    raise ValueError("Die Dauer muss als ganze Anzahl Monate angegeben werden.")
                if str(duration_raw).strip()!=str(duration_months) or not 1<=duration_months<=1200:
                    raise ValueError("Die Dauer muss zwischen 1 und 1.200 ganzen Monaten liegen.")
                calculated_end=add_months_anchored(due,duration_months).isoformat()
                if parsed_end and parsed_end!=calculated_end:
                    raise ValueError("Enddatum und Dauer passen nicht zusammen.")
                stream_end=calculated_end
            elif parsed_end:
                stream_end=parsed_end
            if stream_end and stream_end<due:
                raise ValueError("Das Enddatum darf nicht vor der ersten Fälligkeit liegen.")
        household=con.execute("SELECT mode FROM households WHERE id=?",(hid,)).fetchone()
        if not household: raise ValueError("Haushalt nicht gefunden.")
        people={row["slot"]:row["id"] for row in con.execute("SELECT id,slot FROM persons WHERE household_id=?",(hid,)).fetchall()}
        owner="A" if household["mode"]=="single" else payload.get("owner")
        if owner=="joint": scope="joint"; owner_id=None
        elif owner in people: scope="person"; owner_id=people[owner]
        else: raise ValueError("Ungültiger Besitzer.")
        account_id=payload.get("account_id") or None
        if account_id and not con.execute("SELECT 1 FROM accounts WHERE id=? AND household_id=?",(account_id,hid)).fetchone(): raise ValueError("Das gewählte Konto gehört nicht zum Haushalt.")
        active=0 if payload.get("active") in (False,0,"0") else 1
        return {"household_id":hid,"name":name,"category":category,"amount_cents":amount,"gross_amount_cents":None,"recurrence":recurrence,"effective_from":effective,"due_date":due,"stream_end":stream_end,"duration_months":duration_months,"active":active,"owner_scope":scope,"owner_person_id":owner_id,"account_id":account_id}
    def create_cash_flow(self,payload):
        kind=payload.get("kind")
        with self.lock,self.connect() as con:
            values=self.cash_flow_values(con,payload,kind)
            flow_id=uid()
            con.execute("""INSERT INTO cash_flows(id,household_id,kind,name,owner_scope,owner_person_id,account_id,source_key,category)
                VALUES(?,?,?,?,?,?,?,?,?)""",(flow_id,values["household_id"],kind,values["name"],values["owner_scope"],values["owner_person_id"],values["account_id"],None,values["category"]))
            con.execute("""INSERT INTO cash_flow_versions(id,cash_flow_id,amount_cents,active,version_from,version_to,stream_start,stream_end,due_date,source_reference,gross_amount_cents,recurrence,name,category,owner_scope,owner_person_id,account_id)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(uid(),flow_id,values["amount_cents"],values["active"],values["effective_from"],None,values["effective_from"],values["stream_end"],values["due_date"],"Manuell erstellt",values["gross_amount_cents"],values["recurrence"],values["name"],values["category"],values["owner_scope"],values["owner_person_id"],values["account_id"]))
        return next(item for item in self.list_cash_flows(values["household_id"],kind,values["effective_from"]) if item["id"]==flow_id)
    def update_cash_flow(self,flow_id,payload):
        kind=payload.get("kind")
        with self.lock,self.connect() as con:
            flow=con.execute("SELECT * FROM cash_flows WHERE id=? AND household_id=?",(flow_id,payload.get("household_id"))).fetchone()
            if not flow: raise ValueError("Zahlungsstrom nicht gefunden.")
            if kind and kind!=flow["kind"]: raise ValueError("Die Zahlungsart kann nicht geändert werden.")
            kind=flow["kind"]; values=self.cash_flow_values(con,payload,kind); effective=values["effective_from"]
            versions=con.execute("SELECT * FROM cash_flow_versions WHERE cash_flow_id=? ORDER BY version_from,rowid",(flow_id,)).fetchall()
            same=next((row for row in versions if row["version_from"]==effective),None)
            next_date=next((row["version_from"] for row in versions if row["version_from"]>effective),None)
            if same:
                con.execute("""UPDATE cash_flow_versions SET amount_cents=?,active=?,stream_start=?,stream_end=?,due_date=?,source_reference=?,gross_amount_cents=?,recurrence=?,name=?,category=?,owner_scope=?,owner_person_id=?,account_id=? WHERE id=?""",
                    (values["amount_cents"],values["active"],effective,values["stream_end"],values["due_date"],"Manuelle Änderung",values["gross_amount_cents"],values["recurrence"],values["name"],values["category"],values["owner_scope"],values["owner_person_id"],values["account_id"],same["id"]))
            else:
                previous=[row for row in versions if row["version_from"]<effective]
                if previous:
                    prior=previous[-1]
                    if prior["version_to"] is None or prior["version_to"]>effective: con.execute("UPDATE cash_flow_versions SET version_to=? WHERE id=?",(effective,prior["id"]))
                con.execute("""INSERT INTO cash_flow_versions(id,cash_flow_id,amount_cents,active,version_from,version_to,stream_start,stream_end,due_date,source_reference,gross_amount_cents,recurrence,name,category,owner_scope,owner_person_id,account_id)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(uid(),flow_id,values["amount_cents"],values["active"],effective,next_date,effective,values["stream_end"],values["due_date"],"Manuelle Änderung",values["gross_amount_cents"],values["recurrence"],values["name"],values["category"],values["owner_scope"],values["owner_person_id"],values["account_id"]))
            if effective<=date.today().isoformat():
                con.execute("UPDATE cash_flows SET name=?,category=?,owner_scope=?,owner_person_id=?,account_id=?,source_key=NULL WHERE id=?",(values["name"],values["category"],values["owner_scope"],values["owner_person_id"],values["account_id"],flow_id))
            else:
                con.execute("UPDATE cash_flows SET source_key=NULL WHERE id=?",(flow_id,))
        return next(item for item in self.list_cash_flows(values["household_id"],kind,effective) if item["id"]==flow_id)
    def delete_cash_flow(self,hid,flow_id):
        with self.lock,self.connect() as con:
            flow=con.execute("SELECT id,name FROM cash_flows WHERE id=? AND household_id=?",(flow_id,hid)).fetchone()
            if not flow: raise ValueError("Zahlungsstrom nicht gefunden.")
            con.execute("DELETE FROM cash_flows WHERE id=?",(flow_id,))
        return {"id":flow_id,"name":flow["name"],"deleted":True}
    def transfer_values(self,con,payload):
        hid=payload.get("household_id"); source=payload.get("source_account_id"); target=payload.get("target_account_id")
        name=str(payload.get("name") or "Umbuchung").strip() or "Umbuchung"
        if not hid or not source or not target: raise ValueError("Haushalt, Quellkonto und Zielkonto sind erforderlich.")
        if source==target: raise ValueError("Quellkonto und Zielkonto müssen verschieden sein.")
        accounts={row["id"] for row in con.execute("SELECT id FROM accounts WHERE household_id=?",(hid,)).fetchall()}
        if source not in accounts or target not in accounts: raise ValueError("Beide Konten müssen zum Haushalt gehören.")
        try: amount=int(payload.get("amount_cents") or 0)
        except (TypeError,ValueError): raise ValueError("Der Betrag muss ein gültiger Geldwert sein.")
        if amount<=0: raise ValueError("Der Umbuchungsbetrag muss größer als 0,00 € sein.")
        recurrence=str(payload.get("recurrence") or "once")
        if recurrence not in ("monthly","quarterly","yearly","once"): raise ValueError("Ungültiger Zahlungsrhythmus.")
        due=as_of_date(payload.get("due_date"))
        end_date=None
        if payload.get("end_date") not in (None,""):
            end_date=as_of_date(payload.get("end_date"))
            if end_date<due: raise ValueError("Das Ende darf nicht vor der ersten Fälligkeit liegen.")
        occurrence_count=None
        count_raw=payload.get("occurrence_count")
        if count_raw not in (None,""):
            try: occurrence_count=int(count_raw)
            except (TypeError,ValueError): raise ValueError("Die Anzahl muss eine ganze Zahl sein.")
            if str(count_raw).strip()!=str(occurrence_count) or not 1<=occurrence_count<=1200:
                raise ValueError("Die Anzahl muss zwischen 1 und 1.200 Ausführungen liegen.")
        active=0 if payload.get("active") in (False,0,"0") else 1
        return {"household_id":hid,"name":name,"source_account_id":source,"target_account_id":target,
            "amount_cents":amount,"recurrence":recurrence,"due_date":due,"end_date":end_date,
            "occurrence_count":occurrence_count,"active":active}
    def list_transfers(self,hid):
        with self.connect() as con:
            if not con.execute("SELECT 1 FROM households WHERE id=?",(hid,)).fetchone(): raise ValueError("Haushalt nicht gefunden.")
            rows=con.execute("""SELECT t.*,s.name AS source_account_name,d.name AS target_account_name
                FROM transfers t JOIN accounts s ON s.id=t.source_account_id JOIN accounts d ON d.id=t.target_account_id
                WHERE t.household_id=? ORDER BY t.active DESC,t.due_date,t.name""",(hid,)).fetchall()
            return [dict(row) for row in rows]
    def create_transfer(self,payload):
        with self.lock,self.connect() as con:
            values=self.transfer_values(con,payload); transfer_id=uid()
            con.execute("""INSERT INTO transfers(id,household_id,name,source_account_id,target_account_id,amount_cents,recurrence,due_date,end_date,occurrence_count,active)
                VALUES(?,?,?,?,?,?,?,?,?,?,?)""",(transfer_id,values["household_id"],values["name"],values["source_account_id"],values["target_account_id"],values["amount_cents"],values["recurrence"],values["due_date"],values["end_date"],values["occurrence_count"],values["active"]))
        return next(item for item in self.list_transfers(values["household_id"]) if item["id"]==transfer_id)
    def update_transfer(self,transfer_id,payload):
        with self.lock,self.connect() as con:
            values=self.transfer_values(con,payload)
            if not con.execute("SELECT 1 FROM transfers WHERE id=? AND household_id=?",(transfer_id,values["household_id"])).fetchone(): raise ValueError("Umbuchung nicht gefunden.")
            con.execute("""UPDATE transfers SET name=?,source_account_id=?,target_account_id=?,amount_cents=?,recurrence=?,due_date=?,end_date=?,occurrence_count=?,active=?
                WHERE id=? AND household_id=?""",(values["name"],values["source_account_id"],values["target_account_id"],values["amount_cents"],values["recurrence"],values["due_date"],values["end_date"],values["occurrence_count"],values["active"],transfer_id,values["household_id"]))
        return next(item for item in self.list_transfers(values["household_id"]) if item["id"]==transfer_id)
    def delete_transfer(self,hid,transfer_id):
        with self.lock,self.connect() as con:
            row=con.execute("SELECT id,name FROM transfers WHERE id=? AND household_id=?",(transfer_id,hid)).fetchone()
            if not row: raise ValueError("Umbuchung nicht gefunden.")
            con.execute("DELETE FROM transfers WHERE id=?",(transfer_id,))
        return {"id":transfer_id,"name":row["name"],"deleted":True}
    def household_detail(self,hid,as_of=None):
        selected_date=as_of_date(as_of)
        with self.connect() as con:
            household=con.execute("SELECT id,name,mode FROM households WHERE id=?",(hid,)).fetchone()
            if not household: return None
            people=con.execute("SELECT id,slot,display_name FROM persons WHERE household_id=? ORDER BY slot",(hid,)).fetchall()
            account_rows=con.execute("""SELECT a.id,COALESCE(v.name,a.name) AS name,COALESCE(v.owner_scope,a.owner_scope) AS owner_scope,
                COALESCE(v.owner_person_id,a.owner_person_id) AS owner_person_id,
                COALESCE(v.overdraft_limit_cents,a.overdraft_limit_cents) AS overdraft_limit_cents,a.is_default
                FROM accounts a
                LEFT JOIN account_versions v ON v.id=(SELECT v2.id FROM account_versions v2 WHERE v2.account_id=a.id AND substr(v2.valid_from,1,10)<=? AND (v2.valid_to IS NULL OR substr(v2.valid_to,1,10)>?) ORDER BY v2.valid_from DESC LIMIT 1)
                WHERE a.household_id=? ORDER BY a.created_at""",(selected_date,selected_date,hid)).fetchall()
            accounts=[]
            for row in account_rows:
                item=dict(row)
                anchor=con.execute("""SELECT balance_cents,anchor_date,anchor_source,bookings_applied FROM (
                        SELECT balance_cents,anchor_date,'manual' AS anchor_source,bookings_applied,COALESCE(created_at,'') AS recorded_at
                        FROM balance_anchors WHERE account_id=?
                        UNION ALL
                        SELECT closing_balance_cents AS balance_cents,balance_date AS anchor_date,'statement' AS anchor_source,1 AS bookings_applied,created_at AS recorded_at
                        FROM account_reconciliations WHERE account_id=? AND status='active'
                    ) WHERE anchor_date<=? ORDER BY anchor_date DESC,
                        CASE anchor_source WHEN 'statement' THEN 1 ELSE 0 END DESC,
                        recorded_at DESC LIMIT 1""",
                    (item["id"],item["id"],selected_date)).fetchone()
                item["balance_cents"]=anchor["balance_cents"] if anchor else None
                item["anchor_date"]=anchor["anchor_date"] if anchor else None
                item["anchor_source"]=anchor["anchor_source"] if anchor else None
                item["bookings_applied"]=int(anchor["bookings_applied"]) if anchor else 0
                accounts.append(item)
            return {**dict(household),"as_of":selected_date,"persons":[dict(x) for x in people],"accounts":accounts}
    def projected_account_balances(self,con,hid,accounts,selected_date,excluded_cash_flow_ids=None):
        excluded_cash_flow_ids={str(value) for value in (excluded_cash_flow_ids or [])}
        account_by_id={account["id"]:account for account in accounts}
        projected={account["id"]:{
            "balance_cents":account["balance_cents"],"event_count":0,
            "income_cents":0,"expense_cents":0,
        } for account in accounts}
        result={"event_count":0,"net_cents":0,"events":[],"unassigned_events":[]}

        matches=con.execute("""SELECT m.occurrence_key,m.target_type,m.target_id,m.planned_date,m.match_method,
                t.id AS transaction_id,t.booking_date,t.amount_cents
            FROM bank_transaction_matches m JOIN bank_transactions t ON t.id=m.transaction_id
            WHERE t.household_id=?""",(hid,)).fetchall()
        matched_occurrences={row["occurrence_key"] for row in matches}
        bank_actual_flow_ids={
            row["target_id"] for row in matches
            if row["target_type"]=="cash_flow" and row["match_method"]=="created-other-expense"
        }

        def add_event(account_id,event_date,amount_cents,kind,label,source_id,occurrence_key,origin,show_on_anchor=False):
            event={
                "date":event_date,"account_id":account_id,"kind":kind,"label":label,
                "source_id":source_id,"occurrence_key":occurrence_key,
                "origin":origin,"amount_cents":amount_cents,
            }
            target=projected.get(account_id)
            if target is None:
                result["event_count"]+=1; result["net_cents"]+=amount_cents
                result["unassigned_events"].append(event)
                return
            account=account_by_id[account_id]
            if account["anchor_date"] is None: return
            before_anchor=event_date<account["anchor_date"]
            already_in_anchor=event_date==account["anchor_date"] and bool(account.get("bookings_applied"))
            if before_anchor or already_in_anchor:
                # A confirmed end-of-day anchor already contains its same-day
                # movements. They remain visible, but are not applied twice.
                if show_on_anchor and event_date==account["anchor_date"] and event_date==selected_date:
                    result["events"].append({**event,"applied_to_projection":False})
                return
            if target["balance_cents"] is None: return
            target["balance_cents"]+=amount_cents; target["event_count"]+=1
            if amount_cents>=0: target["income_cents"]+=amount_cents
            else: target["expense_cents"]+=-amount_cents
            result["events"].append({**event,"applied_to_projection":True})

        versions=con.execute("""SELECT f.id AS flow_id,f.kind,COALESCE(v.name,f.name) AS label,
                   v.amount_cents,v.active,v.version_from,v.version_to,v.stream_start,v.stream_end,
                   v.due_date,v.recurrence,COALESCE(v.account_id,f.account_id) AS account_id
            FROM cash_flow_versions v JOIN cash_flows f ON f.id=v.cash_flow_id
            WHERE f.household_id=? AND v.active=1 AND v.version_from<=?
              AND (v.stream_start IS NULL OR v.stream_start<=?)""",(hid,selected_date,selected_date)).fetchall()
        for version in versions:
            if version["flow_id"] in excluded_cash_flow_ids: continue
            # A cash flow created from an unmatched statement debit classifies
            # an already persisted bank transaction.  The bank row remains the
            # accounting truth even when the editable label, amount or date of
            # that classification is changed later; materialising the flow as
            # an additional plan occurrence would count the debit twice.
            if version["flow_id"] in bank_actual_flow_ids: continue
            account=projected.get(version["account_id"])
            start=None
            if account:
                account_meta=account_by_id[version["account_id"]]
                start=account_meta["anchor_date"]
                if start and not account_meta.get("bookings_applied"):
                    start=(date.fromisoformat(start)-timedelta(days=1)).isoformat()
            if start is None:
                # Unassigned items are reported for the selected month.  This
                # keeps the warning actionable instead of accumulating every
                # historical occurrence forever.
                try: start=(date.fromisoformat(selected_date).replace(day=1)-timedelta(days=1)).isoformat()
                except (TypeError,ValueError): continue
            try:
                due_dates=recurrence_dates(version["due_date"],version["recurrence"] or "monthly",start,selected_date,
                    version["version_from"],version["version_to"],version["stream_start"],version["stream_end"])
            except (TypeError,ValueError):
                # Legacy or otherwise malformed rows remain visible in the
                # data check, but must not break the complete forecast.
                continue
            for due in due_dates:
                due_text=due.isoformat(); occurrence_key=f"cash-flow:{version['flow_id']}:{due_text}"
                if occurrence_key in matched_occurrences: continue
                amount=int(version["amount_cents"] or 0)*(1 if version["kind"]=="income" else -1)
                add_event(version["account_id"],due_text,amount,version["kind"],version["label"],version["flow_id"],occurrence_key,"planned")

        transfers=con.execute("SELECT * FROM transfers WHERE household_id=? AND active=1",(hid,)).fetchall()
        for transfer in transfers:
            starts=[]
            for account_id in (transfer["source_account_id"],transfer["target_account_id"]):
                if account_id not in account_by_id or not account_by_id[account_id]["anchor_date"]: continue
                account_meta=account_by_id[account_id]; start=account_meta["anchor_date"]
                if not account_meta.get("bookings_applied"):
                    start=(date.fromisoformat(start)-timedelta(days=1)).isoformat()
                starts.append(start)
            start=min(starts) if starts else (date.fromisoformat(selected_date).replace(day=1)-timedelta(days=1)).isoformat()
            try:
                due_dates=recurrence_dates(transfer["due_date"],transfer["recurrence"] or "once",start,selected_date,
                    active_from=transfer["due_date"],stream_start=transfer["due_date"],stream_end=transfer["end_date"],
                    max_occurrences=transfer["occurrence_count"])
            except (TypeError,ValueError):
                continue
            for due in due_dates:
                due_text=due.isoformat(); amount=int(transfer["amount_cents"] or 0)
                add_event(transfer["source_account_id"],due_text,-amount,"transfer_out",transfer["name"],transfer["id"],f"transfer:{transfer['id']}:{due_text}:out","transfer")
                add_event(transfer["target_account_id"],due_text,amount,"transfer_in",transfer["name"],transfer["id"],f"transfer:{transfer['id']}:{due_text}:in","transfer")

        bank_rows=con.execute("""SELECT t.*,m.target_type,m.target_id
            FROM bank_transactions t LEFT JOIN bank_transaction_matches m ON m.transaction_id=t.id
            WHERE t.household_id=? AND t.booking_date<=? ORDER BY t.booking_date,t.rowid""",(hid,selected_date)).fetchall()
        for row in bank_rows:
            if row["target_type"]=="cash_flow" and row["target_id"] in excluded_cash_flow_ids: continue
            amount=int(row["amount_cents"] or 0)
            kind="income" if amount>=0 else "expense"
            label=str(row["counterparty"] or row["purpose"] or "Kontobuchung").strip()
            source_id=row["target_id"] or row["id"]
            add_event(row["account_id"],row["booking_date"],amount,kind,label,source_id,f"bank-transaction:{row['id']}","actual",True)

        for account in accounts:
            values=projected[account["id"]]
            account["projected_balance_cents"]=values["balance_cents"]
            account["projection_event_count"]=values["event_count"]
            account["projection_income_cents"]=values["income_cents"]
            account["projection_expense_cents"]=values["expense_cents"]
            account["projected_through"]=selected_date
            limit=int(account.get("overdraft_limit_cents") or 0)
            balance=values["balance_cents"]
            account["overdraft_exceeded"]=bool(limit>0 and balance is not None and balance < -limit)
            account["overdraft_overage_cents"]=max(0,-limit-int(balance)) if account["overdraft_exceeded"] else 0
        return result

    def simulation_dashboard(self,hid,as_of,account_ids,excluded_cash_flow_ids=None):
        selected_date=as_of_date(as_of)
        if not isinstance(account_ids,list): raise ValueError("Die Kontenauswahl muss eine Liste sein.")
        account_ids=[str(value) for value in account_ids if str(value)]
        if len(account_ids)>4: raise ValueError("In der Prognose können höchstens vier Konten ausgewählt werden.")
        if len(account_ids)!=len(set(account_ids)): raise ValueError("Konten dürfen nicht doppelt ausgewählt werden.")
        excluded=[str(value) for value in (excluded_cash_flow_ids or []) if str(value)]
        if len(excluded)!=len(set(excluded)): excluded=list(dict.fromkeys(excluded))
        detail=self.household_detail(hid,selected_date)
        if not detail: raise ValueError("Haushalt nicht gefunden.")
        owned_accounts={item["id"] for item in detail["accounts"]}
        if any(account_id not in owned_accounts for account_id in account_ids):
            raise ValueError("Mindestens ein Konto gehört nicht zu diesem Haushalt.")
        with self.connect() as con:
            if excluded:
                placeholders=",".join("?" for _ in excluded)
                found={row["id"] for row in con.execute(
                    f"SELECT id FROM cash_flows WHERE household_id=? AND id IN ({placeholders})",(hid,*excluded)).fetchall()}
                if found!=set(excluded): raise ValueError("Mindestens ein Zahlungsstrom gehört nicht zu diesem Haushalt.")
            projection=self.projected_account_balances(con,hid,detail["accounts"],selected_date,excluded)
            selected_day=date.fromisoformat(selected_date)
            next_month=(selected_day.replace(day=28)+timedelta(days=4)).replace(day=1)
            month_end=(next_month-timedelta(days=1)).isoformat()
            month_accounts=[dict(account) for account in detail["accounts"]]
            month_projection=self.projected_account_balances(con,hid,month_accounts,month_end,excluded)
        selected=[]
        for account in detail["accounts"]:
            if account["id"] not in account_ids: continue
            item=dict(account)
            day_delta=sum(event["amount_cents"] for event in projection["events"] if event["account_id"]==account["id"] and event["date"]==selected_date)
            item["available"]=item["anchor_date"] is not None and item["projected_balance_cents"] is not None
            item["day_delta_cents"]=day_delta
            selected.append(item)
        selected_ids=set(account_ids)
        movements=[event for event in projection["events"] if event["account_id"] in selected_ids and event["date"]==selected_date]
        movements.sort(key=lambda item:(account_ids.index(item["account_id"]),item["kind"],item["label"]))
        day_income=sum(item["amount_cents"] for item in movements if item["amount_cents"]>0)
        day_expense=sum(-item["amount_cents"] for item in movements if item["amount_cents"]<0)
        projected_total=sum(int(item["projected_balance_cents"] or 0) for item in selected if item["available"])
        month_movements=[
            event for event in month_projection["events"]
            if event["account_id"] in selected_ids and selected_date<event["date"]<=month_end
        ]
        month_unassigned=[
            event for event in month_projection["unassigned_events"]
            if selected_date<event["date"]<=month_end
        ]
        account_order={account_id:index for index,account_id in enumerate(account_ids)}
        month_movements.extend(month_unassigned)
        month_movements.sort(key=lambda item:(
            item["date"],account_order.get(item["account_id"],len(account_order)),item["kind"],item["label"]
        ))
        month_income=sum(item["amount_cents"] for item in month_movements if item["amount_cents"]>0)
        month_expense=sum(-item["amount_cents"] for item in month_movements if item["amount_cents"]<0)
        return {
            "as_of":selected_date,"accounts":selected,"movements":movements,
            "totals":{"projected_balance_cents":projected_total,"day_income_cents":day_income,
                "day_expense_cents":day_expense,"day_delta_cents":day_income-day_expense},
            "unassigned":{"event_count":projection["event_count"],"net_cents":projection["net_cents"],
                "items":projection["unassigned_events"]},
            "month":{"through":month_end,"movements":month_movements,
                "totals":{"income_cents":month_income,"expense_cents":month_expense,
                    "delta_cents":month_income-month_expense}},
            "excluded_cash_flow_ids":excluded,
        }

    def monthly_preview(self,hid,month,account_ids):
        try:
            month_start=date.fromisoformat(f"{str(month)[:7]}-01")
        except ValueError:
            raise ValueError("Der Vorschaumonat ist ungültig.")
        next_month=(month_start.replace(day=28)+timedelta(days=4)).replace(day=1)
        month_end=next_month-timedelta(days=1); opening_day=month_start-timedelta(days=1)
        if not isinstance(account_ids,list): raise ValueError("Die Kontenauswahl muss eine Liste sein.")
        account_ids=list(dict.fromkeys(str(value) for value in account_ids if str(value)))
        end_detail=self.household_detail(hid,month_end.isoformat())
        opening_detail=self.household_detail(hid,opening_day.isoformat())
        if not end_detail or not opening_detail: raise ValueError("Haushalt nicht gefunden.")
        owned={account["id"] for account in end_detail["accounts"]}
        if any(account_id not in owned for account_id in account_ids): raise ValueError("Mindestens ein Konto gehört nicht zu diesem Haushalt.")
        selected_ids=set(account_ids)
        account_order={account_id:index for index,account_id in enumerate(account_ids)}
        with self.connect() as con:
            self.projected_account_balances(con,hid,opening_detail["accounts"],opening_day.isoformat())
            opening_by_id={account["id"]:dict(account) for account in opening_detail["accounts"]}
            days=[]; movements=[]; minimum_by_id={}
            cursor=month_start
            while cursor<=month_end:
                day_text=cursor.isoformat(); day_detail=self.household_detail(hid,day_text)
                if not day_detail: raise ValueError("Haushalt nicht gefunden.")
                projection=self.projected_account_balances(con,hid,day_detail["accounts"],day_text)
                day_accounts=[]
                for account in day_detail["accounts"]:
                    if account["id"] not in selected_ids: continue
                    balance=account.get("projected_balance_cents")
                    minimum_by_id[account["id"]]=balance if account["id"] not in minimum_by_id else (
                        minimum_by_id[account["id"]] if balance is None else (
                            balance if minimum_by_id[account["id"]] is None else min(minimum_by_id[account["id"]],balance)
                        )
                    )
                    day_accounts.append({
                        "id":account["id"],"name":account["name"],
                        "projected_balance_cents":balance,
                        "overdraft_limit_cents":int(account.get("overdraft_limit_cents") or 0),
                        "overdraft_exceeded":bool(account.get("overdraft_exceeded")),
                        "overdraft_overage_cents":int(account.get("overdraft_overage_cents") or 0),
                    })
                day_movements=[event for event in projection["events"]
                    if event["account_id"] in selected_ids and event["date"]==day_text]
                day_movements.extend(event for event in projection["unassigned_events"] if event["date"]==day_text)
                day_movements.sort(key=lambda item:(account_order.get(item["account_id"],len(account_order)),item["kind"],item["label"]))
                movements.extend(day_movements)
                day_total=sum(int(account["projected_balance_cents"] or 0) for account in day_accounts
                    if account["projected_balance_cents"] is not None)
                days.append({
                    "date":day_text,"accounts":day_accounts,"balances":day_accounts,
                    "total_balance_cents":day_total,
                    "delta_cents":sum(int(event["amount_cents"] or 0) for event in day_movements),
                    "movement_count":len(day_movements),"movements":day_movements,
                    "overdraft_warning_count":sum(1 for account in day_accounts if account["overdraft_exceeded"]),
                })
                cursor+=timedelta(days=1)
        closing_by_id={account["id"]:account for account in days[-1]["accounts"]} if days else {}
        selected=[]
        for account in end_detail["accounts"]:
            if account["id"] not in selected_ids: continue
            opening=opening_by_id.get(account["id"]); closing=closing_by_id.get(account["id"])
            item=dict(account)
            item["opening_balance_cents"]=opening.get("projected_balance_cents") if opening else None
            item["closing_balance_cents"]=closing.get("projected_balance_cents") if closing else None
            item["projected_balance_cents"]=item["closing_balance_cents"]
            item["month_delta_cents"]=(item["closing_balance_cents"]-item["opening_balance_cents"]
                if item["closing_balance_cents"] is not None and item["opening_balance_cents"] is not None else None)
            minimum=minimum_by_id.get(account["id"])
            if item["opening_balance_cents"] is not None:
                minimum=item["opening_balance_cents"] if minimum is None else min(minimum,item["opening_balance_cents"])
            limit=int(account.get("overdraft_limit_cents") or 0)
            item["minimum_balance_cents"]=minimum
            item["overdraft_exceeded_during_month"]=bool(limit>0 and minimum is not None and minimum < -limit)
            item["monthly_overdraft_overage_cents"]=max(0,-limit-int(minimum)) if item["overdraft_exceeded_during_month"] else 0
            selected.append(item)
        movements.sort(key=lambda item:(item["date"],account_order.get(item["account_id"],len(account_order)),item["kind"],item["label"]))
        income=sum(item["amount_cents"] for item in movements if item["kind"]=="income" and item["amount_cents"]>0)
        expenses=sum(-item["amount_cents"] for item in movements if item["kind"]=="expense" and item["amount_cents"]<0)
        transfers=sum(abs(item["amount_cents"]) for item in movements if item["kind"] in ("transfer_in","transfer_out"))
        opening_total=sum(int(item["opening_balance_cents"] or 0) for item in selected if item["opening_balance_cents"] is not None)
        closing_total=sum(int(item["closing_balance_cents"] or 0) for item in selected if item["closing_balance_cents"] is not None)
        return {"month":month_start.strftime("%Y-%m"),"from":month_start.isoformat(),"through":month_end.isoformat(),
            "accounts":selected,"days":days,"movements":movements,
            "totals":{"opening_balance_cents":opening_total,"closing_balance_cents":closing_total,
                "income_cents":income,"expense_cents":expenses,"transfer_volume_cents":transfers,
                "delta_cents":closing_total-opening_total},
            "unassigned":{"items":[item for item in movements if item.get("account_id") is None]},
            "overdraft_warnings":[{"account_id":account["id"],"name":account["name"],"overage_cents":account["monthly_overdraft_overage_cents"]}
                for account in selected if account.get("overdraft_exceeded_during_month")]}

    def planned_occurrences_for_matching(self,con,hid,account_id,period_from,period_to):
        scan_from=(date.fromisoformat(period_from)-timedelta(days=3))
        scan_to=(date.fromisoformat(period_to)+timedelta(days=3))
        start=(scan_from-timedelta(days=1)).isoformat(); end=scan_to.isoformat()
        occurrences=[]
        versions=con.execute("""SELECT f.id AS flow_id,f.kind,COALESCE(v.name,f.name) AS label,
                   v.amount_cents,v.version_from,v.version_to,v.stream_start,v.stream_end,
                   v.due_date,v.recurrence,COALESCE(v.account_id,f.account_id) AS account_id
            FROM cash_flow_versions v JOIN cash_flows f ON f.id=v.cash_flow_id
            WHERE f.household_id=? AND COALESCE(v.account_id,f.account_id)=? AND v.active=1
              AND v.version_from<=? AND (v.stream_start IS NULL OR v.stream_start<=?)""",
            (hid,account_id,end,end)).fetchall()
        for version in versions:
            for due in recurrence_dates(version["due_date"],version["recurrence"] or "monthly",start,end,
                                        version["version_from"],version["version_to"],version["stream_start"],version["stream_end"]):
                due_text=due.isoformat()
                occurrences.append({
                    "target_type":"cash_flow","target_id":version["flow_id"],
                    "occurrence_key":f"cash-flow:{version['flow_id']}:{due_text}",
                    "date":due_text,"amount_cents":int(version["amount_cents"] or 0)*(1 if version["kind"]=="income" else -1),
                    "kind":version["kind"],"label":version["label"],
                })
        used={row["occurrence_key"] for row in con.execute("""SELECT m.occurrence_key FROM bank_transaction_matches m
            JOIN bank_transactions t ON t.id=m.transaction_id WHERE t.household_id=?""",(hid,)).fetchall()}
        return [item for item in occurrences if item["occurrence_key"] not in used]

    def save_bank_statement_preview(self,hid,account_id,parsed):
        raise ValueError("Importfunktionen sind in dieser Version vollständig deaktiviert.")
        if not hid or not account_id: raise ValueError("Haushalt und Konto sind erforderlich.")
        currencies={str(row.get("currency") or "EUR").upper() for row in parsed.get("rows",[])}
        if currencies-{"EUR"}: raise ValueError("Der Kontoauszugsimport unterstützt in dieser Version ausschließlich EUR-Buchungen.")
        summary=dict(parsed.get("summary") or {})
        period_from=as_of_date(summary.get("period_from")); period_to=as_of_date(summary.get("period_to"))
        detail=self.household_detail(hid,period_to)
        if not detail: raise ValueError("Haushalt nicht gefunden.")
        account=next((item for item in detail["accounts"] if item["id"]==account_id),None)
        if not account: raise ValueError("Konto gehört nicht zu diesem Haushalt.")
        dashboard=self.dashboard(hid,summary.get("detected_closing_balance_date") or period_to)
        projected_account=next(item for item in dashboard["household"]["accounts"] if item["id"]==account_id)
        projected_balance=projected_account.get("projected_balance_cents")
        closing_balance=summary.get("detected_closing_balance_cents")
        with self.lock,self.connect() as con:
            occurrences=self.planned_occurrences_for_matching(con,hid,account_id,period_from,period_to)
            occurrences_by_amount={}
            for occurrence in occurrences:
                occurrences_by_amount.setdefault(int(occurrence["amount_cents"]),[]).append(occurrence)
            existing={(row["fingerprint_base"],int(row["occurrence_no"])) for row in con.execute(
                "SELECT fingerprint_base,occurrence_no FROM bank_transactions WHERE account_id=?",(account_id,)).fetchall()}
            preview_rows=[]
            for transaction in parsed["rows"]:
                row=dict(transaction)
                identity=(row["fingerprint_base"],int(row["occurrence_no"]))
                if identity in existing:
                    row.update({"status":"duplicate","candidates":[],"suggested_action":"skip","suggested_occurrence_key":None})
                    preview_rows.append(row); continue
                transaction_date=date.fromisoformat(row.get("value_date") or row["booking_date"])
                transaction_tokens=normalized_match_tokens(row.get("counterparty"),row.get("purpose"),row.get("bank_reference"))
                candidates=[]
                for occurrence in occurrences_by_amount.get(int(row["amount_cents"]),[]):
                    distance=abs((date.fromisoformat(occurrence["date"])-transaction_date).days)
                    if distance>3: continue
                    label_tokens=normalized_match_tokens(occurrence["label"])
                    overlap=len(transaction_tokens & label_tokens)
                    score=100+(3-distance)*10+min(20,overlap*5)
                    candidates.append({**occurrence,"date_distance":distance,"score":score})
                candidates.sort(key=lambda item:(-item["score"],item["date"],item["label"]))
                suggested=None
                if len(candidates)==1:
                    suggested=candidates[0]
                elif len(candidates)>1 and candidates[0]["score"]>=candidates[1]["score"]+5:
                    suggested=candidates[0]
                if suggested:
                    status="matched"; action="match"; occurrence_key=suggested["occurrence_key"]
                elif candidates:
                    status="ambiguous"; action="review"; occurrence_key=None
                elif int(row["amount_cents"])<0:
                    status="unmatched_debit"; action="other_expense"; occurrence_key=None
                else:
                    status="unmatched_credit"; action="actual_only"; occurrence_key=None
                row.update({"status":status,"candidates":candidates[:8],"suggested_action":action,"suggested_occurrence_key":occurrence_key})
                preview_rows.append(row)
            preview_id=uid()
            already_imported=con.execute("SELECT id FROM bank_statement_imports WHERE account_id=? AND sha256=?",(account_id,parsed["sha256"])).fetchone()
            payload={**parsed,"rows":preview_rows,"account":{"id":account_id,"name":account["name"]},
                "projected_balance_cents":projected_balance,
                "balance_delta_cents":None if closing_balance is None or projected_balance is None else int(closing_balance)-int(projected_balance),
                "already_imported":bool(already_imported)}
            con.execute("INSERT INTO bank_statement_previews(id,household_id,account_id,sha256,file_name,payload) VALUES(?,?,?,?,?,?)",
                (preview_id,hid,account_id,parsed["sha256"],parsed["file_name"],json.dumps(payload,ensure_ascii=False)))
        return {**payload,"preview_id":preview_id}

    def commit_bank_statement_preview(self,hid,account_id,preview_id,decisions,closing_balance_cents,balance_date):
        raise ValueError("Importfunktionen sind in dieser Version vollständig deaktiviert.")
        with self.connect() as con:
            preview=con.execute("SELECT * FROM bank_statement_previews WHERE id=? AND household_id=? AND account_id=?",(preview_id,hid,account_id)).fetchone()
            if not preview: raise ValueError("Die Kontoauszugsvorschau ist abgelaufen oder gehört nicht zu diesem Konto.")
            payload=json.loads(preview["payload"])
        detected_balance=payload["summary"].get("detected_closing_balance_cents")
        detected_date=payload["summary"].get("detected_closing_balance_date") or payload["summary"].get("period_to")
        value=detected_balance if closing_balance_cents in (None,"") else closing_balance_cents
        try:
            closing_balance=int(value)
        except (TypeError,ValueError):
            raise ValueError("Der Endsaldo muss centgenau angegeben werden.")
        balance_date=as_of_date(balance_date or detected_date)
        if balance_date<payload["summary"]["period_from"] or balance_date>payload["summary"]["period_to"]:
            raise ValueError("Das Saldodatum muss innerhalb des Kontoauszugszeitraums liegen.")
        current=self.dashboard(hid,balance_date)
        current_account=next((item for item in current["household"]["accounts"] if item["id"]==account_id),None)
        if not current_account: raise ValueError("Konto gehört nicht zu diesem Haushalt.")
        projected_before=current_account.get("projected_balance_cents")
        delta=None if projected_before is None else closing_balance-int(projected_before)
        decision_by_fingerprint={str(item.get("fingerprint")):item for item in (decisions or []) if item.get("fingerprint")}
        with self.lock,self.connect() as con:
            preview=con.execute("SELECT * FROM bank_statement_previews WHERE id=? AND household_id=? AND account_id=?",(preview_id,hid,account_id)).fetchone()
            if not preview: raise ValueError("Die Kontoauszugsvorschau ist abgelaufen.")
            existing_import=con.execute("SELECT id FROM bank_statement_imports WHERE account_id=? AND sha256=?",(account_id,payload["sha256"])).fetchone()
            if existing_import:
                con.execute("DELETE FROM bank_statement_previews WHERE id=?",(preview_id,))
                return {"id":existing_import["id"],"already_imported":True,"imported_count":0,"duplicate_count":len(payload["rows"]),"created_expense_count":0}
            account=con.execute("SELECT * FROM accounts WHERE id=? AND household_id=?",(account_id,hid)).fetchone()
            if not account: raise ValueError("Konto gehört nicht zu diesem Haushalt.")
            import_id=uid()
            con.execute("""INSERT INTO bank_statement_imports(id,household_id,account_id,sha256,file_name,period_from,period_to,closing_balance_cents,balance_date,summary)
                VALUES(?,?,?,?,?,?,?,?,?,?)""",(import_id,hid,account_id,payload["sha256"],payload["file_name"],payload["summary"]["period_from"],payload["summary"]["period_to"],closing_balance,balance_date,json.dumps(payload["summary"],ensure_ascii=False)))
            imported_count=0; duplicate_count=0; matched_count=0; created_expense_count=0; actual_only_count=0
            for row in payload["rows"]:
                decision=decision_by_fingerprint.get(row["fingerprint"]) or {
                    "action":row.get("suggested_action"),"occurrence_key":row.get("suggested_occurrence_key")}
                action=str(decision.get("action") or "")
                if row.get("status")=="duplicate" or action=="skip":
                    duplicate_count+=1; continue
                if action=="review":
                    raise ValueError(f"Zeile {row['row_no']} ist mehrdeutig und muss vor der Übernahme zugeordnet werden.")
                existing=con.execute("SELECT id FROM bank_transactions WHERE account_id=? AND fingerprint_base=? AND occurrence_no=?",
                    (account_id,row["fingerprint_base"],int(row["occurrence_no"]))).fetchone()
                if existing:
                    duplicate_count+=1; continue
                transaction_id=uid()
                con.execute("""INSERT INTO bank_transactions(id,household_id,account_id,import_id,booking_date,value_date,amount_cents,currency,counterparty,purpose,bank_reference,fingerprint_base,occurrence_no,raw_payload)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(transaction_id,hid,account_id,import_id,row["booking_date"],row.get("value_date"),int(row["amount_cents"]),row.get("currency") or "EUR",row.get("counterparty"),row.get("purpose"),row.get("bank_reference"),row["fingerprint_base"],int(row["occurrence_no"]),json.dumps(row,ensure_ascii=False)))
                imported_count+=1
                if action=="match":
                    occurrence_key=str(decision.get("occurrence_key") or "")
                    candidate=next((item for item in row.get("candidates",[]) if item["occurrence_key"]==occurrence_key),None)
                    if not candidate: raise ValueError(f"Die Zuordnung für Zeile {row['row_no']} ist nicht gültig.")
                    con.execute("""INSERT INTO bank_transaction_matches(id,transaction_id,target_type,target_id,planned_date,occurrence_key,match_method,score)
                        VALUES(?,?,?,?,?,?,?,?)""",(uid(),transaction_id,candidate["target_type"],candidate["target_id"],candidate["date"],candidate["occurrence_key"],"amount-date-text",int(candidate["score"])))
                    matched_count+=1
                elif action=="other_expense":
                    if int(row["amount_cents"])>=0: raise ValueError("Nur Abbuchungen dürfen als sonstige Zahlung angelegt werden.")
                    descriptor=str(row.get("counterparty") or row.get("purpose") or "").strip()[:120]
                    name=f"Sonstige Zahlung · {descriptor}" if descriptor else "Sonstige Zahlung"
                    flow_id=uid(); source_key=f"bank-transaction:{transaction_id}"
                    con.execute("""INSERT INTO cash_flows(id,household_id,kind,name,owner_scope,owner_person_id,account_id,source_key,category)
                        VALUES(?,?,?,?,?,?,?,?,?)""",(flow_id,hid,"expense",name,account["owner_scope"],account["owner_person_id"],account_id,source_key,"other_expense"))
                    con.execute("""INSERT INTO cash_flow_versions(id,cash_flow_id,amount_cents,active,version_from,version_to,stream_start,stream_end,due_date,source_reference,gross_amount_cents,recurrence,name,category,owner_scope,owner_person_id,account_id)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(uid(),flow_id,-int(row["amount_cents"]),1,row["booking_date"],None,row["booking_date"],row["booking_date"],row["booking_date"],f"Kontoauszug {payload['file_name']} · Zeile {row['row_no']}",None,"once",name,"other_expense",account["owner_scope"],account["owner_person_id"],account_id))
                    con.execute("""INSERT INTO bank_transaction_matches(id,transaction_id,target_type,target_id,planned_date,occurrence_key,match_method,score)
                        VALUES(?,?,?,?,?,?,?,?)""",(uid(),transaction_id,"cash_flow",flow_id,row["booking_date"],f"cash-flow:{flow_id}:{row['booking_date']}","created-other-expense",100))
                    created_expense_count+=1
                elif action=="actual_only":
                    actual_only_count+=1
                else:
                    raise ValueError(f"Für Zeile {row['row_no']} fehlt eine gültige Importentscheidung.")
            con.execute("UPDATE account_reconciliations SET status='superseded' WHERE account_id=? AND balance_date=? AND status='active'",(account_id,balance_date))
            reconciliation_id=uid()
            con.execute("""INSERT INTO account_reconciliations(id,household_id,account_id,import_id,balance_date,closing_balance_cents,projected_before_cents,delta_cents,status)
                VALUES(?,?,?,?,?,?,?,?,?)""",(reconciliation_id,hid,account_id,import_id,balance_date,closing_balance,projected_before,delta,"active"))
            con.execute("DELETE FROM bank_statement_previews WHERE id=?",(preview_id,))
        return {"id":import_id,"reconciliation_id":reconciliation_id,"already_imported":False,
            "imported_count":imported_count,"duplicate_count":duplicate_count,"matched_count":matched_count,
            "created_expense_count":created_expense_count,"actual_only_count":actual_only_count,
            "closing_balance_cents":closing_balance,"balance_date":balance_date,
            "projected_before_cents":projected_before,"delta_cents":delta}

    def list_bank_statements(self,hid,account_id):
        raise ValueError("Importfunktionen sind in dieser Version vollständig deaktiviert.")
        with self.connect() as con:
            if not con.execute("SELECT 1 FROM accounts WHERE id=? AND household_id=?",(account_id,hid)).fetchone():
                raise ValueError("Konto gehört nicht zu diesem Haushalt.")
            rows=con.execute("""SELECT i.id,i.file_name,i.period_from,i.period_to,i.closing_balance_cents,i.balance_date,i.created_at,
                    COUNT(t.id) AS transaction_count
                FROM bank_statement_imports i LEFT JOIN bank_transactions t ON t.import_id=i.id
                WHERE i.household_id=? AND i.account_id=? GROUP BY i.id ORDER BY i.created_at DESC""",(hid,account_id)).fetchall()
            return [dict(row) for row in rows]

    def dashboard(self,hid,as_of=None):
        selected_date=as_of_date(as_of)
        detail=self.household_detail(hid,selected_date)
        if not detail: raise KeyError("household")
        with self.connect() as con:
            unassigned_projection=self.projected_account_balances(con,hid,detail["accounts"],selected_date)
            def monthly_values(kind):
                rows=con.execute("""SELECT COALESCE(v.name,f.name) AS name,v.amount_cents,v.recurrence,v.due_date FROM cash_flow_versions v JOIN cash_flows f ON f.id=v.cash_flow_id
                    WHERE f.household_id=? AND f.kind=? AND v.active=1 AND v.version_from<=? AND (v.version_to IS NULL OR v.version_to>?)
                    AND (v.stream_start IS NULL OR v.stream_start<=?) AND (v.stream_end IS NULL OR v.stream_end>=?)""",(hid,kind,selected_date,selected_date,selected_date,selected_date)).fetchall()
                values=[]
                for row in rows:
                    recurrence=row["recurrence"] or "monthly"; amount=int(row["amount_cents"] or 0)
                    if recurrence=="once": contribution=amount if str(row["due_date"] or "")[:7]==selected_date[:7] else 0
                    else:
                        divisor={"monthly":1,"quarterly":3,"yearly":12}.get(recurrence,1)
                        contribution=int((Decimal(amount)/Decimal(divisor)).quantize(Decimal("1"),rounding=ROUND_HALF_UP))
                    if contribution: values.append({"label":row["name"],"amount_cents":contribution})
                return values
            income_items=monthly_values("income"); expense_items=monthly_values("expense")
            income=sum(item["amount_cents"] for item in income_items)
            expenses=sum(item["amount_cents"] for item in expense_items)
            balances=sum((a["projected_balance_cents"] or 0) for a in detail["accounts"] if a["projected_balance_cents"] is not None)
        warning_accounts=[account for account in detail["accounts"] if account.get("overdraft_exceeded")]
        return {"as_of":selected_date,"household":detail,"metrics":{"balance_cents":balances,
            "income_cents":income,"expenses_cents":expenses,"surplus_cents":income-expenses,
            "unassigned_projection_count":unassigned_projection["event_count"],
            "unassigned_projection_cents":unassigned_projection["net_cents"],
            "overdraft_warning_count":len(warning_accounts)},
            "breakdowns":{"income":income_items,"expenses":expense_items},
            "overdraft_warnings":[{"account_id":account["id"],"name":account["name"],
                "overage_cents":account["overdraft_overage_cents"],"projected_balance_cents":account["projected_balance_cents"],
                "overdraft_limit_cents":account["overdraft_limit_cents"]} for account in warning_accounts]}
