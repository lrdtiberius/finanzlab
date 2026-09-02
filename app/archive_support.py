from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def install_repository_archive_support(Repository):
    original_initialize = Repository.initialize
    original_list_credits = Repository.list_credits
    original_credit_detail = Repository.credit_detail
    original_dashboard = Repository.dashboard
    original_monthly_preview = Repository.monthly_preview

    def initialize(self):
        original_initialize(self)
        with self.lock, self.connect() as con:
            self.ensure_column(con, "credits", "archived", "INTEGER NOT NULL DEFAULT 0")
            self.ensure_column(con, "credits", "archived_at", "TEXT")
            self.ensure_column(con, "credits", "archive_reason", "TEXT")
            con.execute("CREATE INDEX IF NOT EXISTS credits_archive ON credits(household_id,archived,credit_type)")

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

    def sync_credit_archives(self, hid):
        if not hid:
            return
        current = original_list_credits(self, hid, date.today().isoformat())
        states = archive_states(self, hid)
        with self.lock, self.connect() as con:
            for credit in current.get("items", []):
                state = states.get(credit["id"], {})
                remaining = int(credit.get("remaining_balance_cents") or 0)
                reason = state.get("archive_reason")
                if remaining <= 0 and not state.get("archived"):
                    con.execute(
                        "UPDATE credits SET archived=1,archived_at=?,archive_reason='paid' WHERE id=? AND household_id=?",
                        (_now(), credit["id"], hid),
                    )
                elif remaining > 0 and state.get("archived") and reason == "paid":
                    con.execute(
                        "UPDATE credits SET archived=0,archived_at=NULL,archive_reason=NULL WHERE id=? AND household_id=?",
                        (credit["id"], hid),
                    )

    def decorate_credit(self, hid, credit):
        state = archive_states(self, hid).get(credit["id"], {})
        item = dict(credit)
        item["archived"] = bool(state.get("archived"))
        item["archived_at"] = state.get("archived_at")
        item["archive_reason"] = state.get("archive_reason")
        return item

    def list_credits_view(self, hid, as_of=None, through=None, simulate_future=False):
        sync_credit_archives(self, hid)
        result = original_list_credits(self, hid, as_of, through, simulate_future)
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
        for credit_type in ("consumer_credit", "credit", "borrowed"):
            matching = [item for item in active if item["credit_type"] == credit_type]
            groups.append(
                {
                    "credit_type": credit_type,
                    "count": len(matching),
                    "balance_cents": sum(int(item.get("remaining_balance_cents") or 0) for item in matching),
                }
            )
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

    def credit_detail(self, hid, credit_id, as_of=None):
        sync_credit_archives(self, hid)
        credit = original_credit_detail(self, hid, credit_id, as_of)
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
                con.execute(
                    "UPDATE credits SET archived=1,archived_at=?,archive_reason='manual' WHERE id=? AND household_id=?",
                    (_now(), credit_id, hid),
                )
            else:
                con.execute(
                    "UPDATE credits SET archived=0,archived_at=NULL,archive_reason=NULL WHERE id=? AND household_id=?",
                    (credit_id, hid),
                )
        sync_credit_archives(self, hid)
        return credit_detail(self, hid, credit_id, date.today().isoformat())

    def dashboard(self, hid, as_of=None):
        result = original_dashboard(self, hid, as_of)
        view = list_credits_view(self, hid, as_of, simulate_future=True)
        result["credit_summary"] = {
            "as_of": view.get("as_of"),
            "today": view.get("today"),
            "groups": view.get("groups", []),
            "totals": view.get("totals", {}),
        }
        return result

    def monthly_preview(self, hid, month, account_ids, credit_ids):
        sync_credit_archives(self, hid)
        states = archive_states(self, hid)
        active_credit_ids = [credit_id for credit_id in credit_ids if not states.get(credit_id, {}).get("archived")]
        return original_monthly_preview(self, hid, month, account_ids, active_credit_ids)

    Repository.initialize = initialize
    Repository._credit_archive_states = archive_states
    Repository._sync_credit_archives = sync_credit_archives
    Repository.list_credits_view = list_credits_view
    Repository.credit_detail = credit_detail
    Repository.set_credit_archived = set_credit_archived
    Repository.dashboard = dashboard
    Repository.monthly_preview = monthly_preview


def install_web_archive_support(Handler):
    original_get = Handler.do_GET
    original_put = Handler.do_PUT
    static_root = Path(__file__).resolve().parent / "static"

    def repository():
        from app import web
        return web.REPOSITORY

    def do_GET(self):
        parsed = urlparse(self.path)
        path, query = parsed.path, parse_qs(parsed.query)
        try:
            if path == "/api/credits":
                hid = (query.get("household_id") or [""])[0]
                as_of = (query.get("as_of") or [None])[0]
                return self.json_response(repository().list_credits_view(hid, as_of))
            if path == "/app.js":
                core = (static_root / "app.js").read_bytes()
                patch = (static_root / "credit-archive.js").read_bytes()
                data = core + b"\n\n" + patch
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                return self.wfile.write(data)
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
