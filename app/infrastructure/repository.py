import hashlib
import json
import os
import secrets
import sqlite3
from calendar import monthrange
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from threading import RLock
from uuid import uuid4

from app.domain.recurrence import (
    RECURRENCE_MONTHS,
    add_months_anchored,
    last_occurrence_date,
    last_occurrence_on_or_before,
    planned_booking_dates,
    recurrence_dates,
)

APP_VERSION = "1.6.1"

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
CREATE TABLE IF NOT EXISTS credits(
 id TEXT PRIMARY KEY, household_id TEXT NOT NULL REFERENCES households(id) ON DELETE CASCADE,
 name TEXT NOT NULL, credit_type TEXT NOT NULL CHECK(credit_type IN('consumer_credit','credit','borrowed')),
 opening_balance_cents INTEGER NOT NULL, interest_rate TEXT,
 automatic_interest INTEGER NOT NULL DEFAULT 0, balloon_payment_cents INTEGER NOT NULL DEFAULT 0, note TEXT,
 provider TEXT, product_price_cents INTEGER, financing_price_cents INTEGER, installment_surcharge_cents INTEGER,
 payment_count INTEGER,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(household_id,name));
CREATE TABLE IF NOT EXISTS credit_payments(
 id TEXT PRIMARY KEY, household_id TEXT NOT NULL REFERENCES households(id) ON DELETE CASCADE,
 credit_id TEXT NOT NULL REFERENCES credits(id) ON DELETE CASCADE,
 payment_date TEXT NOT NULL, amount_cents INTEGER NOT NULL, note TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS credit_payments_dates ON credit_payments(credit_id,payment_date);
CREATE TABLE IF NOT EXISTS credit_interest_bookings(
 id TEXT PRIMARY KEY, household_id TEXT NOT NULL REFERENCES households(id) ON DELETE CASCADE,
 credit_id TEXT NOT NULL REFERENCES credits(id) ON DELETE CASCADE,
 booking_date TEXT NOT NULL, amount_cents INTEGER NOT NULL,
 account_id TEXT REFERENCES accounts(id) ON DELETE SET NULL,
 cash_flow_id TEXT REFERENCES cash_flows(id) ON DELETE SET NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS credit_interest_bookings_dates ON credit_interest_bookings(household_id,booking_date);
CREATE TABLE IF NOT EXISTS cash_flows(
 id TEXT PRIMARY KEY, household_id TEXT NOT NULL REFERENCES households(id) ON DELETE CASCADE,
 kind TEXT NOT NULL, name TEXT NOT NULL, owner_scope TEXT NOT NULL,
 owner_person_id TEXT REFERENCES persons(id), account_id TEXT REFERENCES accounts(id),
 source_key TEXT, source_provider TEXT, source_segment_id TEXT, source_contract_id TEXT,
 category TEXT NOT NULL DEFAULT 'other', UNIQUE(household_id,source_key));
CREATE TABLE IF NOT EXISTS cash_flow_versions(
 id TEXT PRIMARY KEY, cash_flow_id TEXT NOT NULL REFERENCES cash_flows(id) ON DELETE CASCADE,
 amount_cents INTEGER NOT NULL, active INTEGER NOT NULL, version_from TEXT NOT NULL, version_to TEXT,
 stream_start TEXT, stream_end TEXT, due_date TEXT, source_reference TEXT,
 gross_amount_cents INTEGER, recurrence TEXT NOT NULL DEFAULT 'monthly', name TEXT, category TEXT,
 owner_scope TEXT, owner_person_id TEXT, account_id TEXT,
 credit_id TEXT, credit_reduction_cents INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS energylab_integrations(
 household_id TEXT PRIMARY KEY REFERENCES households(id) ON DELETE CASCADE,
 base_url TEXT NOT NULL, account_id TEXT REFERENCES accounts(id) ON DELETE SET NULL,
 enabled INTEGER NOT NULL DEFAULT 1, last_sync_at TEXT, last_status TEXT,
 last_message TEXT, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS energylab_account_overrides(
 household_id TEXT NOT NULL REFERENCES households(id) ON DELETE CASCADE,
 source_key TEXT NOT NULL, account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
 payment_day INTEGER,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(household_id,source_key));
CREATE TABLE IF NOT EXISTS energylab_sync_runs(
 id TEXT PRIMARY KEY, household_id TEXT NOT NULL REFERENCES households(id) ON DELETE CASCADE,
 status TEXT NOT NULL CHECK(status IN('preview','ok','error')), source_version TEXT,
 payload_sha256 TEXT, contracts INTEGER NOT NULL DEFAULT 0,
 created INTEGER NOT NULL DEFAULT 0, updated INTEGER NOT NULL DEFAULT 0,
 unchanged INTEGER NOT NULL DEFAULT 0, deactivated INTEGER NOT NULL DEFAULT 0,
 message TEXT, started_at TEXT NOT NULL, finished_at TEXT NOT NULL,
 UNIQUE(household_id,status,payload_sha256,finished_at));
CREATE INDEX IF NOT EXISTS energylab_sync_runs_history
 ON energylab_sync_runs(household_id,finished_at DESC);
CREATE TABLE IF NOT EXISTS energylab_sync_items(
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES energylab_sync_runs(id) ON DELETE CASCADE,
 household_id TEXT NOT NULL REFERENCES households(id) ON DELETE CASCADE,
 source_key TEXT NOT NULL, action TEXT NOT NULL,
 before_payload TEXT, after_payload TEXT, created_at TEXT NOT NULL,
 UNIQUE(run_id,source_key));
CREATE INDEX IF NOT EXISTS energylab_sync_items_source
 ON energylab_sync_items(household_id,source_key,created_at DESC);
CREATE TABLE IF NOT EXISTS energylab_payment_events(
 id TEXT PRIMARY KEY, household_id TEXT NOT NULL REFERENCES households(id) ON DELETE CASCADE,
 source_key TEXT NOT NULL, occurrence_date TEXT NOT NULL, booking_date TEXT,
 planned_amount_cents INTEGER, actual_amount_cents INTEGER NOT NULL,
 event_type TEXT NOT NULL CHECK(event_type IN('payment','refund','chargeback','correction','skipped')),
 canonical_event_type TEXT,
 status TEXT NOT NULL CHECK(status IN('pending','confirmed','reversed','ignored')),
 bank_transaction_id TEXT REFERENCES bank_transactions(id) ON DELETE SET NULL,
 external_id TEXT, note TEXT, confirmed INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL, supersedes_event_id TEXT REFERENCES energylab_payment_events(id),
 UNIQUE(household_id,external_id));
CREATE INDEX IF NOT EXISTS energylab_payment_events_contract
 ON energylab_payment_events(household_id,source_key,occurrence_date,created_at);
CREATE TABLE IF NOT EXISTS energylab_billing_snapshots(
 id TEXT PRIMARY KEY, household_id TEXT NOT NULL REFERENCES households(id) ON DELETE CASCADE,
 segment_id TEXT NOT NULL, contract_id TEXT NOT NULL,
 period_from TEXT NOT NULL, period_to TEXT NOT NULL, revision INTEGER NOT NULL,
 status TEXT NOT NULL DEFAULT 'final', payload_sha256 TEXT NOT NULL,
 statement_payload TEXT NOT NULL, planned_total_cents INTEGER NOT NULL DEFAULT 0,
 actual_total_cents INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
 supersedes_snapshot_id TEXT REFERENCES energylab_billing_snapshots(id),
 UNIQUE(household_id,segment_id,contract_id,period_from,period_to,revision));
CREATE INDEX IF NOT EXISTS energylab_billing_snapshot_lookup
 ON energylab_billing_snapshots(household_id,segment_id,contract_id,period_from,period_to,revision DESC);
CREATE TABLE IF NOT EXISTS energylab_billing_snapshot_items(
 id TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL REFERENCES energylab_billing_snapshots(id) ON DELETE CASCADE,
 payment_event_id TEXT, occurrence_date TEXT NOT NULL,
 planned_amount_cents INTEGER, actual_amount_cents INTEGER NOT NULL,
 event_type TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL,
 UNIQUE(snapshot_id,id));
CREATE TABLE IF NOT EXISTS app_backups(
 id TEXT PRIMARY KEY, file_name TEXT NOT NULL UNIQUE, reason TEXT,
 database_sha256 TEXT NOT NULL, size_bytes INTEGER NOT NULL,
 created_at TEXT NOT NULL, restored_at TEXT);
CREATE TABLE IF NOT EXISTS transfers(
 id TEXT PRIMARY KEY, household_id TEXT NOT NULL REFERENCES households(id) ON DELETE CASCADE,
 name TEXT NOT NULL, source_account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
 target_account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
 amount_cents INTEGER NOT NULL, recurrence TEXT NOT NULL DEFAULT 'once', due_date TEXT NOT NULL,
 end_date TEXT, occurrence_count INTEGER,
 active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS transfers_projection ON transfers(household_id,due_date,active);
CREATE TABLE IF NOT EXISTS movement_completions(
 id TEXT PRIMARY KEY, household_id TEXT NOT NULL REFERENCES households(id) ON DELETE CASCADE,
 occurrence_key TEXT NOT NULL, source_type TEXT NOT NULL CHECK(source_type IN('cash_flow','transfer')),
 source_id TEXT NOT NULL, occurrence_date TEXT NOT NULL, completed_at TEXT NOT NULL,
 UNIQUE(household_id,occurrence_key));
CREATE INDEX IF NOT EXISTS movement_completions_source
 ON movement_completions(household_id,source_type,source_id,occurrence_date);
CREATE TABLE IF NOT EXISTS movement_amount_overrides(
 id TEXT PRIMARY KEY, household_id TEXT NOT NULL REFERENCES households(id) ON DELETE CASCADE,
 occurrence_key TEXT NOT NULL, cash_flow_id TEXT NOT NULL REFERENCES cash_flows(id) ON DELETE CASCADE,
 occurrence_date TEXT NOT NULL, amount_cents INTEGER NOT NULL CHECK(amount_cents >= 0),
 updated_at TEXT NOT NULL,
 UNIQUE(household_id,occurrence_key));
CREATE INDEX IF NOT EXISTS movement_amount_overrides_source
 ON movement_amount_overrides(household_id,cash_flow_id,occurrence_date);
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

def energylab_first_due(start_date,payment_day,recurrence,active_from=None,explicit_first=None):
    """Find the first effective due date without changing the contract cadence."""
    interval=RECURRENCE_MONTHS.get(recurrence,1)
    if explicit_first:
        due=explicit_first
    else:
        due=date(start_date.year,start_date.month,min(payment_day,monthrange(start_date.year,start_date.month)[1]))
        if due<start_date: due=add_months_anchored(due,interval)
    active=active_from or start_date
    while due<active: due=add_months_anchored(due,interval)
    return due

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

def inferred_nominal_apr(principal_cents,payment_cents,occurrence_count,balloon_cents=0):
    """Infer a nominal annual rate from a bounded monthly instalment plan."""
    try:
        principal=Decimal(int(principal_cents)); payment=Decimal(int(payment_cents))
        count=int(occurrence_count); balloon=Decimal(int(balloon_cents or 0))
    except (TypeError,ValueError,InvalidOperation):
        return None
    if principal<=0 or payment<=0 or count<1 or balloon<0 or balloon>principal:
        return None
    total=payment*count+balloon
    if total<principal:
        return None
    if total==principal:
        return "0"

    def present_value(monthly_rate):
        factor=Decimal(1)+monthly_rate
        discount=Decimal(1); value=Decimal(0)
        for _ in range(count):
            discount*=factor
            value+=payment/discount
        return value+balloon/discount

    low=Decimal(0); high=Decimal("0.01")
    while present_value(high)>principal and high<Decimal(10):
        high*=2
    if present_value(high)>principal:
        return None
    for _ in range(96):
        middle=(low+high)/2
        if present_value(middle)>principal:
            low=middle
        else:
            high=middle
    annual_percent=((low+high)/2*Decimal(1200)).quantize(Decimal("0.0001"),rounding=ROUND_HALF_UP)
    return format(annual_percent.normalize(),"f")

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

def normalized_match_tokens(*values):
    """Return conservative, provider-friendly tokens used for bank matching."""
    text=" ".join(str(value or "") for value in values).casefold()
    token=""; result=set()
    for character in text:
        if character.isalnum():
            token+=character
        elif token:
            if len(token)>=3: result.add(token)
            token=""
    if token and len(token)>=3: result.add(token)
    ignored={"gmbh","ag","kg","se","energie","energylab","zahlung","abschlag","rechnung"}
    return result-ignored

class Repository:
    def __init__(self, path=None):
        if path is None:
            data_dir=Path(os.environ.get("DATA_DIR","data")); data_dir.mkdir(parents=True,exist_ok=True); path=data_dir/"planner.db"
        else: Path(path).parent.mkdir(parents=True,exist_ok=True)
        self.path=str(path); self.lock=RLock()
        upgrade_backup=self._prepare_upgrade_backup()
        self.initialize()
        if upgrade_backup:
            with self.lock,self.connect() as con:
                con.execute("""INSERT OR IGNORE INTO app_backups(
                    id,file_name,reason,database_sha256,size_bytes,created_at
                ) VALUES(?,?,?,?,?,?)""",(
                    upgrade_backup["id"],upgrade_backup["file_name"],upgrade_backup["reason"],
                    upgrade_backup["database_sha256"],upgrade_backup["size_bytes"],upgrade_backup["created_at"],
                ))
        marker=self._upgrade_marker(); marker.parent.mkdir(parents=True,exist_ok=True)
        marker.write_text(APP_VERSION+"\n",encoding="utf-8")

    def _upgrade_marker(self):
        return Path(self.path).resolve().parent/"backups"/f".finanzlab-upgrade-{APP_VERSION}.done"

    def _prepare_upgrade_backup(self):
        """Create one consistent safety copy before this release migrates an existing database."""
        database=Path(self.path)
        marker=self._upgrade_marker()
        if marker.exists() or not database.is_file() or database.stat().st_size<=0:
            return None
        backup_dir=marker.parent; backup_dir.mkdir(parents=True,exist_ok=True)
        backup_id=uid(); compact=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        file_name=f"finanzlab-before-{APP_VERSION}-{compact}-{backup_id[:8]}.sqlite3"
        target=backup_dir/file_name
        source=sqlite3.connect(database); destination=sqlite3.connect(target)
        try: source.backup(destination)
        finally: destination.close(); source.close()
        return {
            "id":backup_id,"file_name":file_name,
            "reason":f"automatisch vor Update auf {APP_VERSION}",
            "database_sha256":hashlib.sha256(target.read_bytes()).hexdigest(),
            "size_bytes":target.stat().st_size,"created_at":timestamp(),
        }
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
            self.ensure_column(con,"cash_flows","source_provider","TEXT")
            self.ensure_column(con,"cash_flows","source_segment_id","TEXT")
            self.ensure_column(con,"cash_flows","source_contract_id","TEXT")
            self.ensure_column(con,"cash_flow_versions","gross_amount_cents","INTEGER")
            self.ensure_column(con,"cash_flow_versions","recurrence","TEXT NOT NULL DEFAULT 'monthly'")
            self.ensure_column(con,"cash_flow_versions","name","TEXT")
            self.ensure_column(con,"cash_flow_versions","category","TEXT")
            self.ensure_column(con,"cash_flow_versions","owner_scope","TEXT")
            self.ensure_column(con,"cash_flow_versions","owner_person_id","TEXT")
            self.ensure_column(con,"cash_flow_versions","account_id","TEXT")
            self.ensure_column(con,"cash_flow_versions","credit_id","TEXT")
            self.ensure_column(con,"cash_flow_versions","credit_reduction_cents","INTEGER NOT NULL DEFAULT 0")
            self.ensure_column(con,"credits","interest_rate","TEXT")
            self.ensure_column(con,"credits","automatic_interest","INTEGER NOT NULL DEFAULT 0")
            self.ensure_column(con,"credits","balloon_payment_cents","INTEGER NOT NULL DEFAULT 0")
            self.ensure_column(con,"credits","provider","TEXT")
            self.ensure_column(con,"credits","product_price_cents","INTEGER")
            self.ensure_column(con,"credits","financing_price_cents","INTEGER")
            self.ensure_column(con,"credits","installment_surcharge_cents","INTEGER")
            self.ensure_column(con,"credits","payment_count","INTEGER")
            con.execute("""CREATE TABLE IF NOT EXISTS credit_interest_bookings(
                id TEXT PRIMARY KEY, household_id TEXT NOT NULL REFERENCES households(id) ON DELETE CASCADE,
                credit_id TEXT NOT NULL REFERENCES credits(id) ON DELETE CASCADE,
                booking_date TEXT NOT NULL, amount_cents INTEGER NOT NULL,
                account_id TEXT REFERENCES accounts(id) ON DELETE SET NULL,
                cash_flow_id TEXT REFERENCES cash_flows(id) ON DELETE SET NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
            con.execute("CREATE INDEX IF NOT EXISTS credit_interest_bookings_dates ON credit_interest_bookings(household_id,booking_date)")
            self.ensure_column(con,"accounts","is_default","INTEGER NOT NULL DEFAULT 0")
            self.ensure_column(con,"balance_anchors","created_at","TEXT")
            self.ensure_column(con,"balance_anchors","bookings_applied","INTEGER NOT NULL DEFAULT 1")
            self.ensure_column(con,"transfers","end_date","TEXT")
            self.ensure_column(con,"transfers","occurrence_count","INTEGER")
            self.ensure_column(con,"energylab_account_overrides","payment_day","INTEGER")
            self.ensure_column(con,"energylab_integrations","callback_token","TEXT")
            self.ensure_column(con,"energylab_integrations","last_payload_sha256","TEXT")
            self.ensure_column(con,"energylab_payment_events","booking_date","TEXT")
            self.ensure_column(con,"energylab_payment_events","canonical_event_type","TEXT")
            self.ensure_column(con,"bank_transaction_matches","confirmed","INTEGER NOT NULL DEFAULT 0")
            self.ensure_column(con,"bank_transaction_matches","status","TEXT NOT NULL DEFAULT 'confirmed'")
            self.ensure_column(con,"bank_transaction_matches","reversal_of_transaction_id","TEXT")
            con.execute("""UPDATE energylab_payment_events SET
                booking_date=COALESCE(booking_date,occurrence_date),
                canonical_event_type=COALESCE(canonical_event_type,CASE event_type
                    WHEN 'payment' THEN 'regular_payment'
                    WHEN 'refund' THEN 'credit_payout'
                    WHEN 'chargeback' THEN 'chargeback'
                    WHEN 'correction' THEN 'correction'
                    WHEN 'skipped' THEN 'suspension' END)""")
            legacy_match_confirmation=con.execute(
                "SELECT 1 FROM schema_migrations WHERE name='v1.3-confirm-legacy-bank-matches'"
            ).fetchone()
            if not legacy_match_confirmation:
                # In 1.1.2 a persisted match was already the result of the
                # account-statement import decision.  The new column must not
                # turn those accepted matches into unconfirmed suggestions.
                con.execute("""UPDATE bank_transaction_matches
                    SET confirmed=1,status='confirmed'
                    WHERE confirmed=0 AND status='confirmed'""")
                con.execute(
                    "INSERT INTO schema_migrations(name) VALUES('v1.3-confirm-legacy-bank-matches')"
                )
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
            future_cleanup=con.execute(
                "SELECT 1 FROM schema_migrations WHERE name='v0.13-collapse-hidden-future-flow-versions'"
            ).fetchone()
            if not future_cleanup:
                # "Gültig ab/bis" is no longer editable in the application.
                # Older releases could nevertheless leave a future version
                # behind.  Such a hidden row silently replaced the visible
                # configuration on its version date and made recurring
                # payments disappear from the forecast.  Keep the historic
                # version that is effective today and make it authoritative
                # for the future.
                today=date.today().isoformat()
                for flow in con.execute("SELECT id FROM cash_flows").fetchall():
                    current=con.execute("""SELECT id,substr(version_from,1,10) AS version_day
                        FROM cash_flow_versions
                        WHERE cash_flow_id=? AND substr(version_from,1,10)<=?
                        ORDER BY substr(version_from,1,10) DESC,rowid DESC LIMIT 1""",
                        (flow["id"],today)).fetchone()
                    if not current:
                        continue
                    con.execute("""DELETE FROM cash_flow_versions
                        WHERE cash_flow_id=? AND id<>? AND substr(version_from,1,10)>=?""",
                        (flow["id"],current["id"],current["version_day"]))
                    con.execute("UPDATE cash_flow_versions SET version_to=NULL WHERE id=?",(current["id"],))
                con.execute("INSERT INTO schema_migrations(name) VALUES('v0.13-collapse-hidden-future-flow-versions')")
            for household in con.execute("SELECT id FROM households").fetchall():
                if not con.execute("SELECT 1 FROM accounts WHERE household_id=? AND is_default=1",(household["id"],)).fetchone():
                    first=con.execute("SELECT id FROM accounts WHERE household_id=? ORDER BY created_at,id LIMIT 1",(household["id"],)).fetchone()
                    if first: con.execute("UPDATE accounts SET is_default=1 WHERE id=?",(first["id"],))
            con.execute("CREATE UNIQUE INDEX IF NOT EXISTS accounts_one_default ON accounts(household_id) WHERE is_default=1")
            con.execute("CREATE UNIQUE INDEX IF NOT EXISTS energylab_payment_event_external ON energylab_payment_events(household_id,external_id) WHERE external_id IS NOT NULL")
            # Import history, payment events and billing revisions are append-only.
            # Cascading household deletion remains possible because the parent row
            # no longer exists when SQLite executes its child cascades.
            for table in ("energylab_sync_runs","energylab_sync_items","energylab_payment_events","energylab_billing_snapshots"):
                con.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_no_update
                    BEFORE UPDATE ON {table} BEGIN
                    SELECT RAISE(ABORT,'Historieneinträge sind unveränderlich'); END""")
                con.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_no_delete
                    BEFORE DELETE ON {table}
                    WHEN EXISTS(SELECT 1 FROM households WHERE id=OLD.household_id)
                    BEGIN SELECT RAISE(ABORT,'Historieneinträge sind unveränderlich'); END""")
            con.execute("""CREATE TRIGGER IF NOT EXISTS energylab_billing_snapshot_items_no_update
                BEFORE UPDATE ON energylab_billing_snapshot_items BEGIN
                SELECT RAISE(ABORT,'Abrechnungssnapshots sind unveränderlich'); END""")
            con.execute("""CREATE TRIGGER IF NOT EXISTS energylab_billing_snapshot_items_no_delete
                BEFORE DELETE ON energylab_billing_snapshot_items
                WHEN EXISTS(SELECT 1 FROM energylab_billing_snapshots s
                    JOIN households h ON h.id=s.household_id WHERE s.id=OLD.snapshot_id)
                BEGIN SELECT RAISE(ABORT,'Abrechnungssnapshots sind unveränderlich'); END""")
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
        account_anchor_date=None; account_balance_cents=0
        if account_name:
            account_anchor_date=as_of_date(account.get("anchor_date"))
            try: account_balance_cents=int(account.get("balance_cents") or 0)
            except (TypeError,ValueError): raise ValueError("Der Kontostand muss ein gültiger Geldwert sein.")
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
                    (uid(),hid,account_id,account_anchor_date,account_balance_cents,1 if account.get("bookings_applied") else 0))
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
    def delete_account(self,hid,account_id):
        if not hid or not account_id: raise ValueError("Haushalt und Konto sind erforderlich.")
        with self.lock,self.connect() as con:
            account=con.execute("SELECT id,name,is_default FROM accounts WHERE id=? AND household_id=?",(account_id,hid)).fetchone()
            if not account: raise ValueError("Konto nicht gefunden.")
            flow_count=con.execute("""SELECT COUNT(DISTINCT f.id) FROM cash_flows f
                LEFT JOIN cash_flow_versions v ON v.cash_flow_id=f.id
                WHERE f.household_id=? AND (f.account_id=? OR v.account_id=?)""",(hid,account_id,account_id)).fetchone()[0]
            transfer_rows=con.execute("SELECT id FROM transfers WHERE household_id=? AND (source_account_id=? OR target_account_id=?)",(hid,account_id,account_id)).fetchall()
            transfer_ids=[row["id"] for row in transfer_rows]
            transfer_count=len(transfer_ids)
            history_count=con.execute("SELECT COUNT(*) FROM balance_anchors WHERE account_id=?",(account_id,)).fetchone()[0]
            history_count+=con.execute("SELECT COUNT(*) FROM account_reconciliations WHERE account_id=?",(account_id,)).fetchone()[0]
            con.execute("UPDATE cash_flows SET account_id=NULL WHERE household_id=? AND account_id=?",(hid,account_id))
            con.execute("UPDATE cash_flow_versions SET account_id=NULL WHERE account_id=?",(account_id,))
            if transfer_ids:
                placeholders=",".join("?" for _ in transfer_ids)
                con.execute(f"DELETE FROM movement_completions WHERE household_id=? AND source_type='transfer' AND source_id IN ({placeholders})",(hid,*transfer_ids))
            con.execute("DELETE FROM accounts WHERE id=? AND household_id=?",(account_id,hid))
            if account["is_default"]:
                replacement=con.execute("SELECT id FROM accounts WHERE household_id=? ORDER BY created_at,id LIMIT 1",(hid,)).fetchone()
                if replacement: con.execute("UPDATE accounts SET is_default=1 WHERE id=?",(replacement["id"],))
        return {"id":account_id,"name":account["name"],"deleted":True,
            "unassigned_cash_flow_count":int(flow_count),"deleted_transfer_count":int(transfer_count),
            "deleted_history_count":int(history_count)}
    def delete_household(self,hid):
        if not hid: raise ValueError("Haushalt ist erforderlich.")
        with self.lock,self.connect() as con:
            household=con.execute("SELECT id,name FROM households WHERE id=?",(hid,)).fetchone()
            if not household: raise ValueError("Haushalt nicht gefunden.")
            con.execute("DELETE FROM households WHERE id=?",(hid,))
        return {"id":hid,"name":household["name"],"deleted":True}
    def credit_values(self,con,payload):
        hid=payload.get("household_id"); name=str(payload.get("name") or "").strip()
        credit_type=str(payload.get("credit_type") or "")
        if not hid or not name: raise ValueError("Haushalt und Kreditname sind erforderlich.")
        if credit_type not in ("consumer_credit","credit","borrowed"):
            raise ValueError("Die Kreditart muss Konsumkredit, Kredit oder Geliehen sein.")
        if not con.execute("SELECT 1 FROM households WHERE id=?",(hid,)).fetchone():
            raise ValueError("Haushalt nicht gefunden.")
        try: opening_balance_cents=int(payload.get("opening_balance_cents") or 0)
        except (TypeError,ValueError): raise ValueError("Der Anfangssaldo muss ein gültiger Geldwert sein.")
        if opening_balance_cents<0: raise ValueError("Der Anfangssaldo darf nicht negativ sein.")
        interest_raw=payload.get("interest_rate")
        if interest_raw in (None,""):
            interest_rate=None
        else:
            try: interest=Decimal(str(interest_raw).replace(",","."))
            except (InvalidOperation,ValueError): raise ValueError("Der Sollzinssatz muss eine gültige Zahl sein.")
            if not interest.is_finite() or interest<0:
                raise ValueError("Der Sollzinssatz darf nicht negativ sein.")
            interest_rate=format(interest.normalize(),"f")
        automatic_interest=0 if payload.get("automatic_interest") in (False,0,"0",None,"") else 1
        try: balloon_payment_cents=int(payload.get("balloon_payment_cents") or 0)
        except (TypeError,ValueError): raise ValueError("Die vertragliche Restschuld muss ein gültiger Geldwert sein.")
        if balloon_payment_cents<0 or balloon_payment_cents>opening_balance_cents:
            raise ValueError("Die vertragliche Restschuld muss zwischen 0,00 € und dem Anfangssaldo liegen.")
        provider=str(payload.get("provider") or "").strip() or None
        if credit_type!="consumer_credit": provider=None
        def optional_money(key):
            raw=payload.get(key)
            if raw in (None,""): return None
            try: value=int(raw)
            except (TypeError,ValueError): raise ValueError("Produkt- und Finanzierungspreise müssen gültige Geldwerte sein.")
            if value<0: raise ValueError("Produkt- und Finanzierungspreise dürfen nicht negativ sein.")
            return value
        product_price_cents=optional_money("product_price_cents")
        financing_price_cents=optional_money("financing_price_cents")
        installment_surcharge_cents=optional_money("installment_surcharge_cents")
        plan=payload.get("payment_plan") if isinstance(payload.get("payment_plan"),dict) else {}
        payment_count_raw=(plan.get("occurrence_count") if plan else payload.get("payment_count"))
        payment_count=None
        if payment_count_raw not in (None,""):
            try: payment_count=int(payment_count_raw)
            except (TypeError,ValueError): raise ValueError("Die Zahlungsanzahl muss eine ganze Zahl sein.")
            if str(payment_count_raw).strip()!=str(payment_count) or not 1<=payment_count<=1200:
                raise ValueError("Die Zahlungsanzahl muss zwischen 1 und 1.200 liegen.")
        if financing_price_cents is None and plan.get("amount_cents") not in (None,"") and plan.get("occurrence_count") not in (None,""):
            try:
                financing_price_cents=int(plan["amount_cents"])*int(plan["occurrence_count"])+balloon_payment_cents
            except (TypeError,ValueError):
                raise ValueError("Rate und Zahlungsanzahl müssen gültige Zahlen sein.")
        if installment_surcharge_cents is None and product_price_cents is not None and financing_price_cents is not None:
            installment_surcharge_cents=max(0,financing_price_cents-product_price_cents)
        elif financing_price_cents is None and product_price_cents is not None and installment_surcharge_cents is not None:
            financing_price_cents=product_price_cents+installment_surcharge_cents
        elif product_price_cents is None and financing_price_cents is not None and installment_surcharge_cents is not None:
            product_price_cents=max(0,financing_price_cents-installment_surcharge_cents)
        # The product price is the financed principal. The financing price
        # already includes all financing costs and must not be financed again.
        # Preserve explicitly different balances and repair only the old default.
        if (credit_type=="consumer_credit" and automatic_interest and product_price_cents is not None
                and (opening_balance_cents==0 or opening_balance_cents==financing_price_cents)):
            opening_balance_cents=product_price_cents
            if balloon_payment_cents>opening_balance_cents:
                raise ValueError("Die vertragliche Restschuld darf den Produktpreis nicht übersteigen.")
        if (credit_type=="consumer_credit" and financing_price_cents is not None
                and plan.get("amount_cents") not in (None,"") and payment_count is not None):
            try: contractual_total=int(plan["amount_cents"])*payment_count+balloon_payment_cents
            except (TypeError,ValueError): raise ValueError("Rate und Zahlungsanzahl müssen gültige Zahlen sein.")
            rounding_tolerance=max(5,payment_count)
            if abs(contractual_total-financing_price_cents)>rounding_tolerance:
                raise ValueError(
                    "Monatsrate, Zahlungsanzahl und Schlussrate passen nicht zum Finanzierungspreis."
                )
        note=str(payload.get("note") or "").strip() or None
        return {"household_id":hid,"name":name,"credit_type":credit_type,
            "opening_balance_cents":opening_balance_cents,"interest_rate":interest_rate,
            "automatic_interest":automatic_interest,"balloon_payment_cents":balloon_payment_cents,"note":note,
            "provider":provider,"product_price_cents":product_price_cents,
            "financing_price_cents":financing_price_cents,"installment_surcharge_cents":installment_surcharge_cents,
            "payment_count":payment_count}
    def create_credit(self,payload):
        with self.lock,self.connect() as con:
            values=self.credit_values(con,payload)
            if con.execute("SELECT 1 FROM credits WHERE household_id=? AND name=?",(values["household_id"],values["name"])).fetchone():
                raise ValueError("Ein Kredit mit diesem Namen existiert bereits.")
            credit_id=uid()
            con.execute("""INSERT INTO credits(id,household_id,name,credit_type,opening_balance_cents,
                interest_rate,automatic_interest,balloon_payment_cents,note,provider,product_price_cents,
                financing_price_cents,installment_surcharge_cents,payment_count) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (credit_id,values["household_id"],values["name"],values["credit_type"],values["opening_balance_cents"],
                 values["interest_rate"],values["automatic_interest"],values["balloon_payment_cents"],values["note"],
                 values["provider"],values["product_price_cents"],values["financing_price_cents"],values["installment_surcharge_cents"],
                 values["payment_count"]))
            plan=payload.get("payment_plan")
            if plan:
                plan_payload={
                    "household_id":values["household_id"],"kind":"expense","name":values["name"],
                    "category":values["credit_type"],"amount_cents":plan.get("amount_cents"),
                    "recurrence":"monthly","due_date":plan.get("first_due_date"),
                    "duration_months":plan.get("occurrence_count"),"account_id":plan.get("account_id"),
                    "credit_id":credit_id,"credit_reduction_cents":"","owner":plan.get("owner") or "A",
                    "active":True,
                }
                plan_values=self.cash_flow_values(con,plan_payload,"expense")
                flow_id=uid()
                con.execute("""INSERT INTO cash_flows(id,household_id,kind,name,owner_scope,owner_person_id,account_id,source_key,category)
                    VALUES(?,?,?,?,?,?,?,?,?)""",(flow_id,values["household_id"],"expense",values["name"],
                    plan_values["owner_scope"],plan_values["owner_person_id"],plan_values["account_id"],
                    f"credit-plan:{credit_id}",values["credit_type"]))
                con.execute("""INSERT INTO cash_flow_versions(id,cash_flow_id,amount_cents,active,version_from,version_to,
                    stream_start,stream_end,due_date,source_reference,gross_amount_cents,recurrence,name,category,
                    owner_scope,owner_person_id,account_id,credit_id,credit_reduction_cents)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(uid(),flow_id,plan_values["amount_cents"],1,
                    plan_values["effective_from"],None,plan_values["effective_from"],plan_values["stream_end"],
                    plan_values["due_date"],"Automatisch aus Kredit",None,"monthly",values["name"],values["credit_type"],
                    plan_values["owner_scope"],plan_values["owner_person_id"],plan_values["account_id"],credit_id,
                    plan_values["credit_reduction_cents"]))
        return self.credit_detail(values["household_id"],credit_id)
    def update_credit(self,credit_id,payload):
        with self.lock,self.connect() as con:
            current=con.execute("SELECT * FROM credits WHERE id=? AND household_id=?",(credit_id,payload.get("household_id"))).fetchone()
            if not current:
                raise ValueError("Kredit nicht gefunden.")
            merged=dict(payload)
            merged.setdefault("interest_rate",current["interest_rate"])
            merged.setdefault("automatic_interest",current["automatic_interest"])
            merged.setdefault("balloon_payment_cents",current["balloon_payment_cents"])
            merged.setdefault("provider",current["provider"])
            merged.setdefault("product_price_cents",current["product_price_cents"])
            merged.setdefault("financing_price_cents",current["financing_price_cents"])
            merged.setdefault("installment_surcharge_cents",current["installment_surcharge_cents"])
            merged.setdefault("payment_count",current["payment_count"])
            values=self.credit_values(con,merged)
            if con.execute("SELECT 1 FROM credits WHERE household_id=? AND name=? AND id<>?",(values["household_id"],values["name"],credit_id)).fetchone():
                raise ValueError("Ein Kredit mit diesem Namen existiert bereits.")
            linked_types={row["category"] for row in con.execute(
                "SELECT DISTINCT category FROM cash_flow_versions WHERE credit_id=?",(credit_id,)).fetchall()}
            if linked_types and linked_types!={values["credit_type"]}:
                raise ValueError("Die Kreditart kann wegen verknüpfter Ausgaben nicht geändert werden.")
            con.execute("""UPDATE credits SET name=?,credit_type=?,opening_balance_cents=?,interest_rate=?,
                automatic_interest=?,balloon_payment_cents=?,note=?,provider=?,product_price_cents=?,
                financing_price_cents=?,installment_surcharge_cents=? WHERE id=? AND household_id=?""",
                (values["name"],values["credit_type"],values["opening_balance_cents"],values["interest_rate"],
                 values["automatic_interest"],values["balloon_payment_cents"],values["note"],values["provider"],
                 values["product_price_cents"],values["financing_price_cents"],values["installment_surcharge_cents"],
                 credit_id,values["household_id"]))
        plan=payload.get("payment_plan")
        if plan:
            flow_id=plan.get("flow_id")
            if not flow_id:
                with self.connect() as con:
                    linked=con.execute("""SELECT f.id FROM cash_flows f JOIN cash_flow_versions v ON v.cash_flow_id=f.id
                        WHERE f.household_id=? AND v.credit_id=? AND v.recurrence='monthly'
                        ORDER BY v.version_from DESC,v.rowid DESC LIMIT 1""",(values["household_id"],credit_id)).fetchone()
                    flow_id=linked["id"] if linked else None
            if flow_id:
                saved_plan=self.update_cash_flow(flow_id,{
                "household_id":values["household_id"],"kind":"expense","name":values["name"],
                "category":values["credit_type"],"amount_cents":plan.get("amount_cents"),
                "recurrence":"monthly","due_date":plan.get("first_due_date"),
                "duration_months":plan.get("occurrence_count"),"account_id":plan.get("account_id"),
                "credit_id":credit_id,"credit_reduction_cents":"","owner":plan.get("owner") or "A",
                "active":True,"effective_from":plan.get("effective_from") or date.today().isoformat(),
                })
            else:
                saved_plan=self.create_cash_flow({
                    "household_id":values["household_id"],"kind":"expense","name":values["name"],
                    "category":values["credit_type"],"amount_cents":plan.get("amount_cents"),
                    "recurrence":"monthly","due_date":plan.get("first_due_date"),
                    "duration_months":plan.get("occurrence_count"),"account_id":plan.get("account_id"),
                    "credit_id":credit_id,"credit_reduction_cents":"","owner":plan.get("owner") or "A",
                    "active":True,"effective_from":plan.get("effective_from") or date.today().isoformat(),
                })
            expected_count=values["payment_count"]
            if expected_count is None or int(saved_plan.get("duration_months") or 0)!=expected_count:
                raise RuntimeError("Die Zahlungsanzahl konnte nicht zuverlässig gespeichert werden.")
            with self.lock,self.connect() as con:
                con.execute("UPDATE credits SET payment_count=? WHERE id=? AND household_id=?",
                    (expected_count,credit_id,values["household_id"]))
        return self.credit_detail(values["household_id"],credit_id)
    def delete_credit(self,hid,credit_id):
        with self.lock,self.connect() as con:
            row=con.execute("SELECT id,name FROM credits WHERE id=? AND household_id=?",(credit_id,hid)).fetchone()
            if not row: raise ValueError("Kredit nicht gefunden.")
            con.execute("UPDATE cash_flow_versions SET credit_id=NULL,credit_reduction_cents=0 WHERE credit_id=?",(credit_id,))
            con.execute("DELETE FROM credits WHERE id=?",(credit_id,))
        return {"id":credit_id,"name":row["name"],"deleted":True}
    def add_credit_payment(self,credit_id,payload):
        hid=payload.get("household_id")
        try: payment_date=date.fromisoformat(str(payload.get("payment_date") or "")).isoformat()
        except ValueError: raise ValueError("Das Zahlungsdatum muss ein gültiges Datum sein.")
        try: amount_cents=int(payload.get("amount_cents") or 0)
        except (TypeError,ValueError): raise ValueError("Die Tilgung muss ein gültiger Geldwert sein.")
        if amount_cents==0: raise ValueError("Tilgung oder Kreditaufstockung darf nicht 0,00 € sein.")
        note=str(payload.get("note") or "").strip() or (
            "Kreditaufstockung" if amount_cents<0 else "Manuelle Tilgung"
        )
        with self.lock,self.connect() as con:
            if not con.execute("SELECT 1 FROM credits WHERE id=? AND household_id=?",(credit_id,hid)).fetchone():
                raise ValueError("Kredit nicht gefunden.")
            payment_id=uid()
            con.execute("INSERT INTO credit_payments(id,household_id,credit_id,payment_date,amount_cents,note) VALUES(?,?,?,?,?,?)",
                (payment_id,hid,credit_id,payment_date,amount_cents,note))
        return self.credit_detail(hid,credit_id)
    def delete_credit_payment(self,hid,credit_id,payment_id):
        with self.lock,self.connect() as con:
            row=con.execute("SELECT id FROM credit_payments WHERE id=? AND credit_id=? AND household_id=?",(payment_id,credit_id,hid)).fetchone()
            if not row: raise ValueError("Tilgung nicht gefunden oder nicht manuell erfasst.")
            con.execute("DELETE FROM credit_payments WHERE id=?",(payment_id,))
        return {"id":payment_id,"deleted":True}

    def _credit_timelines(self,con,hid,through_date,include_inactive_version_ids=None,
            inactive_credit_cutoffs=None):
        """Build effective credit payments and account debits in date order.

        Manual payments are applied before linked expenses on the same day.
        Once a credit reaches zero, later linked expenses are retained as
        skipped planning rows but no longer affect either credit or account.
        """
        credits=[dict(row) for row in con.execute(
            "SELECT * FROM credits WHERE household_id=? ORDER BY created_at,name",(hid,)
        ).fetchall()]
        events_by_credit={credit["id"]:[] for credit in credits}
        for row in con.execute("""SELECT * FROM credit_payments
                WHERE household_id=? AND payment_date<=?
                ORDER BY payment_date,created_at,id""",(hid,through_date)).fetchall():
            events_by_credit.setdefault(row["credit_id"],[]).append({
                "id":row["id"],"date":row["payment_date"],
                "requested_reduction_cents":int(row["amount_cents"] or 0),
                "planned_account_amount_cents":0,
                "label":row["note"] or "Manuelle Tilgung","source":"manual",
                "source_id":row["id"],"occurrence_key":None,
            })
        included_versions={str(version_id) for version_id in (include_inactive_version_ids or [])}
        active_clause="v.active=1"
        version_params=[]
        if included_versions:
            placeholders=",".join("?" for _ in included_versions)
            active_clause=f"(v.active=1 OR v.id IN ({placeholders}))"
            version_params=sorted(included_versions)
        versions=con.execute(f"""SELECT v.id AS version_id,f.id AS flow_id,COALESCE(v.name,f.name) AS label,
                    v.amount_cents,v.credit_reduction_cents,v.credit_id,
                    v.version_from,v.version_to,v.stream_start,v.stream_end,v.due_date,v.recurrence
                FROM cash_flow_versions v JOIN cash_flows f ON f.id=v.cash_flow_id
                WHERE f.household_id=? AND f.kind='expense' AND v.credit_id IS NOT NULL
                  AND {active_clause} AND v.version_from<=?""",
                [hid,*version_params,through_date]).fetchall()
        latest_monthly_plans={}
        for version in versions:
            if version["recurrence"]!="monthly" or not version["stream_end"] or not version["due_date"]:
                continue
            current=latest_monthly_plans.get(version["credit_id"])
            if current is None or (version["version_from"],version["flow_id"])>(current["version_from"],current["flow_id"]):
                latest_monthly_plans[version["credit_id"]]=version
        for version in versions:
            if not version["due_date"]: continue
            try:
                start=(date.fromisoformat(version["due_date"])-timedelta(days=1)).isoformat()
                final_due=None
                if version["stream_end"] and (
                    version["version_to"] is None or version["version_to"]>version["stream_end"]
                ):
                    final_date=last_occurrence_on_or_before(
                        version["due_date"],version["recurrence"] or "monthly",version["stream_end"]
                    )
                    final_due=final_date.isoformat() if final_date else None
                due_dates=planned_booking_dates(
                    version["due_date"],version["recurrence"] or "monthly",start,through_date,
                    version["version_from"],version["version_to"],version["stream_start"],version["stream_end"])
            except (TypeError,ValueError):
                continue
            for due in due_dates:
                due_text=due.isoformat()
                inactive_cutoff=(inactive_credit_cutoffs or {}).get(version["credit_id"])
                if inactive_cutoff and due_text>inactive_cutoff:
                    continue
                events_by_credit.setdefault(version["credit_id"],[]).append({
                    "id":f"expense:{version['flow_id']}:{due_text}","date":due_text,
                    "requested_reduction_cents":int(version["credit_reduction_cents"] or 0),
                    "planned_account_amount_cents":int(version["amount_cents"] or 0),
                    "label":version["label"],"source":"expense","source_id":version["flow_id"],
                    "occurrence_key":f"cash-flow:{version['flow_id']}:{due_text}",
                    "is_final_scheduled_occurrence":bool(final_due and due_text==final_due),
                })

        timelines={}; occurrence_adjustments={}
        for credit in credits:
            credit["calculated_interest_rate"]=None
            credit["interest_rate_inferred"]=False
            if bool(credit.get("automatic_interest")) and credit.get("interest_rate") is None:
                plan=latest_monthly_plans.get(credit["id"])
                if plan:
                    try:
                        payment_count=len(recurrence_dates(
                            plan["due_date"],"monthly",
                            date.fromisoformat(plan["due_date"])-timedelta(days=1),plan["stream_end"]))
                    except (TypeError,ValueError):
                        payment_count=0
                    principal=(int(credit.get("product_price_cents") or 0)
                        if credit.get("credit_type")=="consumer_credit" else 0)
                    principal=principal or int(credit.get("opening_balance_cents") or 0)
                    inferred=inferred_nominal_apr(principal,int(plan["amount_cents"] or 0),payment_count,
                        int(credit.get("balloon_payment_cents") or 0))
                    if inferred is not None:
                        credit["calculated_interest_rate"]=inferred
                        credit["interest_rate_inferred"]=True
            remaining=max(0,int(credit["opening_balance_cents"] or 0)); timeline=[]
            events=events_by_credit.get(credit["id"],[])
            events.sort(key=lambda item:(item["date"],0 if item["source"]=="manual" else 1,item["id"]))
            for raw in events:
                item=dict(raw); before=remaining
                requested_raw=int(item["requested_reduction_cents"] or 0)
                requested=(requested_raw if item["source"]=="manual" else max(0,requested_raw))
                planned_account=max(0,int(item["planned_account_amount_cents"] or 0))
                contractual_residual=max(0,int(credit.get("balloon_payment_cents") or 0))
                effective_rate=(credit.get("interest_rate") if credit.get("interest_rate") is not None
                    else credit.get("calculated_interest_rate"))
                automatic=bool(credit.get("automatic_interest")) and effective_rate is not None
                interest_cents=0
                final_residual_added=0
                if item["source"]=="manual":
                    effective=(requested if requested<0 else min(requested,before))
                    account_amount=0; skipped=False; skip_reason=None
                    overpaid=max(0,requested-effective) if requested>0 else 0
                elif before<=0:
                    effective=0; account_amount=0; skipped=True; skip_reason="credit_repaid"
                    overpaid=0
                elif item["source"]=="expense" and before<=contractual_residual:
                    effective=0; account_amount=0; skipped=True; skip_reason="contractual_residual_reached"
                    overpaid=0
                elif automatic:
                    apr=Decimal(str(effective_rate))
                    interest_cents=int((Decimal(before)*apr/Decimal(1200)).quantize(Decimal("1"),rounding=ROUND_HALF_UP))
                    scheduled_principal=max(0,planned_account-interest_cents)
                    available_principal=max(0,before-contractual_residual)
                    effective=min(scheduled_principal,available_principal)
                    residual_after_rate=max(0,before-effective)
                    residual_above_target=max(0,residual_after_rate-contractual_residual)
                    final_residual_added=(residual_above_target
                        if item.get("is_final_scheduled_occurrence") and 0<residual_above_target<300
                        else 0)
                    effective+=final_residual_added
                    account_amount=min(planned_account,interest_cents+available_principal)+final_residual_added
                    skipped=False; skip_reason=None; overpaid=0
                elif requested>0:
                    available_principal=max(0,before-contractual_residual)
                    effective=min(requested,available_principal)
                    residual_after_rate=max(0,before-effective)
                    residual_above_target=max(0,residual_after_rate-contractual_residual)
                    final_residual_added=(residual_above_target
                        if item.get("is_final_scheduled_occurrence") and 0<residual_above_target<300
                        else 0)
                    if final_residual_added:
                        # A tiny residual at the explicitly bounded end of the
                        # plan is collected with the final instalment instead
                        # of leaving a few cents of debt behind.
                        effective+=final_residual_added
                        account_amount=planned_account+final_residual_added
                    else:
                        # Without a separate interest model, a shortened final
                        # instalment is exactly the remaining principal balance.
                        account_amount=effective if effective<requested else planned_account
                    skipped=False; skip_reason=None; overpaid=0
                else:
                    effective=0; account_amount=planned_account
                    skipped=False; skip_reason=None; overpaid=0
                if item["source"]=="expense" and not automatic and account_amount>effective:
                    # Legacy/manual plans often contain both the bank amount
                    # and the actual principal reduction.  Their difference is
                    # the only reliable interest value available.
                    interest_cents=account_amount-effective
                remaining=max(0,before-effective)
                item.update({
                    "amount_cents":requested if item["source"]=="manual" else effective,
                    "planned_amount_cents":requested,
                    "effective_reduction_cents":effective,
                    "interest_cents":interest_cents,
                    "automatic_calculation":automatic and item["source"]=="expense",
                    "account_amount_cents":account_amount,
                    "remaining_before_cents":before,"remaining_after_cents":remaining,
                    "adjusted":item["source"]=="expense" and (
                        effective!=requested or account_amount!=planned_account),
                    "final_residual_added_cents":final_residual_added,
                    "skipped":skipped,"skip_reason":skip_reason,"overpaid_cents":overpaid,
                })
                timeline.append(item)
                if item["occurrence_key"]:
                    occurrence_adjustments[item["occurrence_key"]]=item
            timelines[credit["id"]]={"credit":credit,"events":timeline,"remaining_balance_cents":remaining}
        return {"credits":timelines,"occurrences":occurrence_adjustments}

    def list_credits(self,hid,as_of=None,through=None,simulate_future=False,
            include_inactive_version_ids=None,inactive_credit_cutoffs=None):
        requested=as_of_date(as_of); actual_today=date.today().isoformat()
        cutoff=requested if simulate_future else min(requested,actual_today)
        default_through=add_months_anchored(actual_today,24).isoformat()
        through_date=as_of_date(through) if through else default_through
        if through_date<cutoff: through_date=cutoff
        with self.connect() as con:
            if not con.execute("SELECT 1 FROM households WHERE id=?",(hid,)).fetchone(): raise ValueError("Haushalt nicht gefunden.")
            if through is None:
                finite_end=con.execute("""SELECT MAX(COALESCE(v.stream_end,v.due_date)) AS last_date
                    FROM cash_flow_versions v JOIN cash_flows f ON f.id=v.cash_flow_id
                    WHERE f.household_id=? AND f.kind='expense' AND v.credit_id IS NOT NULL
                      AND (v.stream_end IS NOT NULL OR v.recurrence='once')""",(hid,)).fetchone()["last_date"]
                if finite_end and finite_end>through_date: through_date=finite_end
                manual_end=con.execute(
                    "SELECT MAX(payment_date) AS last_date FROM credit_payments WHERE household_id=?",(hid,)
                ).fetchone()["last_date"]
                if manual_end and manual_end>through_date: through_date=manual_end
            schedule=self._credit_timelines(con,hid,through_date,include_inactive_version_ids,
                inactive_credit_cutoffs)
            result=[]
            for credit_id,timeline in schedule["credits"].items():
                credit=dict(timeline["credit"])
                payments=[dict(item) for item in timeline["events"]
                    if item["source"]=="manual" or int(item["planned_amount_cents"] or 0)>0
                    or item.get("automatic_calculation")]
                for payment in payments:
                    payment["future"]=payment["date"]>actual_today
                    payment["applied"]=payment["date"]<=cutoff and not payment["skipped"]
                payments.sort(key=lambda item:(item["date"],item["source"],item["id"]),reverse=True)
                opening=int(credit["opening_balance_cents"] or 0)
                effective_paid=sum(item["effective_reduction_cents"] for item in payments if item["date"]<=cutoff)
                credit["paid_cents"]=min(opening,effective_paid)
                credit["remaining_balance_cents"]=max(0,opening-effective_paid)
                credit["overpaid_cents"]=sum(item["overpaid_cents"] for item in payments if item["date"]<=cutoff)
                credit["future_payment_cents"]=sum(
                    item["effective_reduction_cents"] for item in payments if item["date"]>cutoff)
                credit["interest_cents"]=sum(
                    int(item.get("interest_cents") or 0) for item in payments if item["date"]<=cutoff)
                credit["future_interest_cents"]=sum(
                    int(item.get("interest_cents") or 0) for item in payments if item["date"]>cutoff)
                credit["interest_booked_cents"]=int(con.execute(
                    "SELECT COALESCE(SUM(amount_cents),0) FROM credit_interest_bookings WHERE credit_id=? AND booking_date<=?",
                    (credit_id,cutoff)).fetchone()[0] or 0)
                contractual=con.execute("""SELECT MAX(stream_end) AS end_date
                    FROM cash_flow_versions
                    WHERE credit_id=? AND active=1 AND recurrence<>'once' AND stream_end IS NOT NULL""",
                    (credit_id,)).fetchone()["end_date"]
                repaid=next((item["date"] for item in reversed(payments)
                    if item["date"]>=cutoff and item["remaining_after_cents"]<=0 and not item["skipped"]),None)
                credit["contractual_end_date"]=contractual
                credit["expected_repayment_date"]=repaid
                plan_row=con.execute("""SELECT f.id AS flow_id,v.amount_cents,v.due_date,v.stream_end,
                        v.account_id,v.version_from,v.owner_scope,v.owner_person_id
                    FROM cash_flow_versions v JOIN cash_flows f ON f.id=v.cash_flow_id
                    WHERE v.credit_id=? AND v.active=1 AND v.recurrence='monthly'
                    ORDER BY v.version_from DESC,v.rowid DESC LIMIT 1""",(credit_id,)).fetchone()
                if plan_row:
                    plan_data=dict(plan_row)
                    derived_count=len(recurrence_dates(
                        plan_data["due_date"],"monthly",date.fromisoformat(plan_data["due_date"])-timedelta(days=1),
                        plan_data["stream_end"])) if plan_data.get("stream_end") else None
                    plan_data["occurrence_count"]=(int(credit["payment_count"])
                        if credit.get("payment_count") is not None else derived_count)
                    plan_data["derived_occurrence_count"]=derived_count
                    credit["payment_plan"]=plan_data
                else:
                    credit["payment_plan"]=None
                credit["payments"]=payments
                credit["as_of"]=cutoff
                credit["through"]=through_date
                result.append(credit)
        groups=[]
        for credit_type in ("consumer_credit","credit","borrowed"):
            matching=[item for item in result if item["credit_type"]==credit_type]
            groups.append({"credit_type":credit_type,"count":len(matching),
                "balance_cents":sum(item["remaining_balance_cents"] for item in matching)})
        return {"as_of":cutoff,"today":actual_today,"through":through_date,"items":result,"groups":groups,
            "totals":{"count":len(result),"balance_cents":sum(item["remaining_balance_cents"] for item in result)}}

    def list_interest(self,hid,as_of=None,credit_ids=None):
        credit_view=getattr(self,"list_credits_view",self.list_credits)
        view=credit_view(hid,as_of)
        active_credits=view.get("items",[])
        all_credits=view.get("all_items",active_credits)
        if credit_ids is None:
            selected_credits=active_credits
        else:
            selected_ids={str(credit_id) for credit_id in credit_ids}
            selected_credits=[credit for credit in all_credits if credit["id"] in selected_ids]
        manually_archived={credit["id"]:str(credit.get("archived_at") or "").split("T",1)[0].split(" ",1)[0]
            for credit in selected_credits if credit.get("archived") and credit.get("archive_reason")=="manual"}
        if manually_archived:
            with self.connect() as con:
                placeholders=",".join("?" for _ in manually_archived)
                saved_versions=con.execute(f"""SELECT s.version_id FROM credit_archive_flow_states s
                    WHERE s.active=1 AND s.credit_id IN ({placeholders})""",sorted(manually_archived)).fetchall()
            historical=self.list_credits(hid,as_of,include_inactive_version_ids=[row["version_id"] for row in saved_versions],
                inactive_credit_cutoffs=manually_archived)
            historical_by_id={credit["id"]:credit for credit in historical.get("items",[])}
            selected_credits=[historical_by_id.get(credit["id"],credit) for credit in selected_credits]
        cutoff=view.get("as_of") or as_of_date(as_of)
        with self.connect() as con:
            bookings=[dict(row) for row in con.execute("""SELECT b.*,c.name AS credit_name,c.provider,
                    a.name AS account_name FROM credit_interest_bookings b
                    JOIN credits c ON c.id=b.credit_id LEFT JOIN accounts a ON a.id=b.account_id
                    WHERE b.household_id=? ORDER BY b.booking_date DESC,b.created_at DESC""",(hid,)).fetchall()]
            for booking in bookings:
                booking["source"]="interest_booking"
                booking["unassigned"]=False
            linked_flow_ids={booking["cash_flow_id"] for booking in bookings if booking.get("cash_flow_id")}
            manual_versions=[dict(row) for row in con.execute("""SELECT f.id AS flow_id,
                    COALESCE(v.name,f.name) AS booking_name,v.amount_cents,v.active,v.version_from,v.version_to,
                    v.stream_start,v.stream_end,v.due_date,v.recurrence,v.account_id,a.name AS account_name
                FROM cash_flow_versions v JOIN cash_flows f ON f.id=v.cash_flow_id
                LEFT JOIN accounts a ON a.id=v.account_id
                WHERE f.household_id=? AND f.kind='expense'
                  AND COALESCE(v.category,f.category)='interest' AND v.active=1 AND v.version_from<=?
                ORDER BY v.version_from,v.rowid""",(hid,cutoff)).fetchall()]
            amount_overrides={row["occurrence_key"]:int(row["amount_cents"])
                for row in con.execute("SELECT occurrence_key,amount_cents FROM movement_amount_overrides WHERE household_id=?",(hid,)).fetchall()}
        # Interest entries created through the dedicated dialog already have a
        # formal credit_interest_bookings row.  Their linked cash flow must not
        # be counted a second time.  Ordinary expenses with category "interest"
        # are nevertheless valid booked interest and belong in this overview.
        manual_bookings=[]; recurring_versions=[]; latest_once={}
        for version in manual_versions:
            if version["flow_id"] in linked_flow_ids: continue
            if (version.get("recurrence") or "once")=="once":
                latest_once[version["flow_id"]]=version
            else:
                recurring_versions.append(version)
        interest_versions=list(latest_once.values())+recurring_versions
        for version in interest_versions:
            due_date=version.get("due_date")
            if not due_date: continue
            recurrence=version.get("recurrence") or "once"
            try:
                if recurrence=="once":
                    due_dates=[date.fromisoformat(due_date)] if due_date<=cutoff else []
                else:
                    start=(date.fromisoformat(due_date)-timedelta(days=1)).isoformat()
                    due_dates=planned_booking_dates(due_date,recurrence,start,cutoff,
                        version.get("version_from"),version.get("version_to"),
                        version.get("stream_start"),version.get("stream_end"))
            except (TypeError,ValueError):
                continue
            for due in due_dates:
                due_text=due.isoformat(); occurrence_key=f"cash-flow:{version['flow_id']}:{due_text}"
                manual_bookings.append({
                    "id":occurrence_key,"household_id":hid,"credit_id":None,
                    "booking_date":due_text,
                    "amount_cents":amount_overrides.get(occurrence_key,int(version.get("amount_cents") or 0)),
                    "account_id":version.get("account_id"),"cash_flow_id":version["flow_id"],
                    "credit_name":version.get("booking_name") or "Zinsen","provider":None,
                    "account_name":version.get("account_name"),"source":"expense","unassigned":True,
                })
        bookings.extend(manual_bookings)
        bookings.sort(key=lambda item:(item.get("booking_date") or "",item.get("id") or ""),reverse=True)
        by_credit={item["id"]:item for item in selected_credits}
        for booking in bookings: booking["credit"] = by_credit.get(booking["credit_id"])
        rows=[]
        for credit in selected_credits:
            expected_total=int(credit.get("interest_cents") or 0)+int(credit.get("future_interest_cents") or 0)
            rows.append({"credit_id":credit["id"],"name":credit["name"],"provider":credit.get("provider"),
                "credit_type":credit["credit_type"],"calculated_interest_cents":int(credit.get("interest_cents") or 0),
                "future_interest_cents":int(credit.get("future_interest_cents") or 0),
                "expected_total_interest_cents":expected_total,
                "interest_rate":credit.get("interest_rate") or credit.get("calculated_interest_rate"),
                "interest_rate_inferred":bool(credit.get("interest_rate_inferred")),
                "booked_interest_cents":int(credit.get("interest_booked_cents") or 0),
                "difference_cents":int(credit.get("interest_cents") or 0)-int(credit.get("interest_booked_cents") or 0)})
        unassigned_total=sum(int(item["amount_cents"] or 0) for item in manual_bookings)
        credit_interest_total=sum(row["calculated_interest_cents"] for row in rows)
        planned_credit_interest_total=sum(row["future_interest_cents"] for row in rows)
        return {"as_of":view.get("as_of"),"items":rows,"bookings":bookings,
            "account_interest_bookings":manual_bookings,
            "totals":{"credit_interest_cents":credit_interest_total,
                "planned_credit_interest_cents":planned_credit_interest_total,
                "checking_account_interest_cents":unassigned_total,
                "total_interest_cents":credit_interest_total+unassigned_total,
                "calculated_interest_cents":credit_interest_total,
                "future_interest_cents":planned_credit_interest_total,
                "expected_total_interest_cents":sum(row["expected_total_interest_cents"] for row in rows),
                "booked_interest_cents":sum(row["booked_interest_cents"] for row in rows)+unassigned_total,
                "unassigned_interest_cents":unassigned_total}}

    def create_interest_booking(self,payload):
        hid=str(payload.get("household_id") or "").strip(); credit_id=str(payload.get("credit_id") or "").strip()
        if not hid or not credit_id: raise ValueError("Haushalt und Kredit sind erforderlich.")
        try: booking_date=date.fromisoformat(str(payload.get("booking_date") or "")).isoformat()
        except ValueError: raise ValueError("Das Buchungsdatum muss ein gültiges Datum sein.")
        try: amount_cents=int(payload.get("amount_cents") or 0)
        except (TypeError,ValueError): raise ValueError("Der Zinsbetrag muss ein gültiger Geldwert sein.")
        if amount_cents<=0: raise ValueError("Der Zinsbetrag muss größer als 0,00 € sein.")
        with self.connect() as con:
            credit=con.execute("SELECT * FROM credits WHERE id=? AND household_id=?",(credit_id,hid)).fetchone()
            if not credit: raise ValueError("Kredit nicht gefunden.")
            account_id=payload.get("account_id") or None
            if account_id and not con.execute("SELECT 1 FROM accounts WHERE id=? AND household_id=?",(account_id,hid)).fetchone():
                raise ValueError("Das gewählte Konto gehört nicht zum Haushalt.")
            name=f"Zinsen – {credit['name']}"
        flow=self.create_cash_flow({"household_id":hid,"kind":"expense","name":name,"category":"interest",
            "amount_cents":amount_cents,"recurrence":"once","due_date":booking_date,"account_id":account_id,
            "owner":"A","active":True})
        booking_id=uid()
        with self.lock,self.connect() as con:
            con.execute("""INSERT INTO credit_interest_bookings(id,household_id,credit_id,booking_date,amount_cents,account_id,cash_flow_id)
                VALUES(?,?,?,?,?,?,?)""",(booking_id,hid,credit_id,booking_date,amount_cents,account_id,flow["id"]))
        return self.list_interest(hid,booking_date)

    def delete_interest_booking(self,hid,booking_id):
        with self.lock,self.connect() as con:
            row=con.execute("SELECT cash_flow_id FROM credit_interest_bookings WHERE id=? AND household_id=?",(booking_id,hid)).fetchone()
            if not row: raise ValueError("Zinsbuchung nicht gefunden.")
            flow_id=row["cash_flow_id"]
            con.execute("DELETE FROM credit_interest_bookings WHERE id=?",(booking_id,))
        if flow_id:
            try: self.delete_cash_flow(hid,flow_id)
            except ValueError: pass
        return self.list_interest(hid)
    def credit_detail(self,hid,credit_id,as_of=None):
        result=self.list_credits(hid,as_of)
        credit=next((item for item in result["items"] if item["id"]==credit_id),None)
        if not credit: raise ValueError("Kredit nicht gefunden.")
        return credit
    def energylab_integration(self,hid):
        with self.connect() as con:
            if not con.execute("SELECT 1 FROM households WHERE id=?",(hid,)).fetchone(): raise ValueError("Haushalt nicht gefunden.")
            row=con.execute("SELECT * FROM energylab_integrations WHERE household_id=?",(hid,)).fetchone()
        return dict(row) if row else {"household_id":hid,"base_url":"http://energylab:8090","account_id":None,"enabled":0,"last_sync_at":None,"last_status":None,"last_message":None}
    def save_energylab_integration(self,payload):
        hid=payload.get("household_id"); base_url=str(payload.get("base_url") or "").strip().rstrip("/")
        account_id=payload.get("account_id") or None; enabled=0 if payload.get("enabled") in (False,0,"0") else 1
        callback_token=(str(payload.get("callback_token") or "").strip() or None) if "callback_token" in payload else None
        if not hid or not base_url.startswith(("http://","https://")): raise ValueError("Haushalt und eine gültige EnergyLab-Adresse sind erforderlich.")
        with self.lock,self.connect() as con:
            if not con.execute("SELECT 1 FROM households WHERE id=?",(hid,)).fetchone(): raise ValueError("Haushalt nicht gefunden.")
            if account_id and not con.execute("SELECT 1 FROM accounts WHERE id=? AND household_id=?",(account_id,hid)).fetchone(): raise ValueError("Das gewählte Konto gehört nicht zum Haushalt.")
            if "callback_token" in payload:
                con.execute("""INSERT INTO energylab_integrations(household_id,base_url,account_id,enabled,callback_token)
                    VALUES(?,?,?,?,?) ON CONFLICT(household_id) DO UPDATE SET
                    base_url=excluded.base_url,account_id=excluded.account_id,enabled=excluded.enabled,
                    callback_token=excluded.callback_token,updated_at=CURRENT_TIMESTAMP""",(hid,base_url,account_id,enabled,callback_token))
            else:
                con.execute("""INSERT INTO energylab_integrations(household_id,base_url,account_id,enabled)
                    VALUES(?,?,?,?) ON CONFLICT(household_id) DO UPDATE SET
                    base_url=excluded.base_url,account_id=excluded.account_id,enabled=excluded.enabled,updated_at=CURRENT_TIMESTAMP""",(hid,base_url,account_id,enabled))
        return self.energylab_integration(hid)
    def enabled_energylab_integrations(self):
        with self.connect() as con: return [dict(row) for row in con.execute("SELECT * FROM energylab_integrations WHERE enabled=1")]
    def record_energylab_sync(self,hid,status,message):
        with self.lock,self.connect() as con:
            con.execute("UPDATE energylab_integrations SET last_sync_at=?,last_status=?,last_message=? WHERE household_id=?",(timestamp(),status,str(message)[:500],hid))
    @staticmethod
    def _energylab_cents(value):
        try: return int((Decimal(str(value or 0))*100).quantize(Decimal("1"),rounding=ROUND_HALF_UP))
        except (InvalidOperation,ValueError): return 0
    def sync_energylab_contracts(self,hid,payload):
        if not isinstance(payload,dict) or payload.get("source",{}).get("app") not in ("EnergieLab","EnergyLab"): raise ValueError("Die Gegenstelle liefert keine gültigen EnergyLab-Daten.")
        segments=payload.get("segments")
        if not isinstance(segments,list): raise ValueError("Die EnergyLab-Vertragsdaten fehlen.")
        labels={"electricity":"Strom","gas":"Gas","water":"Wasser","wastewater":"Abwasser"}; seen=set(); created=0; updated=0; unmatched_accounts=[]
        with self.lock,self.connect() as con:
            config=con.execute("SELECT * FROM energylab_integrations WHERE household_id=?",(hid,)).fetchone()
            household=con.execute("SELECT * FROM households WHERE id=?",(hid,)).fetchone()
            if not config or not household: raise ValueError("Die EnergyLab-Verbindung ist nicht eingerichtet.")
            account_id=config["account_id"]
            if account_id and not con.execute("SELECT 1 FROM accounts WHERE id=? AND household_id=?",(account_id,hid)).fetchone(): account_id=None
            person=con.execute("SELECT id FROM persons WHERE household_id=? AND slot='A'",(hid,)).fetchone()
            owner_scope="joint" if household["mode"]=="couple" else "person"; owner_person_id=None if owner_scope=="joint" else person["id"]
            for segment in segments:
                segment_id=str(segment.get("id") or "")
                if segment_id not in labels: continue
                for contract in segment.get("contracts") or []:
                    remote_id=str(contract.get("id") or "").strip(); start=str(contract.get("validFrom") or ""); end=str(contract.get("validTo") or "") or None
                    try:
                        start_date=date.fromisoformat(start)
                        if end: date.fromisoformat(end)
                    except (TypeError,ValueError): continue
                    if not remote_id or (end and end<start): continue
                    recurrence=str(contract.get("paymentRecurrence") or "monthly")
                    if recurrence not in RECURRENCE_MONTHS: recurrence="monthly"
                    try: explicit_first=date.fromisoformat(str(contract.get("firstPaymentDate") or ""))
                    except ValueError: explicit_first=None
                    if explicit_first and (explicit_first<start_date or (end and explicit_first>date.fromisoformat(end))): explicit_first=None
                    provider=str(contract.get("provider") or "").strip(); name=f"EnergyLab · {labels[segment_id]}"+(f" · {provider}" if provider else "")
                    source_key=f"energylab:advance:{segment_id}:{remote_id}"; seen.add(source_key)
                    override=con.execute("SELECT account_id,payment_day FROM energylab_account_overrides WHERE household_id=? AND source_key=?",(hid,source_key)).fetchone()
                    source_account_name=str(contract.get("paymentAccountName") or "").strip()
                    source_account=con.execute("SELECT id FROM accounts WHERE household_id=? AND lower(name)=lower(?)",(hid,source_account_name)).fetchone() if source_account_name else None
                    if source_account_name and not source_account: unmatched_accounts.append(f"{name}: {source_account_name}")
                    flow_account_id=source_account["id"] if source_account else (override["account_id"] if override else account_id)
                    try: source_payment_day=int(contract.get("paymentDay"))
                    except (TypeError,ValueError): source_payment_day=None
                    if source_payment_day not in range(1,32): source_payment_day=None
                    payment_day=source_payment_day or (int(override["payment_day"]) if override and override["payment_day"] else None)
                    flow=con.execute("SELECT * FROM cash_flows WHERE household_id=? AND source_key=?",(hid,source_key)).fetchone()
                    if flow: flow_id=flow["id"]; updated+=1
                    else:
                        flow_id=uid(); created+=1
                        con.execute("""INSERT INTO cash_flows(id,household_id,kind,name,owner_scope,owner_person_id,account_id,source_key,category)
                            VALUES(?,?,?,?,?,?,?,?,?)""",(flow_id,hid,"expense",name,owner_scope,owner_person_id,flow_account_id,source_key,"energy"))
                    con.execute("UPDATE cash_flows SET name=?,owner_scope=?,owner_person_id=?,account_id=?,category='energy' WHERE id=?",(name,owner_scope,owner_person_id,flow_account_id,flow_id))
                    payment_amount=contract.get("paymentAmount")
                    if payment_amount is None: payment_amount=contract.get("advanceMonthly")
                    values={start:(start,self._energylab_cents(payment_amount))}
                    for change in contract.get("advanceChanges") or []:
                        change_from=str(change.get("validFrom") or "")
                        try: change_date=date.fromisoformat(change_from)
                        except (TypeError,ValueError): continue
                        if change_date<start_date or (end and change_from>end): continue
                        effective=change_date.isoformat()
                        values[effective]=(effective,self._energylab_cents(change.get("advanceMonthly")))
                    schedule=sorted(values.values()); con.execute("DELETE FROM cash_flow_versions WHERE cash_flow_id=?",(flow_id,)); due_day=payment_day or start_date.day
                    for index,(effective,amount) in enumerate(schedule):
                        effective_date=date.fromisoformat(effective)
                        first_due=energylab_first_due(start_date,due_day,recurrence,effective_date,explicit_first)
                        due=start if index==0 and not payment_day else first_due.isoformat()
                        version_to=schedule[index+1][0] if index+1<len(schedule) else None
                        con.execute("""INSERT INTO cash_flow_versions(id,cash_flow_id,amount_cents,active,version_from,version_to,stream_start,stream_end,due_date,source_reference,gross_amount_cents,recurrence,name,category,owner_scope,owner_person_id,account_id,credit_id,credit_reduction_cents)
                            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(uid(),flow_id,amount,1 if amount>0 else 0,effective,version_to,start,end,due,f"EnergyLab-Vertrag {remote_id}",None,recurrence,name,"energy",owner_scope,owner_person_id,flow_account_id,None,0))
            stale=[row for row in con.execute("SELECT id,source_key FROM cash_flows WHERE household_id=? AND source_key LIKE 'energylab:advance:%'",(hid,)).fetchall() if row["source_key"] not in seen]
            for row in stale: con.execute("UPDATE cash_flow_versions SET active=0 WHERE cash_flow_id=?",(row["id"],))
        return {"created":created,"updated":updated,"deactivated":len(stale),"contracts":len(seen),"unmatched_accounts":unmatched_accounts}

    @staticmethod
    def _canonical_json(value):
        return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))

    @staticmethod
    def _strict_energylab_cents(value,field="Betrag"):
        try:
            decimal=Decimal(str(value))
        except (InvalidOperation,TypeError,ValueError) as exc:
            raise ValueError(f"{field} ist ungültig.") from exc
        if not decimal.is_finite(): raise ValueError(f"{field} ist ungültig.")
        cents=int((decimal*100).quantize(Decimal("1"),rounding=ROUND_HALF_UP))
        if cents<0: raise ValueError(f"{field} darf nicht negativ sein.")
        return cents

    def _current_energylab_snapshot(self,con,hid,source_key):
        flow=con.execute("SELECT * FROM cash_flows WHERE household_id=? AND source_key=?",(hid,source_key)).fetchone()
        if not flow: return None
        versions=con.execute("""SELECT amount_cents,active,version_from,version_to,stream_start,stream_end,
                due_date,source_reference,recurrence,name,category,owner_scope,owner_person_id,account_id
            FROM cash_flow_versions WHERE cash_flow_id=? ORDER BY version_from,rowid""",(flow["id"],)).fetchall()
        return {
            "source_key":source_key,"name":flow["name"],"account_id":flow["account_id"],
            "owner_scope":flow["owner_scope"],"owner_person_id":flow["owner_person_id"],
            "category":flow["category"],"kind":flow["kind"],
            "versions":[dict(row) for row in versions],
        }

    def _normalize_energylab_payload(self,con,hid,payload):
        if not isinstance(payload,dict) or payload.get("source",{}).get("app") not in ("EnergieLab","EnergyLab"):
            raise ValueError("Die Gegenstelle liefert keine gültigen EnergyLab-Daten.")
        segments=payload.get("segments")
        if not isinstance(segments,list): raise ValueError("Die EnergyLab-Vertragsdaten fehlen.")
        config=con.execute("SELECT * FROM energylab_integrations WHERE household_id=?",(hid,)).fetchone()
        household=con.execute("SELECT * FROM households WHERE id=?",(hid,)).fetchone()
        if not config or not household: raise ValueError("Die EnergyLab-Verbindung ist nicht eingerichtet.")
        default_account=config["account_id"]
        if default_account and not con.execute("SELECT 1 FROM accounts WHERE id=? AND household_id=?",(default_account,hid)).fetchone():
            default_account=None
        person=con.execute("SELECT id FROM persons WHERE household_id=? AND slot='A'",(hid,)).fetchone()
        owner_scope="joint" if household["mode"]=="couple" else "person"
        owner_person_id=None if owner_scope=="joint" else person["id"]
        labels={"electricity":"Strom","gas":"Gas","water":"Wasser","wastewater":"Abwasser"}
        desired={}; unmatched=[]; warnings=[]
        for segment in segments:
            segment_id=str(segment.get("id") or "")
            if segment_id not in labels: continue
            contracts=segment.get("contracts") or []
            if not isinstance(contracts,list):
                warnings.append(f"{labels[segment_id]}: ungültige Vertragsliste übersprungen."); continue
            for contract in contracts:
                remote_id=str(contract.get("id") or "").strip()
                if not remote_id:
                    warnings.append(f"{labels[segment_id]}: Vertrag ohne ID übersprungen."); continue
                try:
                    start_date=date.fromisoformat(str(contract.get("validFrom") or ""))
                    end_date=date.fromisoformat(str(contract.get("validTo"))) if contract.get("validTo") else None
                except (TypeError,ValueError):
                    warnings.append(f"{labels[segment_id]} {remote_id}: ungültiger Zeitraum übersprungen."); continue
                if end_date and end_date<start_date:
                    warnings.append(f"{labels[segment_id]} {remote_id}: Enddatum liegt vor dem Startdatum."); continue
                recurrence=str(contract.get("paymentRecurrence") or "monthly")
                if recurrence not in {*RECURRENCE_MONTHS,"once"}: recurrence="monthly"
                explicit_first=None
                if contract.get("firstPaymentDate"):
                    try: explicit_first=date.fromisoformat(str(contract["firstPaymentDate"]))
                    except ValueError: warnings.append(f"{labels[segment_id]} {remote_id}: ungültige erste Fälligkeit ignoriert.")
                if explicit_first and (explicit_first<start_date or (end_date and explicit_first>end_date)): explicit_first=None
                provider=str(contract.get("provider") or "").strip()
                name=f"EnergyLab · {labels[segment_id]}"+(f" · {provider}" if provider else "")
                source_key=f"energylab:advance:{segment_id}:{remote_id}"
                override=con.execute("SELECT account_id,payment_day FROM energylab_account_overrides WHERE household_id=? AND source_key=?",(hid,source_key)).fetchone()
                source_account_name=str(contract.get("paymentAccountName") or "").strip()
                source_account=con.execute("SELECT id FROM accounts WHERE household_id=? AND lower(name)=lower(?)",(hid,source_account_name)).fetchone() if source_account_name else None
                if source_account_name and not source_account: unmatched.append(f"{name}: {source_account_name}")
                flow_account_id=(override["account_id"] if override else None) or (source_account["id"] if source_account else None) or default_account
                try: source_payment_day=int(contract.get("paymentDay"))
                except (TypeError,ValueError): source_payment_day=None
                if source_payment_day not in range(1,32): source_payment_day=None
                payment_day=(int(override["payment_day"]) if override and override["payment_day"] else None) or source_payment_day
                initial=contract.get("paymentAmount")
                if initial is None: initial=contract.get("advanceMonthly")
                if initial is None:
                    warnings.append(f"{name}: Abschlagsbetrag fehlt und wurde als 0,00 EUR behandelt."); initial=0
                amount_changes={start_date:self._strict_energylab_cents(initial,f"{name}: Abschlagsbetrag")}
                for change in contract.get("advanceChanges") or []:
                    try: change_date=date.fromisoformat(str(change.get("validFrom") or ""))
                    except (TypeError,ValueError):
                        warnings.append(f"{name}: Änderung mit ungültigem Datum ignoriert."); continue
                    if change_date<start_date or (end_date and change_date>end_date):
                        warnings.append(f"{name}: Änderung außerhalb der Vertragslaufzeit ignoriert."); continue
                    change_value=change.get("advanceMonthly")
                    if change_value is None: change_value=change.get("paymentAmount")
                    amount_changes[change_date]=self._strict_energylab_cents(change_value,f"{name}: geänderter Abschlag")
                suspensions=[]
                for pause in contract.get("suspendedPeriods") or contract.get("paymentPauses") or []:
                    try:
                        pause_from=date.fromisoformat(str(pause.get("validFrom") or pause.get("from") or ""))
                        pause_to=date.fromisoformat(str(pause.get("validTo") or pause.get("to") or ""))
                    except (TypeError,ValueError):
                        warnings.append(f"{name}: ungültige Zahlungspause ignoriert."); continue
                    pause_from=max(pause_from,start_date); pause_to=min(pause_to,end_date) if end_date else pause_to
                    if pause_from<=pause_to: suspensions.append((pause_from,pause_to))
                boundaries=set(amount_changes)
                for pause_from,pause_to in suspensions:
                    boundaries.add(pause_from)
                    resume=pause_to+timedelta(days=1)
                    if not end_date or resume<=end_date: boundaries.add(resume)
                ordered=sorted(day for day in boundaries if not end_date or day<=end_date)
                versions=[]; due_day=payment_day or start_date.day
                contractual_first_due=(explicit_first or
                    (energylab_first_due(start_date,due_day,recurrence) if payment_day else start_date))
                for index,effective_date in enumerate(ordered):
                    amount=amount_changes[max(day for day in amount_changes if day<=effective_date)]
                    paused=any(pause_from<=effective_date<=pause_to for pause_from,pause_to in suspensions)
                    versions.append({
                        "amount_cents":amount,"active":1 if amount>0 and not paused else 0,
                        "version_from":effective_date.isoformat(),
                        "version_to":ordered[index+1].isoformat() if index+1<len(ordered) else None,
                        "stream_start":start_date.isoformat(),"stream_end":end_date.isoformat() if end_date else None,
                        # Every version keeps the original contractual anchor.
                        # version_from/version_to selects the applicable amount;
                        # moving due_date to the first date after a change would
                        # make a 31st drift permanently to the 29th in February.
                        "due_date":contractual_first_due.isoformat(),"source_reference":f"EnergyLab-Vertrag {remote_id}",
                        "recurrence":recurrence,"name":name,"category":"energy",
                        "owner_scope":owner_scope,"owner_person_id":owner_person_id,"account_id":flow_account_id,
                    })
                desired[source_key]={
                    "source_key":source_key,"name":name,"account_id":flow_account_id,
                    "owner_scope":owner_scope,"owner_person_id":owner_person_id,
                    "category":"energy","kind":"expense","versions":versions,
                    "segment_id":segment_id,"contract_id":remote_id,"provider":provider,
                }
        return desired,sorted(set(unmatched)),warnings

    def preview_energylab_contracts(self,hid,payload):
        canonical_payload=self._canonical_json(payload)
        payload_hash=hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()
        with self.connect() as con:
            desired,unmatched,warnings=self._normalize_energylab_payload(con,hid,payload)
            current_keys={row["source_key"] for row in con.execute(
                "SELECT source_key FROM cash_flows WHERE household_id=? AND source_key LIKE 'energylab:advance:%'",(hid,)).fetchall()}
            items=[]
            for source_key,after in sorted(desired.items()):
                before=self._current_energylab_snapshot(con,hid,source_key)
                comparable_after={key:value for key,value in after.items() if key not in ("segment_id","contract_id","provider")}
                action="create" if before is None else ("unchanged" if before==comparable_after else "update")
                items.append({"source_key":source_key,"segment_id":after["segment_id"],"contract_id":after["contract_id"],
                    "provider":after["provider"],"name":after["name"],"action":action,"before":before,"after":comparable_after})
            for source_key in sorted(current_keys-set(desired)):
                items.append({"source_key":source_key,"action":"deactivate","before":self._current_energylab_snapshot(con,hid,source_key),"after":None})
        counts={action:sum(item["action"]==action for item in items) for action in ("create","update","unchanged","deactivate")}
        return {"payload_sha256":payload_hash,"source_version":str(payload.get("source",{}).get("version") or ""),
            "contracts":len(desired),"created":counts["create"],"updated":counts["update"],
            "unchanged":counts["unchanged"],"deactivated":counts["deactivate"],
            "unmatched_accounts":unmatched,"warnings":warnings,"items":items}

    def sync_energylab_contracts(self,hid,payload):
        preview=self.preview_energylab_contracts(hid,payload)
        started=timestamp(); run_id=uid()
        with self.lock,self.connect() as con:
            desired,unmatched,warnings=self._normalize_energylab_payload(con,hid,payload)
            preview_by_key={item["source_key"]:item for item in preview["items"]}
            for source_key,item in desired.items():
                operation=preview_by_key[source_key]
                flow=con.execute("SELECT id FROM cash_flows WHERE household_id=? AND source_key=?",(hid,source_key)).fetchone()
                if flow:
                    flow_id=flow["id"]
                    # These fields are deliberately structured.  Matching a
                    # payment to a supplier must not depend on parsing the
                    # human-readable flow name, especially around a switch.
                    con.execute("""UPDATE cash_flows SET
                        source_provider=?,source_segment_id=?,source_contract_id=? WHERE id=?""",
                        (item["provider"],item["segment_id"],item["contract_id"],flow_id))
                    if operation["action"]=="unchanged":
                        continue
                else:
                    flow_id=uid()
                    con.execute("""INSERT INTO cash_flows(
                            id,household_id,kind,name,owner_scope,owner_person_id,account_id,source_key,
                            source_provider,source_segment_id,source_contract_id,category)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",(
                            flow_id,hid,"expense",item["name"],item["owner_scope"],item["owner_person_id"],
                            item["account_id"],source_key,item["provider"],item["segment_id"],item["contract_id"],"energy"))
                con.execute("""UPDATE cash_flows SET kind='expense',name=?,owner_scope=?,owner_person_id=?,
                    account_id=?,source_provider=?,source_segment_id=?,source_contract_id=?,category='energy' WHERE id=?""",
                    (item["name"],item["owner_scope"],item["owner_person_id"],item["account_id"],item["provider"],
                     item["segment_id"],item["contract_id"],flow_id))
                con.execute("DELETE FROM cash_flow_versions WHERE cash_flow_id=?",(flow_id,))
                for version in item["versions"]:
                    con.execute("""INSERT INTO cash_flow_versions(id,cash_flow_id,amount_cents,active,version_from,version_to,
                        stream_start,stream_end,due_date,source_reference,gross_amount_cents,recurrence,name,category,
                        owner_scope,owner_person_id,account_id,credit_id,credit_reduction_cents)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (uid(),flow_id,version["amount_cents"],version["active"],version["version_from"],version["version_to"],
                         version["stream_start"],version["stream_end"],version["due_date"],version["source_reference"],None,
                         version["recurrence"],version["name"],version["category"],version["owner_scope"],
                         version["owner_person_id"],version["account_id"],None,0))
            stale_day=(date.today()-timedelta(days=1)).isoformat()
            for operation in preview["items"]:
                if operation["action"]!="deactivate": continue
                flow=con.execute("SELECT id FROM cash_flows WHERE household_id=? AND source_key=?",(hid,operation["source_key"])).fetchone()
                if not flow: continue
                con.execute("""UPDATE cash_flow_versions SET
                    stream_end=CASE WHEN stream_start>? THEN stream_end WHEN stream_end IS NULL OR stream_end>? THEN ? ELSE stream_end END,
                    active=CASE WHEN stream_start>? THEN 0 ELSE active END
                    WHERE cash_flow_id=?""",(stale_day,stale_day,stale_day,stale_day,flow["id"]))
            finished=timestamp()
            con.execute("""INSERT INTO energylab_sync_runs(id,household_id,status,source_version,payload_sha256,contracts,
                created,updated,unchanged,deactivated,message,started_at,finished_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (run_id,hid,"ok",preview["source_version"],preview["payload_sha256"],preview["contracts"],preview["created"],
                 preview["updated"],preview["unchanged"],preview["deactivated"],"EnergyLab-Import erfolgreich",started,finished))
            for operation in preview["items"]:
                after=(self._current_energylab_snapshot(con,hid,operation["source_key"])
                    if operation["action"]!="deactivate" else None)
                con.execute("""INSERT INTO energylab_sync_items(id,run_id,household_id,source_key,action,before_payload,after_payload,created_at)
                    VALUES(?,?,?,?,?,?,?,?)""",(uid(),run_id,hid,operation["source_key"],operation["action"],
                    self._canonical_json(operation.get("before")) if operation.get("before") is not None else None,
                    self._canonical_json(after) if after is not None else None,finished))
            con.execute("UPDATE energylab_integrations SET last_payload_sha256=? WHERE household_id=?",(preview["payload_sha256"],hid))
            self._import_energylab_payload_events(con,hid,payload)
        return {key:value for key,value in preview.items() if key!="items"}|{"run_id":run_id,"unmatched_accounts":unmatched,"warnings":warnings}

    def record_energylab_sync(self,hid,status,message):
        now=timestamp()
        with self.lock,self.connect() as con:
            con.execute("UPDATE energylab_integrations SET last_sync_at=?,last_status=?,last_message=? WHERE household_id=?",
                (now,status,str(message)[:500],hid))
            if status=="error" and con.execute("SELECT 1 FROM households WHERE id=?",(hid,)).fetchone():
                con.execute("""INSERT INTO energylab_sync_runs(id,household_id,status,message,started_at,finished_at)
                    VALUES(?,?,?,?,?,?)""",(uid(),hid,"error",str(message)[:1000],now,now))

    def list_energylab_sync_history(self,hid,limit=20):
        try: limit=max(1,min(100,int(limit)))
        except (TypeError,ValueError): limit=20
        with self.connect() as con:
            rows=con.execute("SELECT * FROM energylab_sync_runs WHERE household_id=? ORDER BY finished_at DESC LIMIT ?",(hid,limit)).fetchall()
            result=[]
            for row in rows:
                item=dict(row)
                details=con.execute("SELECT source_key,action,before_payload,after_payload FROM energylab_sync_items WHERE run_id=? ORDER BY source_key",(row["id"],)).fetchall()
                item["items"]=[{**dict(detail),"before":json.loads(detail["before_payload"]) if detail["before_payload"] else None,
                    "after":json.loads(detail["after_payload"]) if detail["after_payload"] else None} for detail in details]
                for detail in item["items"]: detail.pop("before_payload",None); detail.pop("after_payload",None)
                result.append(item)
            return result

    def energylab_sync_status(self,hid):
        integration=self.energylab_integration(hid)
        with self.connect() as con:
            latest=con.execute("SELECT id,finished_at,status,payload_sha256 FROM energylab_sync_runs WHERE household_id=? ORDER BY finished_at DESC LIMIT 1",(hid,)).fetchone()
            pending=con.execute("""SELECT COUNT(*) FROM bank_transaction_matches m JOIN bank_transactions t ON t.id=m.transaction_id
                JOIN cash_flows f ON f.id=m.target_id WHERE t.household_id=? AND f.source_key LIKE 'energylab:%'
                AND (m.confirmed=0 OR m.status='pending')""",(hid,)).fetchone()[0]
            actual=con.execute("""SELECT COUNT(*) FROM bank_transaction_matches m JOIN bank_transactions t ON t.id=m.transaction_id
                JOIN cash_flows f ON f.id=m.target_id WHERE t.household_id=? AND f.source_key LIKE 'energylab:%'
                AND m.status='confirmed'""",(hid,)).fetchone()[0]
            contracts=con.execute("SELECT COUNT(*) FROM cash_flows WHERE household_id=? AND source_key LIKE 'energylab:advance:%'",(hid,)).fetchone()[0]
        safe={key:value for key,value in integration.items() if key!="callback_token"}
        return {**safe,"connected":bool(integration.get("enabled")),"contract_count":contracts,
            "confirmed_payment_count":actual,"pending_review_count":pending,
            "latest_audit":dict(latest) if latest else None,"api_version":APP_VERSION}

    def resolve_energylab_household(self,value):
        """Resolve a callback household without requiring the inbound sync setup.

        EnergyLab stores the FinanzLab household reference as text.  Older setups
        sometimes used the visible household name because the UUID was not shown
        in the UI.  Accept an exact UUID first and, for backwards compatibility,
        a unique case-insensitive household name.
        """
        reference=str(value or "").strip()
        if not reference:
            raise ValueError("Die Haushalts-ID für den Zahlungsabgleich fehlt.")
        with self.connect() as con:
            row=con.execute("SELECT id FROM households WHERE id=?",(reference,)).fetchone()
            if row:
                return row["id"]
            matches=con.execute(
                "SELECT id FROM households WHERE lower(trim(name))=lower(?) ORDER BY created_at,id",
                (reference,),
            ).fetchall()
        if len(matches)==1:
            return matches[0]["id"]
        if len(matches)>1:
            raise ValueError(
                "Der Haushaltsname ist nicht eindeutig. Bitte die interne Haushalts-ID verwenden."
            )
        raise KeyError("Haushalt nicht gefunden.")

    def verify_energylab_access(self,hid,token=None):
        with self.connect() as con:
            household=con.execute("SELECT 1 FROM households WHERE id=?",(hid,)).fetchone()
            row=con.execute(
                "SELECT callback_token FROM energylab_integrations WHERE household_id=?",(hid,)
            ).fetchone()
        if not household:
            raise KeyError("Haushalt nicht gefunden.")
        # The inbound contract import and the outbound actual-payment feed are
        # independent directions.  A migrated 1.1.2 household may legitimately
        # have no energylab_integrations row yet; in that case the feed is still
        # available (like the other local household APIs) and simply contains
        # the matches already present for that household.
        expected=str(row["callback_token"] or "") if row else ""
        if expected and not secrets.compare_digest(expected,str(token or "")):
            raise PermissionError("Ungültiger Zugriffsschlüssel.")
        return True

    @staticmethod
    def _payment_source_key(payload):
        source_key=str(payload.get("source_key") or payload.get("sourceKey") or "").strip()
        if source_key: return source_key
        segment=str(payload.get("segment_id") or payload.get("segmentId") or "").strip()
        contract=str(payload.get("contract_id") or payload.get("contractId") or "").strip()
        return f"energylab:advance:{segment}:{contract}" if segment and contract else ""

    @staticmethod
    def _event_cents(payload,cent_names,value_names,default=None):
        for name in cent_names:
            if payload.get(name) not in (None,""):
                try: return int(payload[name])
                except (TypeError,ValueError) as exc: raise ValueError("Der Ereignisbetrag muss centgenau sein.") from exc
        for name in value_names:
            if payload.get(name) not in (None,""):
                try: return int((Decimal(str(payload[name]))*100).quantize(Decimal("1"),rounding=ROUND_HALF_UP))
                except (InvalidOperation,TypeError,ValueError) as exc: raise ValueError("Der Ereignisbetrag ist ungültig.") from exc
        return default

    def _planned_amount_for(self,con,flow_id,occurrence_date):
        row=con.execute("""SELECT amount_cents FROM cash_flow_versions WHERE cash_flow_id=?
            AND version_from<=? AND (version_to IS NULL OR version_to>?)
            AND (stream_start IS NULL OR stream_start<=?) AND (stream_end IS NULL OR stream_end>=?)
            ORDER BY version_from DESC,rowid DESC LIMIT 1""",
            (flow_id,occurrence_date,occurrence_date,occurrence_date,occurrence_date)).fetchone()
        return int(row["amount_cents"]) if row else None

    def _insert_energylab_payment_event(self,con,hid,payload):
        source_key=self._payment_source_key(payload)
        flow=con.execute("SELECT id FROM cash_flows WHERE household_id=? AND source_key=?",(hid,source_key)).fetchone()
        if not source_key or not flow: raise ValueError("Das Zahlungsereignis gehört zu keinem importierten EnergyLab-Vertrag.")
        occurrence=as_of_date(payload.get("occurrence_date") or payload.get("occurrenceDate") or
            payload.get("planned_date") or payload.get("plannedDate") or payload.get("booking_date") or payload.get("bookingDate"))
        event_type=str(payload.get("event_type") or payload.get("eventType") or payload.get("type") or "payment").casefold()
        event_type={"paid":"payment","reversal":"chargeback","reversed":"chargeback","pause":"skipped"}.get(event_type,event_type)
        if event_type not in ("payment","refund","chargeback","correction","skipped"):
            raise ValueError("Unbekannter Typ des Zahlungsereignisses.")
        amount=self._event_cents(payload,("actual_amount_cents","actualAmountCents","amount_cents","amountCents"),("actual_amount","actualAmount","amount"),0)
        if event_type=="payment": amount=abs(amount)
        elif event_type in ("refund","chargeback"): amount=-abs(amount)
        elif event_type=="skipped": amount=0
        elif not amount: raise ValueError("Eine Korrektur benötigt einen positiven oder negativen Betrag.")
        planned=self._event_cents(payload,("planned_amount_cents","plannedAmountCents"),("planned_amount","plannedAmount"),None)
        if planned is None: planned=self._planned_amount_for(con,flow["id"],occurrence)
        status=str(payload.get("status") or "confirmed").casefold()
        status={"paid":"confirmed","cancelled":"reversed","canceled":"reversed"}.get(status,status)
        if status not in ("pending","confirmed","reversed","ignored"): raise ValueError("Ungültiger Zahlungsstatus.")
        external_id=str(payload.get("external_id") or payload.get("externalId") or "").strip() or None
        if external_id:
            existing=con.execute("SELECT * FROM energylab_payment_events WHERE household_id=? AND external_id=?",(hid,external_id)).fetchone()
            if existing:
                same=(existing["source_key"]==source_key and existing["occurrence_date"]==occurrence and
                    int(existing["actual_amount_cents"])==amount and existing["event_type"]==event_type and existing["status"]==status)
                if not same: raise ValueError("Ein Zahlungsereignis mit dieser externen ID existiert bereits mit anderem Inhalt.")
                return dict(existing)|{"already_recorded":True}
        supersedes=str(payload.get("supersedes_event_id") or payload.get("supersedesEventId") or "").strip() or None
        if supersedes and not con.execute("SELECT 1 FROM energylab_payment_events WHERE id=? AND household_id=?",(supersedes,hid)).fetchone():
            raise ValueError("Das zu korrigierende Zahlungsereignis wurde nicht gefunden.")
        event_id=uid(); created=timestamp(); confirmed=1 if payload.get("confirmed",status=="confirmed") else 0
        con.execute("""INSERT INTO energylab_payment_events(id,household_id,source_key,occurrence_date,planned_amount_cents,
            actual_amount_cents,event_type,status,bank_transaction_id,external_id,note,confirmed,created_at,supersedes_event_id)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(event_id,hid,source_key,occurrence,planned,amount,event_type,status,
            payload.get("bank_transaction_id") or None,external_id,str(payload.get("note") or "").strip()[:500] or None,
            confirmed,created,supersedes))
        return dict(con.execute("SELECT * FROM energylab_payment_events WHERE id=?",(event_id,)).fetchone())|{"already_recorded":False}

    def _import_energylab_payload_events(self,con,hid,payload):
        events=[]
        for event in payload.get("paymentEvents") or payload.get("payment_events") or []:
            events.append(dict(event))
        for segment in payload.get("segments") or []:
            segment_id=str(segment.get("id") or "")
            for contract in segment.get("contracts") or []:
                contract_id=str(contract.get("id") or "")
                for event in contract.get("paymentEvents") or contract.get("payment_events") or []:
                    events.append({"segment_id":segment_id,"contract_id":contract_id,**dict(event)})
        for event in events: self._insert_energylab_payment_event(con,hid,event)

    def record_energylab_payment_event(self,hid,payload):
        if not hid: raise ValueError("Haushalt fehlt.")
        with self.lock,self.connect() as con: return self._insert_energylab_payment_event(con,hid,payload)

    @staticmethod
    def _source_parts(source_key):
        parts=str(source_key or "").split(":",3)
        return (parts[2],parts[3]) if len(parts)==4 and parts[:2]==["energylab","advance"] else (None,None)

    def actual_energylab_payments(self,hid,since=None):
        since_value=None
        if since:
            try: since_value=datetime.fromisoformat(str(since).replace("Z","+00:00")).date().isoformat()
            except ValueError:
                try: since_value=date.fromisoformat(str(since)).isoformat()
                except ValueError as exc: raise ValueError("since muss ein ISO-Datum oder -Zeitpunkt sein.") from exc
        # ``since`` denotes the booking/occurrence period requested by
        # EnergyLab, not the time at which FinanzLab happened to import it.
        # Filtering by created_at used to hide older persisted matches after an
        # update even though their bank date belonged to the active contract.
        clause=" AND occurrence_date>=?" if since_value else ""; params=(hid,since_value) if since_value else (hid,)
        payments=[]
        with self.connect() as con:
            events=con.execute(f"SELECT * FROM energylab_payment_events WHERE household_id=?{clause} ORDER BY created_at,id",params).fetchall()
            event_bank_ids={row["bank_transaction_id"] for row in events if row["bank_transaction_id"]}
            for row in events:
                segment_id,contract_id=self._source_parts(row["source_key"])
                payments.append({
                    "id":f"energylab-event:{row['id']}","source_key":row["source_key"],"segment_id":segment_id,
                    "contract_id":contract_id,"occurrence_date":row["occurrence_date"],"planned_date":row["occurrence_date"],
                    "booking_date":row["occurrence_date"],"planned_amount_cents":row["planned_amount_cents"],
                    "actual_amount_cents":int(row["actual_amount_cents"]),"currency":"EUR","status":row["status"],
                    "event_type":row["event_type"],"match_method":"manual-event","confidence":100 if row["confirmed"] else 0,
                    "confirmed":bool(row["confirmed"]),"created_at":row["created_at"],
                })
            sql="""SELECT t.*,m.planned_date,m.match_method,m.score,m.confirmed,m.status AS match_status,
                    f.id AS flow_id,f.source_key
                FROM bank_transaction_matches m JOIN bank_transactions t ON t.id=m.transaction_id
                JOIN cash_flows f ON f.id=m.target_id
                WHERE t.household_id=? AND m.target_type='cash_flow' AND f.source_key LIKE 'energylab:advance:%'"""
            values=[hid]
            if since_value: sql+=" AND COALESCE(t.value_date,t.booking_date)>=?"; values.append(since_value)
            sql+=" ORDER BY t.created_at,t.id"
            for row in con.execute(sql,values).fetchall():
                if row["id"] in event_bank_ids: continue
                segment_id,contract_id=self._source_parts(row["source_key"])
                is_reversal=row["match_status"]=="reversed" or int(row["amount_cents"])>0
                actual=(-abs(int(row["amount_cents"])) if is_reversal else abs(int(row["amount_cents"])))
                payments.append({
                    "id":f"bank-transaction:{row['id']}","source_key":row["source_key"],"segment_id":segment_id,
                    "contract_id":contract_id,"occurrence_date":row["planned_date"],"planned_date":row["planned_date"],
                    "booking_date":row["value_date"] or row["booking_date"],
                    "planned_amount_cents":self._planned_amount_for(con,row["flow_id"],row["planned_date"]),
                    "actual_amount_cents":actual,"currency":row["currency"] or "EUR",
                    "status":"reversed" if is_reversal else row["match_status"],
                    "event_type":"chargeback" if is_reversal else "payment","match_method":row["match_method"],
                    "confidence":int(row["score"]),"confirmed":bool(row["confirmed"]),"created_at":row["created_at"],
                })
        payments.sort(key=lambda item:(item["created_at"],item["id"]))
        # API v3 uses the same camelCase field names as EnergyLab's contract
        # export while retaining snake_case aliases for older local clients.
        for item in payments:
            item.update({
                "sourceKey":item.get("source_key"),"segmentId":item.get("segment_id"),
                "contractId":item.get("contract_id"),"occurrenceDate":item.get("occurrence_date"),
                "plannedDate":item.get("planned_date"),"bookingDate":item.get("booking_date"),
                "plannedAmountCents":item.get("planned_amount_cents"),
                "actualAmountCents":item.get("actual_amount_cents"),
                "eventType":item.get("event_type"),"matchMethod":item.get("match_method"),
            })
        return {"source":{"app":"FinanzLab","version":APP_VERSION},"generated_at":timestamp(),
            "household_id":hid,"payments":payments}

    def _planned_energylab_total(self,con,hid,source_key,period_from,period_to):
        flow=con.execute("SELECT id FROM cash_flows WHERE household_id=? AND source_key=?",(hid,source_key)).fetchone()
        if not flow: return 0
        total=0; start=(date.fromisoformat(period_from)-timedelta(days=1)).isoformat()
        for row in con.execute("SELECT * FROM cash_flow_versions WHERE cash_flow_id=? AND active=1",(flow["id"],)).fetchall():
            dates=planned_booking_dates(row["due_date"],row["recurrence"] or "monthly",start,period_to,
                row["version_from"],row["version_to"],row["stream_start"],row["stream_end"])
            total+=len(dates)*int(row["amount_cents"] or 0)
        return total

    def create_energylab_billing_snapshot(self,hid,payload):
        segment_id=str(payload.get("segment_id") or payload.get("segmentId") or "").strip()
        contract_id=str(payload.get("contract_id") or payload.get("contractId") or "").strip()
        period_from=as_of_date(payload.get("period_from") or payload.get("periodFrom"))
        period_to=as_of_date(payload.get("period_to") or payload.get("periodTo"))
        if not segment_id or not contract_id or period_to<period_from: raise ValueError("Vertrag und gültiger Abrechnungszeitraum sind erforderlich.")
        source_key=f"energylab:advance:{segment_id}:{contract_id}"
        all_payments=self.actual_energylab_payments(hid)["payments"]
        payment_items=[item for item in all_payments if item["source_key"]==source_key and
            period_from<=str(item.get("booking_date") or item["occurrence_date"])[:10]<=period_to and
            item["status"] not in ("pending","ignored") and item["confirmed"]]
        with self.lock,self.connect() as con:
            if not con.execute("SELECT 1 FROM cash_flows WHERE household_id=? AND source_key=?",(hid,source_key)).fetchone():
                raise ValueError("EnergyLab-Vertrag nicht gefunden.")
            planned=self._planned_energylab_total(con,hid,source_key,period_from,period_to)
            actual=sum(int(item["actual_amount_cents"]) for item in payment_items)
            statement=payload.get("statement") if isinstance(payload.get("statement"),dict) else {}
            frozen={"segment_id":segment_id,"contract_id":contract_id,"period_from":period_from,"period_to":period_to,
                "statement":statement,"planned_total_cents":planned,"actual_total_cents":actual,
                "payment_ids":[item["id"] for item in payment_items]}
            digest=hashlib.sha256(self._canonical_json(frozen).encode("utf-8")).hexdigest()
            latest=con.execute("""SELECT * FROM energylab_billing_snapshots WHERE household_id=? AND segment_id=? AND contract_id=?
                AND period_from=? AND period_to=? ORDER BY revision DESC LIMIT 1""",(hid,segment_id,contract_id,period_from,period_to)).fetchone()
            if latest and latest["payload_sha256"]==digest:
                return self._billing_snapshot_from_row(con,latest)|{"already_exists":True}
            revision=(int(latest["revision"])+1) if latest else 1; snapshot_id=uid(); created=timestamp()
            con.execute("""INSERT INTO energylab_billing_snapshots(id,household_id,segment_id,contract_id,period_from,period_to,
                revision,status,payload_sha256,statement_payload,planned_total_cents,actual_total_cents,created_at,supersedes_snapshot_id)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(snapshot_id,hid,segment_id,contract_id,period_from,period_to,revision,
                str(payload.get("status") or "final"),digest,self._canonical_json(statement),planned,actual,created,latest["id"] if latest else None))
            for item in payment_items:
                con.execute("""INSERT INTO energylab_billing_snapshot_items(id,snapshot_id,payment_event_id,occurrence_date,
                    planned_amount_cents,actual_amount_cents,event_type,status,payload) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (uid(),snapshot_id,item["id"],item["occurrence_date"],item["planned_amount_cents"],item["actual_amount_cents"],
                     item["event_type"],item["status"],self._canonical_json(item)))
            row=con.execute("SELECT * FROM energylab_billing_snapshots WHERE id=?",(snapshot_id,)).fetchone()
            return self._billing_snapshot_from_row(con,row)|{"already_exists":False}

    def _billing_snapshot_from_row(self,con,row):
        result=dict(row); result["statement"]=json.loads(result.pop("statement_payload"))
        items=con.execute("SELECT * FROM energylab_billing_snapshot_items WHERE snapshot_id=? ORDER BY occurrence_date,id",(row["id"],)).fetchall()
        result["payments"]=[json.loads(item["payload"]) for item in items]
        return result

    def list_energylab_billing_snapshots(self,hid):
        with self.connect() as con:
            return [self._billing_snapshot_from_row(con,row) for row in con.execute(
                "SELECT * FROM energylab_billing_snapshots WHERE household_id=? ORDER BY created_at DESC",(hid,)).fetchall()]

    def get_energylab_billing_snapshot(self,hid,snapshot_id):
        with self.connect() as con:
            row=con.execute("SELECT * FROM energylab_billing_snapshots WHERE id=? AND household_id=?",(snapshot_id,hid)).fetchone()
            if not row: raise ValueError("Abrechnungssnapshot nicht gefunden.")
            return self._billing_snapshot_from_row(con,row)

    def _backup_directory(self):
        return Path(self.path).resolve().parent/"backups"

    def create_backup(self,reason="manual"):
        backup_dir=self._backup_directory(); backup_dir.mkdir(parents=True,exist_ok=True)
        backup_id=uid(); compact=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        file_name=f"finanzlab-{compact}-{backup_id[:8]}.sqlite3"; target=backup_dir/file_name
        with self.lock:
            source=sqlite3.connect(self.path); destination=sqlite3.connect(target)
            try: source.backup(destination)
            finally: destination.close(); source.close()
            digest=hashlib.sha256(target.read_bytes()).hexdigest(); size=target.stat().st_size; created=timestamp()
            with self.connect() as con:
                con.execute("INSERT INTO app_backups(id,file_name,reason,database_sha256,size_bytes,created_at) VALUES(?,?,?,?,?,?)",
                    (backup_id,file_name,str(reason or "manual")[:200],digest,size,created))
        return {"id":backup_id,"file_name":file_name,"reason":str(reason or "manual")[:200],
            "database_sha256":digest,"size_bytes":size,"created_at":created,"restored_at":None}

    def list_backups(self):
        backup_dir=self._backup_directory()
        with self.connect() as con: rows=[dict(row) for row in con.execute("SELECT * FROM app_backups ORDER BY created_at DESC").fetchall()]
        for row in rows: row["available"]=(backup_dir/row["file_name"]).is_file()
        return rows

    def restore_backup(self,backup_id):
        with self.connect() as con: selected=con.execute("SELECT * FROM app_backups WHERE id=?",(backup_id,)).fetchone()
        if not selected: raise ValueError("Sicherung nicht gefunden.")
        selected=dict(selected); source_path=(self._backup_directory()/selected["file_name"]).resolve()
        if source_path.parent!=self._backup_directory().resolve() or not source_path.is_file(): raise ValueError("Sicherungsdatei fehlt.")
        digest=hashlib.sha256(source_path.read_bytes()).hexdigest()
        if not secrets.compare_digest(digest,selected["database_sha256"]): raise ValueError("Prüfsumme der Sicherung stimmt nicht.")
        verify=sqlite3.connect(f"file:{source_path}?mode=ro",uri=True)
        try:
            if verify.execute("PRAGMA integrity_check").fetchone()[0]!="ok": raise ValueError("Sicherung ist beschädigt.")
            required={row[0] for row in verify.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"households","cash_flows","cash_flow_versions"}.issubset(required): raise ValueError("Datei ist keine FinanzLab-Sicherung.")
        finally: verify.close()
        safety=self.create_backup(f"automatisch vor Wiederherstellung {backup_id}")
        with self.lock:
            source=sqlite3.connect(source_path); destination=sqlite3.connect(self.path)
            try: source.backup(destination); destination.commit()
            finally: destination.close(); source.close()
            self.initialize(); restored=timestamp()
            with self.connect() as con:
                for row in (selected,safety):
                    con.execute("""INSERT OR IGNORE INTO app_backups(id,file_name,reason,database_sha256,size_bytes,created_at,restored_at)
                        VALUES(?,?,?,?,?,?,?)""",(row["id"],row["file_name"],row.get("reason"),row["database_sha256"],row["size_bytes"],row["created_at"],row.get("restored_at")))
                con.execute("UPDATE app_backups SET restored_at=? WHERE id=?",(restored,backup_id))
        return {"id":backup_id,"restored":True,"restored_at":restored,"safety_backup_id":safety["id"]}

    def update_energylab_cash_flow_account(self,flow_id,payload):
        hid=payload.get("household_id"); account_id=payload.get("account_id")
        try: payment_day=int(payload.get("payment_day"))
        except (TypeError,ValueError): raise ValueError("Der Zahlungstag muss zwischen 1 und 31 liegen.")
        if not hid or not account_id: raise ValueError("Haushalt und Konto sind erforderlich.")
        if not 1<=payment_day<=31: raise ValueError("Der Zahlungstag muss zwischen 1 und 31 liegen.")
        with self.lock,self.connect() as con:
            flow=con.execute("SELECT * FROM cash_flows WHERE id=? AND household_id=?",(flow_id,hid)).fetchone()
            if not flow or not str(flow["source_key"] or "").startswith("energylab:advance:"): raise ValueError("EnergyLab-Ausgabe nicht gefunden.")
            if not con.execute("SELECT 1 FROM accounts WHERE id=? AND household_id=?",(account_id,hid)).fetchone(): raise ValueError("Das gewählte Konto gehört nicht zum Haushalt.")
            con.execute("""INSERT INTO energylab_account_overrides(household_id,source_key,account_id,payment_day)
                VALUES(?,?,?,?) ON CONFLICT(household_id,source_key) DO UPDATE SET
                account_id=excluded.account_id,payment_day=excluded.payment_day,updated_at=CURRENT_TIMESTAMP""",(hid,flow["source_key"],account_id,payment_day))
            con.execute("UPDATE cash_flows SET account_id=? WHERE id=?",(account_id,flow_id))
            con.execute("UPDATE cash_flow_versions SET account_id=? WHERE cash_flow_id=?",(account_id,flow_id))
            versions=con.execute("SELECT id,version_from,stream_start,due_date,recurrence FROM cash_flow_versions WHERE cash_flow_id=? ORDER BY version_from,rowid",(flow_id,)).fetchall()
            original_first=date.fromisoformat(versions[0]["due_date"]) if versions and versions[0]["due_date"] else None
            adjusted_first=(date(original_first.year,original_first.month,min(payment_day,monthrange(original_first.year,original_first.month)[1])) if original_first else None)
            for version in versions:
                # Keep one contractual anchor for the complete series.  The
                # version dates select the applicable amount but never restart
                # a monthly cadence (notably after February for day 29-31).
                con.execute("UPDATE cash_flow_versions SET due_date=? WHERE id=?",(adjusted_first.isoformat(),version["id"]))
        return next(item for item in self.list_cash_flows(hid,"expense",date.today().isoformat()) if item["id"]==flow_id)

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
                for field in ("name","category","owner_scope","owner_person_id","account_id","credit_id"):
                    item[field]=shown.get(field) if shown.get(field) is not None else item.get(field)
                for field in ("amount_cents","active","version_from","version_to","stream_start","stream_end","due_date","recurrence","credit_reduction_cents"):
                    item[field]=shown.get(field)
                item["configured_active"]=int(bool(shown.get("active")))
                lifecycle_end=item.get("stream_end") or (item.get("due_date") if item.get("recurrence")=="once" else None)
                in_stream=(not item.get("stream_start") or item["stream_start"]<=selected_date) and (not lifecycle_end or lifecycle_end>=selected_date)
                item["active"]=int(bool(current) and bool(item.get("active")) and in_stream)
                item["lifecycle_status"]="current" if current and in_stream else ("upcoming" if upcoming and not current else "ended")
                item["archive_date"]=lifecycle_end
                item["end_date"]=item.get("stream_end") if kind=="expense" else None
                if kind=="expense" and item.get("due_date") and item.get("stream_end"):
                    start_day=date.fromisoformat(item["due_date"])-timedelta(days=1)
                    item["duration_months"]=len(recurrence_dates(
                        item["due_date"],item.get("recurrence") or "monthly",start_day,item["stream_end"]))
                else:
                    item["duration_months"]=None
                source_key=str(flow["source_key"] or "")
                item["is_imported"]=source_key.startswith("excel:household-planning:")
                item["managed_by"]="energylab" if source_key.startswith("energylab:advance:") else None
                if item["managed_by"]=="energylab":
                    override=con.execute("SELECT payment_day FROM energylab_account_overrides WHERE household_id=? AND source_key=?",(hid,source_key)).fetchone()
                    item["payment_day"]=int(override["payment_day"]) if override and override["payment_day"] else int(str(item.get("due_date") or "1").split("-")[-1])
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
        with self.connect() as con:
            credit_types={row["id"]:row["credit_type"] for row in con.execute(
                "SELECT id,credit_type FROM credits WHERE household_id=?",(hid,)).fetchall()}
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
                valid_recurrences=("weekly","monthly","quarterly","semiannual","yearly","once") if kind=="expense" else ("monthly","quarterly","semiannual","yearly","once")
                if flow.get("recurrence") not in valid_recurrences:
                    add("invalid_recurrence","error","Der Zahlungsrhythmus ist ungültig.")
                if flow.get("owner_scope") not in ("person","joint"):
                    add("invalid_owner","error","Die Besitzerzuordnung ist ungültig.")
                elif flow.get("owner_scope")=="person" and flow.get("owner_person_id") not in person_ids:
                    add("missing_owner","error","Die zugeordnete Person existiert nicht mehr.")
                if int(flow.get("amount_cents") or 0)==0:
                    add("zero_amount","warning","Der Betrag ist 0,00 € und hat deshalb keine Auswirkung.")
                if not int(flow.get("configured_active") or 0):
                    add("inactive","warning","Die Position ist deaktiviert und wird derzeit nicht berücksichtigt.")
                if kind=="expense" and flow.get("category") in ("consumer_credit","credit","borrowed"):
                    credit_id=flow.get("credit_id")
                    if not credit_id:
                        add("missing_credit","error","Für diese Kredit-Ausgabe ist kein Kredit ausgewählt.")
                    elif credit_id not in credit_types:
                        add("invalid_credit","error","Der zugeordnete Kredit existiert in diesem Haushalt nicht mehr.")
                    elif credit_types[credit_id]!=flow.get("category"):
                        add("credit_type_mismatch","error","Ausgabenart und Kreditart stimmen nicht überein.")
                    if int(flow.get("credit_reduction_cents") or 0)>int(flow.get("amount_cents") or 0):
                        add("invalid_credit_reduction","error","Der Tilgungsanteil ist höher als die Kontoabbuchung.")
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
        # Neue manuelle Einnahmen/Ausgaben sind standardmäßig einmalig. Bestehende
        # Serien und EnergyLab-Importe liefern ihren Rhythmus weiterhin explizit.
        recurrence=str(payload.get("recurrence") or "once")
        valid_recurrences=("weekly","monthly","quarterly","semiannual","yearly","once") if kind=="expense" else ("monthly","quarterly","semiannual","yearly","once")
        if recurrence not in valid_recurrences: raise ValueError("Ungültiger Zahlungsrhythmus.")
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
                calculated_end=last_occurrence_date(due,recurrence,duration_months).isoformat()
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
        credit_id=None; credit_reduction_cents=0
        credit_categories=("consumer_credit","credit","borrowed")
        if kind=="expense" and category in credit_categories:
            credit_id=payload.get("credit_id") or None
            if not credit_id: raise ValueError("Für diese Ausgabenart muss ein Kredit ausgewählt werden.")
            linked_credit=con.execute("SELECT credit_type FROM credits WHERE id=? AND household_id=?",(credit_id,hid)).fetchone()
            if not linked_credit: raise ValueError("Der gewählte Kredit gehört nicht zum Haushalt.")
            if linked_credit["credit_type"]!=category: raise ValueError("Ausgabenart und Kreditart müssen übereinstimmen.")
            reduction_raw=payload.get("credit_reduction_cents")
            try: credit_reduction_cents=amount if reduction_raw in (None,"") else int(reduction_raw)
            except (TypeError,ValueError): raise ValueError("Der Tilgungsanteil muss ein gültiger Geldwert sein.")
            if credit_reduction_cents<0 or credit_reduction_cents>amount:
                raise ValueError("Der Tilgungsanteil muss zwischen 0,00 € und dem Ausgabenbetrag liegen.")
        active=0 if payload.get("active") in (False,0,"0") else 1
        return {"household_id":hid,"name":name,"category":category,"amount_cents":amount,"gross_amount_cents":None,"recurrence":recurrence,"effective_from":effective,"due_date":due,"stream_end":stream_end,"duration_months":duration_months,"active":active,"owner_scope":scope,"owner_person_id":owner_id,"account_id":account_id,"credit_id":credit_id,"credit_reduction_cents":credit_reduction_cents}
    def create_cash_flow(self,payload):
        kind=payload.get("kind")
        with self.lock,self.connect() as con:
            values=self.cash_flow_values(con,payload,kind)
            flow_id=uid()
            con.execute("""INSERT INTO cash_flows(id,household_id,kind,name,owner_scope,owner_person_id,account_id,source_key,category)
                VALUES(?,?,?,?,?,?,?,?,?)""",(flow_id,values["household_id"],kind,values["name"],values["owner_scope"],values["owner_person_id"],values["account_id"],None,values["category"]))
            con.execute("""INSERT INTO cash_flow_versions(id,cash_flow_id,amount_cents,active,version_from,version_to,stream_start,stream_end,due_date,source_reference,gross_amount_cents,recurrence,name,category,owner_scope,owner_person_id,account_id,credit_id,credit_reduction_cents)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(uid(),flow_id,values["amount_cents"],values["active"],values["effective_from"],None,values["effective_from"],values["stream_end"],values["due_date"],"Manuell erstellt",values["gross_amount_cents"],values["recurrence"],values["name"],values["category"],values["owner_scope"],values["owner_person_id"],values["account_id"],values["credit_id"],values["credit_reduction_cents"]))
        return next(item for item in self.list_cash_flows(values["household_id"],kind,values["effective_from"]) if item["id"]==flow_id)
    def update_cash_flow(self,flow_id,payload):
        kind=payload.get("kind")
        with self.lock,self.connect() as con:
            flow=con.execute("SELECT * FROM cash_flows WHERE id=? AND household_id=?",(flow_id,payload.get("household_id"))).fetchone()
            if not flow: raise ValueError("Zahlungsstrom nicht gefunden.")
            if str(flow["source_key"] or "").startswith("energylab:advance:"): raise ValueError("Diese Ausgabe wird von EnergyLab verwaltet. Änderungen bitte dort vornehmen und anschließend synchronisieren.")
            if kind and kind!=flow["kind"]: raise ValueError("Die Zahlungsart kann nicht geändert werden.")
            kind=flow["kind"]; values=self.cash_flow_values(con,payload,kind); effective=values["effective_from"]
            replace_future=payload.get("effective_from") in (None,"")
            if replace_future:
                # The current UI has no validity-date control.  A regular edit
                # therefore means "from today onward" and must supersede old,
                # invisible future versions instead of ending at the next one.
                con.execute("DELETE FROM cash_flow_versions WHERE cash_flow_id=? AND substr(version_from,1,10)>=?",
                    (flow_id,effective))
            versions=con.execute("SELECT * FROM cash_flow_versions WHERE cash_flow_id=? ORDER BY version_from,rowid",(flow_id,)).fetchall()
            same=next((row for row in versions if row["version_from"]==effective),None)
            next_date=next((row["version_from"] for row in versions if row["version_from"]>effective),None)
            if same:
                con.execute("""UPDATE cash_flow_versions SET amount_cents=?,active=?,version_to=?,stream_start=?,stream_end=?,due_date=?,source_reference=?,gross_amount_cents=?,recurrence=?,name=?,category=?,owner_scope=?,owner_person_id=?,account_id=?,credit_id=?,credit_reduction_cents=? WHERE id=?""",
                    (values["amount_cents"],values["active"],None if replace_future else same["version_to"],effective,values["stream_end"],values["due_date"],"Manuelle Änderung",values["gross_amount_cents"],values["recurrence"],values["name"],values["category"],values["owner_scope"],values["owner_person_id"],values["account_id"],values["credit_id"],values["credit_reduction_cents"],same["id"]))
            else:
                previous=[row for row in versions if row["version_from"]<effective]
                if previous:
                    prior=previous[-1]
                    if prior["version_to"] is None or prior["version_to"]>effective: con.execute("UPDATE cash_flow_versions SET version_to=? WHERE id=?",(effective,prior["id"]))
                con.execute("""INSERT INTO cash_flow_versions(id,cash_flow_id,amount_cents,active,version_from,version_to,stream_start,stream_end,due_date,source_reference,gross_amount_cents,recurrence,name,category,owner_scope,owner_person_id,account_id,credit_id,credit_reduction_cents)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(uid(),flow_id,values["amount_cents"],values["active"],effective,next_date,effective,values["stream_end"],values["due_date"],"Manuelle Änderung",values["gross_amount_cents"],values["recurrence"],values["name"],values["category"],values["owner_scope"],values["owner_person_id"],values["account_id"],values["credit_id"],values["credit_reduction_cents"]))
            if effective<=date.today().isoformat():
                con.execute("UPDATE cash_flows SET name=?,category=?,owner_scope=?,owner_person_id=?,account_id=?,source_key=NULL WHERE id=?",(values["name"],values["category"],values["owner_scope"],values["owner_person_id"],values["account_id"],flow_id))
            else:
                con.execute("UPDATE cash_flows SET source_key=NULL WHERE id=?",(flow_id,))
        return next(item for item in self.list_cash_flows(values["household_id"],kind,effective) if item["id"]==flow_id)
    def delete_cash_flow(self,hid,flow_id):
        with self.lock,self.connect() as con:
            flow=con.execute("SELECT id,name,source_key FROM cash_flows WHERE id=? AND household_id=?",(flow_id,hid)).fetchone()
            if not flow: raise ValueError("Zahlungsstrom nicht gefunden.")
            if str(flow["source_key"] or "").startswith("energylab:advance:"): raise ValueError("Diese Ausgabe wird von EnergyLab verwaltet und kann nur dort entfernt werden.")
            con.execute("DELETE FROM movement_completions WHERE household_id=? AND source_type='cash_flow' AND source_id=?",(hid,flow_id))
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
        if recurrence not in ("monthly","quarterly","semiannual","yearly","once"): raise ValueError("Ungültiger Zahlungsrhythmus.")
        due_raw=payload.get("due_date")
        if due_raw in (None,""): raise ValueError("Die erste Fälligkeit ist erforderlich.")
        try: due=date.fromisoformat(str(due_raw)).isoformat()
        except ValueError: raise ValueError("Die erste Fälligkeit muss ein gültiges Datum sein.")
        end_date=None
        if payload.get("end_date") not in (None,""):
            try: end_date=date.fromisoformat(str(payload.get("end_date"))).isoformat()
            except ValueError: raise ValueError("Das Enddatum muss ein gültiges Datum sein.")
            if end_date<due: raise ValueError("Das Ende darf nicht vor der ersten Fälligkeit liegen.")
        occurrence_count=None
        count_raw=payload.get("occurrence_count")
        if count_raw not in (None,""):
            try: occurrence_count=int(count_raw)
            except (TypeError,ValueError): raise ValueError("Die Anzahl muss eine ganze Zahl sein.")
            if str(count_raw).strip()!=str(occurrence_count) or not 1<=occurrence_count<=1200:
                raise ValueError("Die Anzahl muss zwischen 1 und 1.200 Ausführungen liegen.")
            if recurrence=="once" and occurrence_count!=1:
                raise ValueError("Eine einmalige Umbuchung kann nur eine Ausführung haben.")
        if end_date and occurrence_count is not None:
            expected_end=last_occurrence_date(due,recurrence,occurrence_count).isoformat()
            if end_date!=expected_end:
                expected_label=date.fromisoformat(expected_end).strftime("%d.%m.%Y")
                raise ValueError(
                    f"Enddatum und Anzahl passen nicht zusammen. Bei {occurrence_count} "
                    f"Ausführungen ist das Enddatum {expected_label}."
                )
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
            con.execute("DELETE FROM movement_completions WHERE household_id=? AND source_type='transfer' AND source_id=?",(hid,transfer_id))
            con.execute("DELETE FROM transfers WHERE id=?",(transfer_id,))
        return {"id":transfer_id,"name":row["name"],"deleted":True}

    def set_movement_completion(self,payload):
        hid=str(payload.get("household_id") or "").strip()
        occurrence_key=str(payload.get("occurrence_key") or "").strip()
        raw_completed=payload.get("completed")
        if not hid or not occurrence_key:
            raise ValueError("Haushalt und Bewegung sind erforderlich.")
        if raw_completed not in (True,False,0,1,"0","1"):
            raise ValueError("Der Erledigt-Status ist ungültig.")
        completed=raw_completed in (True,1,"1")
        parts=occurrence_key.split(":")
        if len(parts)!=3 or parts[0] not in ("cash-flow","transfer"):
            raise ValueError("Die Bewegung ist ungültig.")
        source_type="cash_flow" if parts[0]=="cash-flow" else "transfer"
        source_id=parts[1]
        try: occurrence_date=date.fromisoformat(parts[2]).isoformat()
        except ValueError: raise ValueError("Das Bewegungsdatum ist ungültig.")
        with self.lock,self.connect() as con:
            table="cash_flows" if source_type=="cash_flow" else "transfers"
            if not con.execute(f"SELECT 1 FROM {table} WHERE id=? AND household_id=?",(source_id,hid)).fetchone():
                raise ValueError("Die Bewegung gehört nicht zu diesem Haushalt oder existiert nicht mehr.")
            if completed:
                con.execute("""INSERT INTO movement_completions(id,household_id,occurrence_key,source_type,source_id,occurrence_date,completed_at)
                    VALUES(?,?,?,?,?,?,?)
                    ON CONFLICT(household_id,occurrence_key) DO UPDATE SET completed_at=excluded.completed_at""",
                    (uid(),hid,occurrence_key,source_type,source_id,occurrence_date,timestamp()))
            else:
                con.execute("DELETE FROM movement_completions WHERE household_id=? AND occurrence_key=?",(hid,occurrence_key))
        return {"household_id":hid,"occurrence_key":occurrence_key,"completed":completed,
            "occurrence_date":occurrence_date}

    def set_movement_amount(self,payload):
        """Override exactly one planned expense occurrence without changing its series."""
        hid=str(payload.get("household_id") or "").strip()
        occurrence_key=str(payload.get("occurrence_key") or "").strip()
        if not hid or not occurrence_key:
            raise ValueError("Haushalt und Bewegung sind erforderlich.")
        parts=occurrence_key.split(":")
        if len(parts)!=3 or parts[0]!="cash-flow":
            raise ValueError("Nur einzelne geplante Ausgaben können geändert werden.")
        flow_id=parts[1]
        try: occurrence_date=date.fromisoformat(parts[2]).isoformat()
        except ValueError: raise ValueError("Das Bewegungsdatum ist ungültig.")
        reset=payload.get("amount_cents") in (None,"")
        if not reset:
            try: amount_cents=int(payload.get("amount_cents"))
            except (TypeError,ValueError): raise ValueError("Der Betrag muss ein gültiger Geldwert sein.")
            if amount_cents<0: raise ValueError("Der Betrag darf nicht negativ sein.")
        with self.lock,self.connect() as con:
            flow=con.execute("SELECT kind FROM cash_flows WHERE id=? AND household_id=?",(flow_id,hid)).fetchone()
            if not flow or flow["kind"]!="expense":
                raise ValueError("Die geplante Ausgabe gehört nicht zu diesem Haushalt oder existiert nicht mehr.")
            if reset:
                con.execute("DELETE FROM movement_amount_overrides WHERE household_id=? AND occurrence_key=?",
                    (hid,occurrence_key))
            else:
                con.execute("""INSERT INTO movement_amount_overrides
                    (id,household_id,occurrence_key,cash_flow_id,occurrence_date,amount_cents,updated_at)
                    VALUES(?,?,?,?,?,?,?)
                    ON CONFLICT(household_id,occurrence_key) DO UPDATE SET
                    amount_cents=excluded.amount_cents,updated_at=excluded.updated_at""",
                    (uid(),hid,occurrence_key,flow_id,occurrence_date,amount_cents,timestamp()))
        return {"household_id":hid,"occurrence_key":occurrence_key,"occurrence_date":occurrence_date,
            "amount_cents":None if reset else amount_cents,"overridden":not reset}
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
        completed_occurrences={row["occurrence_key"] for row in con.execute(
            "SELECT occurrence_key FROM movement_completions WHERE household_id=?",(hid,)).fetchall()}
        amount_overrides={row["occurrence_key"]:int(row["amount_cents"]) for row in con.execute(
            "SELECT occurrence_key,amount_cents FROM movement_amount_overrides WHERE household_id=?",(hid,)).fetchall()}
        bank_actual_flow_ids={
            row["target_id"] for row in matches
            if row["target_type"]=="cash_flow" and row["match_method"]=="created-other-expense"
        }

        def add_event(account_id,event_date,amount_cents,kind,label,source_id,occurrence_key,origin,
                      show_on_anchor=False,completion_key=None,applied_override=None,event_meta=None):
            completion_allowed=bool(completion_key)
            completed=completion_allowed and completion_key in completed_occurrences
            event={
                "date":event_date,"account_id":account_id,"kind":kind,"label":label,
                "source_id":source_id,"occurrence_key":occurrence_key,
                "origin":origin,"amount_cents":amount_cents,
                "completion_key":completion_key,"completion_allowed":completion_allowed,
                "completed":completed,
            }
            if event_meta: event.update(event_meta)
            target=projected.get(account_id)
            if completed:
                completed_event={**event,"applied_to_projection":False}
                if target is None: result["unassigned_events"].append(completed_event)
                else: result["events"].append(completed_event)
                return
            if target is None:
                if applied_override is False:
                    result["unassigned_events"].append({**event,"applied_to_projection":False})
                    return
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
            if applied_override is False:
                result["events"].append({**event,"applied_to_projection":False})
                return
            if target["balance_cents"] is None: return
            target["balance_cents"]+=amount_cents; target["event_count"]+=1
            if amount_cents>=0: target["income_cents"]+=amount_cents
            else: target["expense_cents"]+=-amount_cents
            result["events"].append({**event,"applied_to_projection":True})

        credit_occurrences=self._credit_timelines(con,hid,selected_date)["occurrences"]
        versions=con.execute("""SELECT f.id AS flow_id,f.kind,COALESCE(v.name,f.name) AS label,
                   v.amount_cents,v.active,v.version_from,v.version_to,v.stream_start,v.stream_end,
                   v.due_date,v.recurrence,COALESCE(v.account_id,f.account_id) AS account_id,
                   v.credit_id,v.credit_reduction_cents,COALESCE(v.category,f.category) AS category
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
                due_dates=planned_booking_dates(version["due_date"],version["recurrence"] or "monthly",start,selected_date,
                    version["version_from"],version["version_to"],version["stream_start"],version["stream_end"])
            except (TypeError,ValueError):
                # Legacy or otherwise malformed rows remain visible in the
                # data check, but must not break the complete forecast.
                continue
            for due in due_dates:
                due_text=due.isoformat(); occurrence_key=f"cash-flow:{version['flow_id']}:{due_text}"
                if occurrence_key in matched_occurrences: continue
                planned_amount=int(version["amount_cents"] or 0)
                actual_override=amount_overrides.get(occurrence_key) if version["kind"]=="expense" else None
                effective_planned=actual_override if actual_override is not None else planned_amount
                amount=effective_planned*(1 if version["kind"]=="income" else -1)
                applied_override=None
                event_meta={"category":version["category"],"planned_amount_cents":planned_amount,
                    "amount_overridden":actual_override is not None}
                completion_key=occurrence_key
                if version["kind"]=="expense" and version["credit_id"]:
                    adjustment=credit_occurrences.get(occurrence_key)
                    if adjustment:
                        effective_amount=(actual_override if actual_override is not None
                            else int(adjustment["account_amount_cents"] or 0))
                        amount=-effective_amount
                        event_meta.update({
                            "credit_id":version["credit_id"],
                            "credit_reduction_cents":min(effective_amount,int(adjustment["effective_reduction_cents"] or 0)),
                            "planned_credit_reduction_cents":int(version["credit_reduction_cents"] or 0),
                            "credit_adjusted":bool(adjustment["adjusted"]),
                            "final_residual_added_cents":int(adjustment.get("final_residual_added_cents") or 0),
                            "skip_reason":adjustment["skip_reason"],
                        })
                        if adjustment["skipped"]:
                            applied_override=False; completion_key=None
                add_event(version["account_id"],due_text,amount,version["kind"],version["label"],version["flow_id"],
                    occurrence_key,"planned",completion_key=completion_key,
                    applied_override=applied_override,event_meta=event_meta)

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
                completion_key=f"transfer:{transfer['id']}:{due_text}"
                add_event(transfer["source_account_id"],due_text,-amount,"transfer_out",transfer["name"],transfer["id"],
                    f"{completion_key}:out","transfer",completion_key=completion_key)
                add_event(transfer["target_account_id"],due_text,amount,"transfer_in",transfer["name"],transfer["id"],
                    f"{completion_key}:in","transfer",completion_key=completion_key)

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
            day_delta=sum(event["amount_cents"] for event in projection["events"]
                if event["account_id"]==account["id"] and event["date"]==selected_date
                and event.get("applied_to_projection",True))
            item["available"]=item["anchor_date"] is not None and item["projected_balance_cents"] is not None
            item["day_delta_cents"]=day_delta
            selected.append(item)
        selected_ids=set(account_ids)
        movements=[event for event in projection["events"] if event["account_id"] in selected_ids and event["date"]==selected_date]
        movements.sort(key=lambda item:(account_ids.index(item["account_id"]),item["kind"],item["label"]))
        applied_movements=[item for item in movements if item.get("applied_to_projection",True)]
        day_income=sum(item["amount_cents"] for item in applied_movements if item["amount_cents"]>0)
        day_expense=sum(-item["amount_cents"] for item in applied_movements if item["amount_cents"]<0)
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
        applied_month_movements=[item for item in month_movements if item.get("applied_to_projection",True)]
        month_income=sum(item["amount_cents"] for item in applied_month_movements if item["amount_cents"]>0)
        month_expense=sum(-item["amount_cents"] for item in applied_month_movements if item["amount_cents"]<0)
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

    def monthly_preview(self,hid,month,account_ids,credit_ids=None):
        try:
            month_start=date.fromisoformat(f"{str(month)[:7]}-01")
        except ValueError:
            raise ValueError("Der Vorschaumonat ist ungültig.")
        next_month=(month_start.replace(day=28)+timedelta(days=4)).replace(day=1)
        month_end=next_month-timedelta(days=1); opening_day=month_start-timedelta(days=1)
        if not isinstance(account_ids,list): raise ValueError("Die Kontenauswahl muss eine Liste sein.")
        account_ids=list(dict.fromkeys(str(value) for value in account_ids if str(value)))
        if credit_ids is None: credit_ids=[]
        if not isinstance(credit_ids,list): raise ValueError("Die Kreditauswahl muss eine Liste sein.")
        credit_ids=list(dict.fromkeys(str(value) for value in credit_ids if str(value)))
        end_detail=self.household_detail(hid,month_end.isoformat())
        opening_detail=self.household_detail(hid,opening_day.isoformat())
        if not end_detail or not opening_detail: raise ValueError("Haushalt nicht gefunden.")
        owned={account["id"] for account in end_detail["accounts"]}
        if any(account_id not in owned for account_id in account_ids): raise ValueError("Mindestens ein Konto gehört nicht zu diesem Haushalt.")
        credit_schedule=self.list_credits(hid,date.today().isoformat(),month_end.isoformat())
        credit_by_id={item["id"]:item for item in credit_schedule["items"]}
        if any(credit_id not in credit_by_id for credit_id in credit_ids): raise ValueError("Mindestens ein Kredit gehört nicht zu diesem Haushalt.")
        selected_credit_rows=[credit_by_id[credit_id] for credit_id in credit_ids]
        def credit_balance_on(credit,day_text):
            paid=sum(item["effective_reduction_cents"] for item in credit["payments"] if item["date"]<=day_text)
            return max(0,int(credit["opening_balance_cents"] or 0)-paid)
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
                day_credits=[]
                for credit in selected_credit_rows:
                    credit_payments=[item for item in credit["payments"] if item["date"]==day_text]
                    day_credits.append({"id":credit["id"],"name":credit["name"],"credit_type":credit["credit_type"],
                        "remaining_balance_cents":credit_balance_on(credit,day_text),
                        "reduction_cents":sum(item["effective_reduction_cents"] for item in credit_payments),
                        "payments":credit_payments})
                days.append({
                    "date":day_text,"accounts":day_accounts,"balances":day_accounts,
                    "credits":day_credits,
                    "total_balance_cents":day_total,
                    "delta_cents":sum(int(event["amount_cents"] or 0) for event in day_movements
                        if event.get("applied_to_projection",True)),
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
        selected_credits=[]
        for credit in selected_credit_rows:
            opening_balance=credit_balance_on(credit,opening_day.isoformat())
            closing_balance=credit_balance_on(credit,month_end.isoformat())
            item={key:value for key,value in credit.items() if key!="payments"}
            item["opening_balance_cents"]=opening_balance
            item["closing_balance_cents"]=closing_balance
            item["month_reduction_cents"]=opening_balance-closing_balance
            item["payments"]=[payment for payment in credit["payments"] if month_start.isoformat()<=payment["date"]<=month_end.isoformat()]
            selected_credits.append(item)
        movements.sort(key=lambda item:(item["date"],account_order.get(item["account_id"],len(account_order)),item["kind"],item["label"]))
        applied_movements=[item for item in movements if item.get("applied_to_projection",True)]
        income=sum(item["amount_cents"] for item in applied_movements if item["kind"]=="income" and item["amount_cents"]>0)
        expenses=sum(-item["amount_cents"] for item in applied_movements if item["kind"]=="expense" and item["amount_cents"]<0)
        transfers=sum(abs(item["amount_cents"]) for item in applied_movements if item["kind"] in ("transfer_in","transfer_out"))
        opening_total=sum(int(item["opening_balance_cents"] or 0) for item in selected if item["opening_balance_cents"] is not None)
        closing_total=sum(int(item["closing_balance_cents"] or 0) for item in selected if item["closing_balance_cents"] is not None)
        credit_opening_total=sum(item["opening_balance_cents"] for item in selected_credits)
        credit_closing_total=sum(item["closing_balance_cents"] for item in selected_credits)
        return {"month":month_start.strftime("%Y-%m"),"from":month_start.isoformat(),"through":month_end.isoformat(),
            "accounts":selected,"credits":selected_credits,"days":days,"movements":movements,
            "totals":{"opening_balance_cents":opening_total,"closing_balance_cents":closing_total,
                "income_cents":income,"expense_cents":expenses,"transfer_volume_cents":transfers,
                "delta_cents":closing_total-opening_total},
            "credit_totals":{"opening_balance_cents":credit_opening_total,"closing_balance_cents":credit_closing_total,
                "reduction_cents":credit_opening_total-credit_closing_total},
            "unassigned":{"items":[item for item in movements if item.get("account_id") is None]},
            "overdraft_warnings":[{"account_id":account["id"],"name":account["name"],"overage_cents":account["monthly_overdraft_overage_cents"]}
                for account in selected if account.get("overdraft_exceeded_during_month")]}

    def excel_export_payload(self,hid,from_month,through_month):
        """Collect a complete, occurrence-based forecast export for up to 24 months."""
        try:
            first=date.fromisoformat(f"{str(from_month)[:7]}-01")
            last=date.fromisoformat(f"{str(through_month)[:7]}-01")
        except (TypeError,ValueError):
            raise ValueError("Start- und Endmonat müssen gültige Monate sein.")
        if first>last:
            raise ValueError("Der Startmonat darf nicht nach dem Endmonat liegen.")
        month_count=(last.year-first.year)*12+last.month-first.month+1
        if month_count>24:
            raise ValueError("Ein Excel-Export darf höchstens 24 Monate umfassen.")

        after_last=(last.replace(day=28)+timedelta(days=4)).replace(day=1)
        through_date=(after_last-timedelta(days=1)).isoformat()
        detail=self.household_detail(hid,through_date)
        if not detail:
            raise ValueError("Haushalt nicht gefunden.")
        account_ids=[account["id"] for account in detail["accounts"]]
        account_names={account["id"]:account["name"] for account in detail["accounts"]}
        people={person["id"]:person["display_name"] for person in detail["persons"]}
        credit_result=self.list_credits(hid,date.today().isoformat(),through_date)
        credit_ids=[credit["id"] for credit in credit_result["items"]]
        credit_names={credit["id"]:credit["name"] for credit in credit_result["items"]}

        months=[]; account_months=[]; credit_months=[]; days=[]; movements=[]
        cursor=first
        while cursor<=last:
            month_value=cursor.strftime("%Y-%m")
            preview=self.monthly_preview(hid,month_value,account_ids,credit_ids)
            months.append({
                "month":month_value,"from":preview["from"],"through":preview["through"],
                **preview["totals"],"warning_count":len(preview["overdraft_warnings"]),
            })
            for account in preview["accounts"]:
                account_months.append({
                    "month":month_value,"account_id":account["id"],"account_name":account["name"],
                    "opening_balance_cents":account.get("opening_balance_cents"),
                    "month_delta_cents":account.get("month_delta_cents"),
                    "closing_balance_cents":account.get("closing_balance_cents"),
                    "minimum_balance_cents":account.get("minimum_balance_cents"),
                    "overdraft_limit_cents":int(account.get("overdraft_limit_cents") or 0),
                    "overdraft_exceeded":bool(account.get("overdraft_exceeded_during_month")),
                    "overdraft_overage_cents":int(account.get("monthly_overdraft_overage_cents") or 0),
                })
            for credit in preview["credits"]:
                credit_months.append({
                    "month":month_value,"credit_id":credit["id"],"credit_name":credit["name"],
                    "credit_type":credit["credit_type"],
                    "opening_balance_cents":credit.get("opening_balance_cents"),
                    "reduction_cents":credit.get("month_reduction_cents"),
                    "closing_balance_cents":credit.get("closing_balance_cents"),
                })
            for day in preview["days"]:
                for account in day["balances"]:
                    days.append({
                        "date":day["date"],"account_id":account["id"],"account_name":account["name"],
                        "projected_balance_cents":account.get("projected_balance_cents"),
                        "overdraft_limit_cents":int(account.get("overdraft_limit_cents") or 0),
                        "overdraft_exceeded":bool(account.get("overdraft_exceeded")),
                        "overdraft_overage_cents":int(account.get("overdraft_overage_cents") or 0),
                        "day_delta_cents":int(day.get("delta_cents") or 0),
                        "movement_count":int(day.get("movement_count") or 0),
                    })
            for event in preview["movements"]:
                movements.append({
                    **event,"account_name":account_names.get(event.get("account_id"),"Nicht zugeordnet"),
                })
            cursor=(cursor.replace(day=28)+timedelta(days=4)).replace(day=1)

        histories=[]
        for account in detail["accounts"]:
            for entry in self.list_balance_history(hid,account["id"]):
                histories.append({**entry,"account_id":account["id"],"account_name":account["name"]})
        histories.sort(key=lambda item:(item["account_name"].casefold(),item["anchor_date"],item.get("created_at") or ""),reverse=False)

        incomes=self.list_cash_flows(hid,"income",through_date)
        expenses=self.list_cash_flows(hid,"expense",through_date)
        transfers=self.list_transfers(hid)
        for collection in (incomes,expenses):
            for item in collection:
                item["account_name"]=account_names.get(item.get("account_id"),"Nicht zugeordnet")
                item["owner_name"]="Gemeinsam" if item.get("owner_scope")=="joint" else people.get(item.get("owner_person_id"),"Nicht zugeordnet")
                item["credit_name"]=credit_names.get(item.get("credit_id"))

        credit_payments=[]
        for credit in credit_result["items"]:
            for payment in credit["payments"]:
                credit_payments.append({**payment,"credit_id":credit["id"],"credit_name":credit["name"],
                    "credit_type":credit["credit_type"]})
        credit_payments.sort(key=lambda item:(item["date"],item["credit_name"].casefold(),item["source"],item["id"]))

        return {
            "generated_at":timestamp(),"from_month":first.strftime("%Y-%m"),
            "through_month":last.strftime("%Y-%m"),"from_date":first.isoformat(),
            "through_date":through_date,"month_count":month_count,
            "household":detail,"months":months,"account_months":account_months,"credit_months":credit_months,
            "days":days,"movements":movements,"accounts":detail["accounts"],
            "incomes":incomes,"expenses":expenses,"transfers":transfers,
            "balance_history":histories,"credits":credit_result["items"],"credit_payments":credit_payments,
        }

    def planned_occurrences_for_matching(self,con,hid,account_id,period_from,period_to):
        scan_from=(date.fromisoformat(period_from)-timedelta(days=7))
        scan_to=(date.fromisoformat(period_to)+timedelta(days=7))
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
            for due in planned_booking_dates(version["due_date"],version["recurrence"] or "monthly",start,end,
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
        raise ValueError("Der Kontoauszugsimport ist in dieser Version vollständig deaktiviert.")

    def _disabled_save_bank_statement_preview(self,hid,account_id,parsed):
        if not hid or not account_id: raise ValueError("Haushalt und Konto sind erforderlich.")
        if not isinstance(parsed,dict) or not isinstance(parsed.get("rows"),list) or not parsed.get("sha256"):
            raise ValueError("Die Kontoauszugsdaten sind unvollständig.")
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
                transaction_amount=int(row["amount_cents"])
                for occurrence in occurrences:
                    planned_amount=int(occurrence["amount_cents"])
                    if (transaction_amount<0)!=(planned_amount<0):
                        continue
                    amount_difference=abs(transaction_amount-planned_amount)
                    amount_tolerance=max(100,min(500,round(abs(planned_amount)*0.05)))
                    if amount_difference>amount_tolerance:
                        continue
                    distance=abs((date.fromisoformat(occurrence["date"])-transaction_date).days)
                    if distance>7: continue
                    label_tokens=normalized_match_tokens(occurrence["label"])
                    overlap=len(transaction_tokens & label_tokens)
                    amount_penalty=round(35*amount_difference/max(1,amount_tolerance))
                    score=max(0,min(100,100-amount_penalty-distance*5+min(15,overlap*5)))
                    candidates.append({**occurrence,"date_distance":distance,
                        "amount_difference_cents":amount_difference,
                        "amount_tolerance_cents":amount_tolerance,"score":score})
                candidates.sort(key=lambda item:(-item["score"],item["date"],item["label"]))
                suggested=None
                # Only an exact, close and clearly unique hit may be proposed
                # automatically. Tolerated differences always stay in review.
                if candidates and candidates[0]["amount_difference_cents"]==0 and candidates[0]["date_distance"]<=3:
                    if len(candidates)==1 or candidates[0]["score"]>=candidates[1]["score"]+10:
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
                    con.execute("""INSERT INTO bank_transaction_matches(id,transaction_id,target_type,target_id,planned_date,
                        occurrence_key,match_method,score,confirmed,status)
                        VALUES(?,?,?,?,?,?,?,?,1,'confirmed')""",(uid(),transaction_id,candidate["target_type"],candidate["target_id"],
                        candidate["date"],candidate["occurrence_key"],"amount-date-text-confirmed",int(candidate["score"])))
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
                    con.execute("""INSERT INTO bank_transaction_matches(id,transaction_id,target_type,target_id,planned_date,
                        occurrence_key,match_method,score,confirmed,status)
                        VALUES(?,?,?,?,?,?,?,?,1,'confirmed')""",(uid(),transaction_id,"cash_flow",flow_id,row["booking_date"],
                        f"cash-flow:{flow_id}:{row['booking_date']}","created-other-expense",100))
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
            month_start=date.fromisoformat(f"{selected_date[:7]}-01")
            next_month=(month_start.replace(day=28)+timedelta(days=4)).replace(day=1)
            month_end=next_month-timedelta(days=1)
            credit_occurrences=self._credit_timelines(con,hid,month_end.isoformat())["occurrences"]
            def monthly_values(kind):
                rows=con.execute("""SELECT f.id AS flow_id,COALESCE(v.name,f.name) AS name,
                        v.amount_cents,v.recurrence,v.due_date,v.credit_id,COALESCE(v.category,f.category) AS category,
                        v.version_from,v.version_to,v.stream_start,v.stream_end
                    FROM cash_flow_versions v JOIN cash_flows f ON f.id=v.cash_flow_id
                    WHERE f.household_id=? AND f.kind=? AND v.active=1
                      AND v.version_from<=? AND (v.version_to IS NULL OR v.version_to>?)
                      AND (v.stream_start IS NULL OR v.stream_start<=?)
                      AND (v.stream_end IS NULL OR v.stream_end>=?)""",
                    (hid,kind,month_end.isoformat(),month_start.isoformat(),
                     month_end.isoformat(),month_start.isoformat())).fetchall()
                totals={}; category_totals={}
                overrides={row["occurrence_key"]:int(row["amount_cents"]) for row in con.execute(
                    "SELECT occurrence_key,amount_cents FROM movement_amount_overrides WHERE household_id=?",(hid,)).fetchall()}
                for row in rows:
                    try:
                        due_dates=planned_booking_dates(
                            row["due_date"],row["recurrence"] or "monthly",
                            (month_start-timedelta(days=1)).isoformat(),month_end.isoformat(),
                            row["version_from"],row["version_to"],row["stream_start"],row["stream_end"])
                    except (TypeError,ValueError):
                        continue
                    if not due_dates: continue
                    label=row["name"]
                    amount=0
                    for due in due_dates:
                        occurrence_key=f"cash-flow:{row['flow_id']}:{due.isoformat()}"
                        adjustment=credit_occurrences.get(occurrence_key) if kind=="expense" and row["credit_id"] else None
                        occurrence_amount=(overrides[occurrence_key] if kind=="expense" and occurrence_key in overrides
                            else int(adjustment["account_amount_cents"]) if adjustment is not None
                            else int(row["amount_cents"] or 0))
                        amount+=occurrence_amount
                        category_totals[row["category"] or "other"]=category_totals.get(row["category"] or "other",0)+occurrence_amount
                    totals[label]=totals.get(label,0)+amount
                return ([
                    {"label":label,"amount_cents":amount}
                    for label,amount in sorted(totals.items(),key=lambda item:(-item[1],item[0].lower()))
                    if amount
                ],[{"category":category,"amount_cents":amount} for category,amount in
                    sorted(category_totals.items(),key=lambda item:(-item[1],item[0])) if amount])
            income_items,_=monthly_values("income"); expense_items,expense_categories=monthly_values("expense")
            income=sum(item["amount_cents"] for item in income_items)
            expenses=sum(item["amount_cents"] for item in expense_items)
            balances=sum((a["projected_balance_cents"] or 0) for a in detail["accounts"] if a["projected_balance_cents"] is not None)
        warning_accounts=[account for account in detail["accounts"] if account.get("overdraft_exceeded")]
        credit_summary=self.list_credits(hid,selected_date,simulate_future=True)
        return {"as_of":selected_date,"household":detail,"metrics":{"balance_cents":balances,
            "income_cents":income,"expenses_cents":expenses,"surplus_cents":income-expenses,
            "unassigned_projection_count":unassigned_projection["event_count"],
            "unassigned_projection_cents":unassigned_projection["net_cents"],
            "overdraft_warning_count":len(warning_accounts)},
            "breakdowns":{"income":income_items,"expenses":expense_items,"expense_categories":expense_categories},
            "credit_summary":{"as_of":credit_summary["as_of"],"groups":credit_summary["groups"],"totals":credit_summary["totals"]},
            "overdraft_warnings":[{"account_id":account["id"],"name":account["name"],
                "overage_cents":account["overdraft_overage_cents"],"projected_balance_cents":account["projected_balance_cents"],
                "overdraft_limit_cents":account["overdraft_limit_cents"]} for account in warning_accounts]}
