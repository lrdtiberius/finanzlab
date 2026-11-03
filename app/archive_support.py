from datetime import date, datetime, timezone
from copy import deepcopy
from threading import RLock
from urllib.parse import parse_qs, urlparse


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def install_repository_archive_support(Repository):
    original_initialize = Repository.initialize
    original_list_credits = Repository.list_credits
    original_credit_detail = Repository.credit_detail
    original_dashboard = Repository.dashboard
    original_monthly_preview = Repository.monthly_preview
    original_liquidity_outlook = Repository.liquidity_outlook

    def initialize(self):
        original_initialize(self)
        with self.lock, self.connect() as con:
            self.ensure_column(con, "credits", "archived", "INTEGER NOT NULL DEFAULT 0")
            self.ensure_column(con, "credits", "archived_at", "TEXT")
            self.ensure_column(con, "credits", "archive_reason", "TEXT")
            con.execute("CREATE INDEX IF NOT EXISTS credits_archive ON credits(household_id,archived,credit_type)")
            con.execute("""CREATE TABLE IF NOT EXISTS credit_archive_flow_states(
                credit_id TEXT NOT NULL REFERENCES credits(id) ON DELETE CASCADE,
                version_id TEXT NOT NULL REFERENCES cash_flow_versions(id) ON DELETE CASCADE,
                active INTEGER NOT NULL,
                PRIMARY KEY(credit_id,version_id))""")

    def archive_states(self, hid):
        with self.connect() as con:
            rows = con.execute(
                "SELECT id,archived,archived_at,archive_reason FROM credits WHERE household_id=?",
                (hid,),
            ).fetchall()
        return {
            row["id"]: {
                "archived": bool(row["archived"]),
                "archived_at": row["archived_at"],
                "archive_reason": row["archive_reason"],
            }
            for row in rows
        }

    def sync_credit_archives(self, hid, current=None):
        if not hid:
            return
        # Wenn der Aufrufer die Kredite ohnehin gerade berechnet hat, dieses
        # Ergebnis wiederverwenden. Zuvor wurde die komplette Tilgungsplanung
        # für denselben Request häufig zwei- bis dreimal aufgebaut.
        current = current or original_list_credits(self, hid, date.today().isoformat())
        states = archive_states(self, hid)
        changes=[]
        for credit in current.get("items", []):
            state = states.get(credit["id"], {})
            remaining = int(credit.get("remaining_balance_cents") or 0)
            reason = state.get("archive_reason")
            if remaining <= 0 and not state.get("archived"):
                changes.append((1,_now(),"paid",credit["id"],hid))
            elif remaining > 0 and state.get("archived") and reason == "paid":
                changes.append((0,None,None,credit["id"],hid))
        if changes:
            with self.lock, self.connect() as con:
                con.executemany(
                    "UPDATE credits SET archived=?,archived_at=?,archive_reason=? WHERE id=? AND household_id=?",
                    changes,
                )

    def decorate_credit(self, hid, credit):
        state = archive_states(self, hid).get(credit["id"], {})
        item = dict(credit)
        item["archived"] = bool(state.get("archived"))
        item["archived_at"] = state.get("archived_at")
        item["archive_reason"] = state.get("archive_reason")
        return item

    def list_credits_view(self, hid, as_of=None, through=None, simulate_future=False):
        result = original_list_credits(self, hid, as_of, through, simulate_future)
        if (not as_of or as_of == date.today().isoformat()) and not through and not simulate_future:
            sync_credit_archives(self, hid, result)
        states = archive_states(self, hid)
        all_items = []
        for credit in result.get("items", []):
            state = states.get(credit["id"], {})
            item = dict(credit)
            item["archived"] = bool(state.get("archived"))
            item["archived_at"] = state.get("archived_at")
            item["archive_reason"] = state.get("archive_reason")
            all_items.append(item)
        active = [item for item in all_items if not item["archived"]]
        archived = [item for item in all_items if item["archived"]]
        groups = []
        for credit_type in ("consumer_credit", "credit", "borrowed", "mortgage"):
            matching = [item for item in active if item["credit_type"] == credit_type]
            groups.append({
                "credit_type": credit_type,
                "count": len(matching),
                "balance_cents": sum(int(item.get("remaining_balance_cents") or 0) for item in matching),
            })
        view = dict(result)
        view["items"] = active
        view["archived_items"] = archived
        view["all_items"] = all_items
        view["groups"] = groups
        view["archive_count"] = len(archived)
        view["totals"] = {
            "count": len(active),
            "balance_cents": sum(int(item.get("remaining_balance_cents") or 0) for item in active),
        }
        return view

    def compact_credit_view(view):
        """Return the list data needed by the UI without payment timelines.

        Full timelines remain available from ``/api/credits/:id``.  Keeping
        this opt-in preserves the existing API for exports and older clients.
        """
        compact = {
            key: deepcopy(value)
            for key, value in view.items()
            if key != "all_items"
        }
        for key in ("items", "archived_items"):
            compact[key] = []
            for credit in view.get(key, []):
                item = dict(credit)
                item.pop("payments", None)
                compact[key].append(item)
        return compact

    def credit_detail(self, hid, credit_id, as_of=None):
        result = original_list_credits(self, hid, as_of)
        if not as_of or as_of == date.today().isoformat():
            sync_credit_archives(self, hid, result)
        credit = next((item for item in result.get("items", []) if item.get("id")==credit_id), None)
        if not credit:
            raise ValueError("Kredit nicht gefunden.")
        return decorate_credit(self, hid, credit)

    def set_credit_archived(self, credit_id, payload):
        hid = str(payload.get("household_id") or "").strip()
        archived = bool(payload.get("archived"))
        if not hid:
            raise ValueError("Haushalt fehlt.")
        with self.lock, self.connect() as con:
            row = con.execute(
                "SELECT id FROM credits WHERE id=? AND household_id=?",
                (credit_id, hid),
            ).fetchone()
            if not row:
                raise ValueError("Kredit nicht gefunden.")
            if archived:
                linked = con.execute(
                    "SELECT id,active FROM cash_flow_versions WHERE credit_id=?",
                    (credit_id,),
                ).fetchall()
                for version in linked:
                    con.execute(
                        "INSERT OR IGNORE INTO credit_archive_flow_states(credit_id,version_id,active) VALUES(?,?,?)",
                        (credit_id, version["id"], int(version["active"])),
                    )
                con.execute("UPDATE cash_flow_versions SET active=0 WHERE credit_id=?", (credit_id,))
                con.execute(
                    "UPDATE credits SET archived=1,archived_at=?,archive_reason='manual' WHERE id=? AND household_id=?",
                    (_now(), credit_id, hid),
                )
            else:
                saved = con.execute(
                    "SELECT version_id,active FROM credit_archive_flow_states WHERE credit_id=?",
                    (credit_id,),
                ).fetchall()
                for version in saved:
                    con.execute(
                        "UPDATE cash_flow_versions SET active=? WHERE id=? AND credit_id=?",
                        (int(version["active"]), version["version_id"], credit_id),
                    )
                con.execute("DELETE FROM credit_archive_flow_states WHERE credit_id=?", (credit_id,))
                con.execute(
                    "UPDATE credits SET archived=0,archived_at=NULL,archive_reason=NULL WHERE id=? AND household_id=?",
                    (credit_id, hid),
                )
        sync_credit_archives(self, hid)
        return credit_detail(self, hid, credit_id, date.today().isoformat())

    def dashboard(self, hid, as_of=None, include_credit_summary=True):
        # Keep the original Repository.dashboard public API. The repayment
        # assistant invokes the inexpensive no-credit-summary variant.
        result = original_dashboard(self, hid, as_of, include_credit_summary=False)
        if not include_credit_summary:
            return result
        view = list_credits_view(self, hid, as_of, simulate_future=True)
        compact_view = compact_credit_view(view)
        result["credit_summary"] = {
            "as_of": view.get("as_of"),
            "today": view.get("today"),
            "groups": [group for group in view.get("groups", []) if group.get("credit_type") != "mortgage"],
            "totals": {
                "count": sum(group.get("count",0) for group in view.get("groups", []) if group.get("credit_type") != "mortgage"),
                "balance_cents": sum(group.get("balance_cents",0) for group in view.get("groups", []) if group.get("credit_type") != "mortgage"),
            },
        }
        # The dashboard has already calculated the simulated credit view.
        # Returning its compact rows avoids a second identical API request and
        # timeline build during startup.
        result["credit_items"] = compact_view.get("items", [])
        result["archived_credit_items"] = compact_view.get("archived_items", [])
        return result

    def liquidity_outlook(self, hid, base_month=None, months=6, account_ids=None):
        if not hasattr(self, "_liquidity_cache_lock"):
            with self.lock:
                if not hasattr(self, "_liquidity_cache_lock"):
                    self._liquidity_cache_lock = RLock()
                    self._liquidity_cache = {}
                    self._liquidity_cache_revisions = {}
        try:
            count = int(months)
        except (TypeError, ValueError):
            return original_liquidity_outlook(self, hid, base_month, months, account_ids)
        key = (
            hid,
            str(base_month or date.today().strftime("%Y-%m"))[:7],
            count,
            tuple(account_ids or []),
            date.today().isoformat(),
        )
        before = self.forecast_revision_value(hid)
        with self._liquidity_cache_lock:
            if before != self._liquidity_cache_revisions.get(hid):
                self._liquidity_cache = {
                    cache_key: value
                    for cache_key, value in self._liquidity_cache.items()
                    if cache_key[0] != hid
                }
                self._liquidity_cache_revisions[hid] = before
            cached = self._liquidity_cache.get(key)
            if cached is not None:
                return deepcopy(cached)

        result = original_liquidity_outlook(
            self, hid, base_month, months, account_ids
        )
        after = self.forecast_revision_value(hid)
        if before == after:
            with self._liquidity_cache_lock:
                if self._liquidity_cache_revisions.get(hid) == before:
                    if len(self._liquidity_cache) >= 36:
                        self._liquidity_cache.pop(next(iter(self._liquidity_cache)))
                    self._liquidity_cache[key] = deepcopy(result)
        return result

    def monthly_preview(self, hid, month, account_ids, credit_ids):
        # Originalberechnung unverändert; identische Monatsabfragen im Server
        # und beim Excel-Export können ihren bereits berechneten Wert teilen.
        if not hasattr(self, "_forecast_cache_lock"):
            with self.lock:
                if not hasattr(self, "_forecast_cache_lock"):
                    self._forecast_cache_lock = RLock()
                    self._forecast_cache_months = {}
                    self._forecast_cache_revisions = {}
        key = (hid, str(month), tuple(account_ids or []), tuple(credit_ids or []))
        before = self.forecast_revision_value(hid)
        with self._forecast_cache_lock:
            if before != self._forecast_cache_revisions.get(hid):
                self._forecast_cache_months = {
                    cache_key:value for cache_key,value in self._forecast_cache_months.items()
                    if cache_key[0] != hid
                }
                self._forecast_cache_revisions[hid] = before
            cached = self._forecast_cache_months.get(key)
            if cached is not None:
                return deepcopy(cached)

        # Archivfilter gehört zum Berechnungspfad, bleibt wie in 2.4.1.
        states = archive_states(self, hid)
        active_credit_ids = [credit_id for credit_id in (credit_ids or []) if not states.get(credit_id, {}).get("archived")]
        result = original_monthly_preview(self, hid, month, account_ids, active_credit_ids)
        after = self.forecast_revision_value(hid)
        if before == after:
            with self._forecast_cache_lock:
                if self._forecast_cache_revisions.get(hid) == before:
                    if len(self._forecast_cache_months) >= 60:
                        self._forecast_cache_months.pop(next(iter(self._forecast_cache_months)))
                    self._forecast_cache_months[key] = deepcopy(result)
        return result

    Repository.initialize = initialize
    Repository._credit_archive_states = archive_states
    Repository._sync_credit_archives = sync_credit_archives
    Repository.list_credits_view = list_credits_view
    Repository.credit_detail = credit_detail
    Repository.set_credit_archived = set_credit_archived
    Repository.dashboard = dashboard
    Repository.monthly_preview = monthly_preview
    Repository.liquidity_outlook = liquidity_outlook
    Repository.compact_credit_view = staticmethod(compact_credit_view)


