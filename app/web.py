import json
import mimetypes
import os
import re
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app.application.excel_export import build_forecast_workbook
from app.application.energylab_service import EnergyLabService
from app.infrastructure.repository import Repository

ROOT = Path(__file__).resolve().parent
REPOSITORY = None
ENERGYLAB = None


class Handler(BaseHTTPRequestHandler):
    server_version = "FinanzLab/2.1.1"

    def json_response(self, data, status=HTTPStatus.OK):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self, max_bytes=1024 * 1024):
        size = int(self.headers.get("Content-Length", "0"))
        if size > max_bytes:
            raise ValueError("Anfrage ist zu groß.")
        return json.loads(self.rfile.read(size) or b"{}")

    def file_response(self, data, content_type, filename):
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        path, query = parsed.path, parse_qs(parsed.query)
        try:
            if path == "/health":
                return self.json_response({"status": "ok", "version": "2.1.1"})
            if path == "/api/households":
                return self.json_response({"items": REPOSITORY.list_households()})
            if path == "/api/categories":
                hid = (query.get("household_id") or [""])[0]
                return self.json_response(REPOSITORY.list_categories(hid))
            if path == "/api/dashboard":
                hid = (query.get("household_id") or [""])[0]
                as_of = (query.get("as_of") or [None])[0]
                return self.json_response(REPOSITORY.dashboard(hid, as_of))
            if path == "/api/cash-flows":
                hid = (query.get("household_id") or [""])[0]
                kind = (query.get("kind") or [""])[0]
                as_of = (query.get("as_of") or [None])[0]
                return self.json_response({"items": REPOSITORY.list_cash_flows(hid, kind, as_of)})
            if path == "/api/integrations/energylab":
                hid = (query.get("household_id") or [""])[0]
                return self.json_response(REPOSITORY.energylab_integration(hid))
            if path == "/api/integrations/energylab/status":
                hid = (query.get("household_id") or [""])[0]
                return self.json_response(REPOSITORY.energylab_sync_status(hid))
            if path == "/api/integrations/energylab/history":
                hid = (query.get("household_id") or [""])[0]
                limit = (query.get("limit") or [20])[0]
                return self.json_response({"items": REPOSITORY.list_energylab_sync_history(hid, limit)})
            if path == "/api/integrations/energylab/actual-payments":
                household_reference = (
                    query.get("household_id") or query.get("householdId") or [""]
                )[0]
                hid = REPOSITORY.resolve_energylab_household(household_reference)
                since = (query.get("since") or [None])[0]
                authorization = self.headers.get("Authorization", "")
                token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else (query.get("token") or [""])[0]
                REPOSITORY.verify_energylab_access(hid, token)
                return self.json_response(REPOSITORY.actual_energylab_payments(hid, since))
            if path == "/api/integrations/energylab/billing-snapshots":
                hid = (query.get("household_id") or [""])[0]
                return self.json_response({"items": REPOSITORY.list_energylab_billing_snapshots(hid)})
            if path.startswith("/api/integrations/energylab/billing-snapshots/"):
                parts = path.strip("/").split("/")
                hid = (query.get("household_id") or [""])[0]
                if len(parts) != 5:
                    return self.json_response({"error": "Nicht gefunden."}, 404)
                return self.json_response(REPOSITORY.get_energylab_billing_snapshot(hid, parts[4]))
            if path == "/api/dashboard/outlook":
                hid = (query.get("household_id") or [""])[0]
                base_month = (query.get("base_month") or [None])[0]
                months = (query.get("months") or ["6"])[0]
                account_ids = []
                for value in query.get("account_id", []) + query.get("account_ids", []):
                    account_ids.extend(
                        part.strip() for part in value.split(",") if part.strip()
                    )
                return self.json_response(
                    REPOSITORY.liquidity_outlook(
                        hid, base_month, months,
                        account_ids if account_ids else None,
                    )
                )
            if path == "/api/backups":
                return self.json_response({"items": REPOSITORY.list_backups()})
            if path == "/api/bank-statements":
                hid = (query.get("household_id") or [""])[0]
                account_id = (query.get("account_id") or [""])[0]
                return self.json_response({"items": REPOSITORY.list_bank_statements(hid, account_id)})
            if path == "/api/diagnostics":
                hid = (query.get("household_id") or [""])[0]
                as_of = (query.get("as_of") or [None])[0]
                return self.json_response(REPOSITORY.cash_flow_diagnostics(hid, as_of))
            if path == "/api/transfers":
                hid = (query.get("household_id") or [""])[0]
                return self.json_response({"items": REPOSITORY.list_transfers(hid)})
            if path == "/api/credits":
                hid = (query.get("household_id") or [""])[0]
                as_of = (query.get("as_of") or [None])[0]
                return self.json_response(REPOSITORY.list_credits(hid, as_of))
            if path == "/api/interest":
                hid = (query.get("household_id") or [""])[0]
                as_of = (query.get("as_of") or [None])[0]
                return self.json_response(REPOSITORY.list_interest(hid, as_of))
            if path.startswith("/api/credits/"):
                parts = path.strip("/").split("/")
                hid = (query.get("household_id") or [""])[0]
                as_of = (query.get("as_of") or [None])[0]
                if len(parts) != 3:
                    return self.json_response({"error": "Nicht gefunden."}, 404)
                return self.json_response(REPOSITORY.credit_detail(hid, parts[2], as_of))
            if path == "/api/export.xlsx":
                hid = (query.get("household_id") or [""])[0]
                from_month = (query.get("from_month") or [""])[0]
                through_month = (query.get("through_month") or [""])[0]
                payload = REPOSITORY.excel_export_payload(hid, from_month, through_month)
                workbook = build_forecast_workbook(payload)
                safe_household = re.sub(r"[^A-Za-z0-9_-]+", "-", payload["household"]["name"]).strip("-") or "Haushalt"
                filename = f"Haushaltsplaner-{safe_household}-{payload['from_month']}-bis-{payload['through_month']}.xlsx"
                return self.file_response(
                    workbook,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    filename,
                )
            if path.startswith("/api/accounts/") and path.endswith("/balances"):
                parts = path.strip("/").split("/")
                hid = (query.get("household_id") or [""])[0]
                if len(parts) != 4:
                    return self.json_response({"error": "Nicht gefunden."}, 404)
                return self.json_response({"items": REPOSITORY.list_balance_history(hid, parts[2])})
            relative = "index.html" if path == "/" else path.lstrip("/")
            static_root = (ROOT / "static").resolve()
            file_path = (static_root / relative).resolve()
            if file_path.is_file() and static_root in file_path.parents:
                data = file_path.read_bytes()
                mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
                self.send_response(200)
                self.send_header("Content-Type", f"{mime}; charset=utf-8" if mime.startswith(("text/", "application/javascript")) else mime)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                return self.wfile.write(data)
            self.json_response({"error": "Nicht gefunden."}, 404)
        except KeyError:
            self.json_response({"error": "Haushalt nicht gefunden."}, 404)
        except PermissionError as exc:
            self.json_response({"error": str(exc)}, 403)
        except Exception as exc:
            self.json_response({"error": str(exc)}, 400)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            if path in ("/api/setup", "/api/households"):
                return self.json_response(REPOSITORY.create_household(self.read_json()), 201)
            if path == "/api/accounts":
                return self.json_response(REPOSITORY.create_account(self.read_json()), 201)
            if path == "/api/categories":
                return self.json_response(REPOSITORY.create_category(self.read_json()), 201)
            if path == "/api/cash-flows":
                return self.json_response(REPOSITORY.create_cash_flow(self.read_json()), 201)
            if path == "/api/integrations/energylab":
                return self.json_response(REPOSITORY.save_energylab_integration(self.read_json()))
            if path == "/api/integrations/energylab/sync":
                payload = self.read_json()
                return self.json_response(ENERGYLAB.sync(payload.get("household_id")))
            if path == "/api/integrations/energylab/preview":
                payload = self.read_json()
                return self.json_response(ENERGYLAB.preview(payload.get("household_id")))
            if path == "/api/integrations/energylab/payment-events":
                payload = self.read_json()
                return self.json_response(REPOSITORY.record_energylab_payment_event(
                    payload.get("household_id"), payload), 201)
            if path == "/api/integrations/energylab/billing-snapshots":
                payload = self.read_json()
                return self.json_response(REPOSITORY.create_energylab_billing_snapshot(
                    payload.get("household_id"), payload), 201)
            if path == "/api/backups":
                payload = self.read_json()
                return self.json_response(REPOSITORY.create_backup(payload.get("reason") or "manuell"), 201)
            if path.startswith("/api/backups/") and path.endswith("/restore"):
                parts = path.strip("/").split("/")
                if len(parts) != 4:
                    return self.json_response({"error": "Nicht gefunden."}, 404)
                return self.json_response(REPOSITORY.restore_backup(parts[2]))
            if path == "/api/bank-statements/preview":
                payload = self.read_json(max_bytes=10 * 1024 * 1024)
                return self.json_response(REPOSITORY.save_bank_statement_preview(
                    payload.get("household_id"), payload.get("account_id"), payload.get("parsed")), 201)
            if path == "/api/bank-statements/commit":
                payload = self.read_json(max_bytes=10 * 1024 * 1024)
                return self.json_response(REPOSITORY.commit_bank_statement_preview(
                    payload.get("household_id"), payload.get("account_id"), payload.get("preview_id"),
                    payload.get("decisions") or [], payload.get("closing_balance_cents"), payload.get("balance_date")), 201)
            if path == "/api/transfers":
                return self.json_response(REPOSITORY.create_transfer(self.read_json()), 201)
            if path == "/api/credits":
                return self.json_response(REPOSITORY.create_credit(self.read_json()), 201)
            if path == "/api/interest/bookings":
                return self.json_response(REPOSITORY.create_interest_booking(self.read_json()), 201)
            if path.startswith("/api/credits/") and path.endswith("/payments"):
                parts = path.strip("/").split("/")
                if len(parts) != 4:
                    return self.json_response({"error": "Nicht gefunden."}, 404)
                return self.json_response(REPOSITORY.add_credit_payment(parts[2], self.read_json()), 201)
            if path == "/api/dashboard/simulation":
                payload = self.read_json()
                return self.json_response(REPOSITORY.simulation_dashboard(
                    payload.get("household_id"), payload.get("as_of"), payload.get("account_ids") or [],
                    payload.get("excluded_cash_flow_ids") or []))
            if path == "/api/preview/monthly":
                payload = self.read_json()
                return self.json_response(REPOSITORY.monthly_preview(
                    payload.get("household_id"), payload.get("month"), payload.get("account_ids") or [],
                    payload.get("credit_ids") or []))
            self.json_response({"error": "Nicht gefunden."}, 404)
        except (ValueError, json.JSONDecodeError) as exc:
            self.json_response({"error": str(exc)}, 400)
        except Exception:
            self.json_response({"error": "Die Anfrage konnte nicht verarbeitet werden."}, 500)

    def do_PUT(self):
        path = urlparse(self.path).path
        try:
            if path == "/api/movement-completion":
                return self.json_response(REPOSITORY.set_movement_completion(self.read_json()))
            if path == "/api/movement-amount":
                return self.json_response(REPOSITORY.set_movement_amount(self.read_json()))
            if path.startswith("/api/integrations/energylab/flows/") and path.endswith("/account"):
                parts = path.strip("/").split("/")
                if len(parts) != 6:
                    return self.json_response({"error": "Nicht gefunden."}, 404)
                return self.json_response(REPOSITORY.update_energylab_cash_flow_account(parts[4], self.read_json()))
            if path.startswith("/api/categories/"):
                category_id = path.removeprefix("/api/categories/")
                if not category_id or "/" in category_id:
                    return self.json_response({"error": "Nicht gefunden."}, 404)
                return self.json_response(REPOSITORY.update_category(category_id, self.read_json()))
            if path.startswith("/api/accounts/"):
                account_id = path.removeprefix("/api/accounts/")
                if not account_id or "/" in account_id:
                    return self.json_response({"error": "Nicht gefunden."}, 404)
                return self.json_response(REPOSITORY.update_account(account_id, self.read_json()))
            if path.startswith("/api/cash-flows/"):
                flow_id = path.removeprefix("/api/cash-flows/")
                if not flow_id or "/" in flow_id:
                    return self.json_response({"error": "Nicht gefunden."}, 404)
                return self.json_response(REPOSITORY.update_cash_flow(flow_id, self.read_json()))
            if path.startswith("/api/transfers/"):
                transfer_id = path.removeprefix("/api/transfers/")
                if not transfer_id or "/" in transfer_id:
                    return self.json_response({"error": "Nicht gefunden."}, 404)
                return self.json_response(REPOSITORY.update_transfer(transfer_id, self.read_json()))
            if path.startswith("/api/credits/"):
                credit_id = path.removeprefix("/api/credits/")
                if not credit_id or "/" in credit_id:
                    return self.json_response({"error": "Nicht gefunden."}, 404)
                return self.json_response(REPOSITORY.update_credit(credit_id, self.read_json()))
            self.json_response({"error": "Nicht gefunden."}, 404)
        except (ValueError, json.JSONDecodeError) as exc:
            self.json_response({"error": str(exc)}, 400)
        except Exception:
            self.json_response({"error": "Die Anfrage konnte nicht verarbeitet werden."}, 500)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path, query = parsed.path, parse_qs(parsed.query)
        hid = (query.get("household_id") or [""])[0]
        try:
            if path.startswith("/api/categories/"):
                category_id = path.removeprefix("/api/categories/")
                if not category_id or "/" in category_id:
                    return self.json_response({"error": "Nicht gefunden."}, 404)
                return self.json_response(REPOSITORY.delete_category(hid, category_id))
            if path.startswith("/api/accounts/") and "/balances/" in path:
                parts = path.strip("/").split("/")
                if len(parts) != 5:
                    return self.json_response({"error": "Nicht gefunden."}, 404)
                return self.json_response(REPOSITORY.delete_balance_entry(hid, parts[2], parts[4]))
            if path.startswith("/api/accounts/"):
                account_id = path.removeprefix("/api/accounts/")
                if not account_id or "/" in account_id:
                    return self.json_response({"error": "Nicht gefunden."}, 404)
                return self.json_response(REPOSITORY.delete_account(hid, account_id))
            if path.startswith("/api/cash-flows/"):
                flow_id = path.removeprefix("/api/cash-flows/")
                if not flow_id or "/" in flow_id:
                    return self.json_response({"error": "Nicht gefunden."}, 404)
                return self.json_response(REPOSITORY.delete_cash_flow(hid, flow_id))
            if path.startswith("/api/transfers/"):
                transfer_id = path.removeprefix("/api/transfers/")
                if not transfer_id or "/" in transfer_id:
                    return self.json_response({"error": "Nicht gefunden."}, 404)
                return self.json_response(REPOSITORY.delete_transfer(hid, transfer_id))
            if path.startswith("/api/credits/") and "/payments/" in path:
                parts = path.strip("/").split("/")
                if len(parts) != 5:
                    return self.json_response({"error": "Nicht gefunden."}, 404)
                return self.json_response(REPOSITORY.delete_credit_payment(hid, parts[2], parts[4]))
            if path.startswith("/api/interest/bookings/"):
                booking_id = path.removeprefix("/api/interest/bookings/")
                if not booking_id or "/" in booking_id:
                    return self.json_response({"error": "Nicht gefunden."}, 404)
                return self.json_response(REPOSITORY.delete_interest_booking(hid, booking_id))
            if path.startswith("/api/credits/"):
                credit_id = path.removeprefix("/api/credits/")
                if not credit_id or "/" in credit_id:
                    return self.json_response({"error": "Nicht gefunden."}, 404)
                return self.json_response(REPOSITORY.delete_credit(hid, credit_id))
            if path.startswith("/api/households/"):
                household_id = path.removeprefix("/api/households/")
                if not household_id or "/" in household_id:
                    return self.json_response({"error": "Nicht gefunden."}, 404)
                return self.json_response(REPOSITORY.delete_household(household_id))
            self.json_response({"error": "Nicht gefunden."}, 404)
        except ValueError as exc:
            self.json_response({"error": str(exc)}, 400)
        except Exception:
            self.json_response({"error": "Die Anfrage konnte nicht verarbeitet werden."}, 500)

    def log_message(self, fmt, *args):
        pass


def energylab_scheduler():
    interval = max(300, int(os.getenv("ENERGYLAB_SYNC_INTERVAL_SECONDS", "21600")))
    while True:
        ENERGYLAB.sync_all()
        time.sleep(interval)


def run(port=8798):
    global REPOSITORY, ENERGYLAB
    REPOSITORY = Repository()
    ENERGYLAB = EnergyLabService(REPOSITORY)
    threading.Thread(target=energylab_scheduler, daemon=True, name="energylab-sync").start()
    print(f"Haushaltsplaner läuft auf http://0.0.0.0:{port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