def install_web_archive_support(Handler):
    original_get = Handler.do_GET
    original_put = Handler.do_PUT
    def repository():
        from app import web
        return web.REPOSITORY

    def do_GET(self):
        parsed = urlparse(self.path)
        path, query = parsed.path, parse_qs(parsed.query)
        try:
            if path == "/health":
                from app.infrastructure.repository import APP_VERSION
                return self.json_response({"status": "ok", "version": APP_VERSION})
            if path == "/api/credits":
                hid = (query.get("household_id") or [""])[0]
                as_of = (query.get("as_of") or [None])[0]
                summary = (
                    (query.get("summary") or ["0"])[0]
                    in ("1", "true", "yes")
                )
                simulate_future = (
                    (query.get("simulate_future") or ["0"])[0]
                    in ("1", "true", "yes")
                )
                view = repository().list_credits_view(
                    hid,
                    as_of,
                    simulate_future=simulate_future
                )
                if summary:
                    view = repository().compact_credit_view(view)
                return self.json_response(view)
            return original_get(self)
        except Exception as exc:
            return self.json_response({"error": str(exc)}, 400)

    def do_PUT(self):
        path = urlparse(self.path).path
        try:
            if path.startswith("/api/credits/") and path.endswith("/archive"):
                parts = path.strip("/").split("/")
                if len(parts) != 4:
                    return self.json_response({"error": "Nicht gefunden."}, 404)
                return self.json_response(repository().set_credit_archived(parts[2], self.read_json()))
            return original_put(self)
        except ValueError as exc:
            return self.json_response({"error": str(exc)}, 400)
        except Exception:
            return self.json_response({"error": "Die Anfrage konnte nicht verarbeitet werden."}, 500)

    Handler.do_GET = do_GET
    Handler.do_PUT = do_PUT
