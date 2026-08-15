import json
import mimetypes
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app.application.excel_export import build_forecast_workbook
from app.infrastructure.repository import Repository

ROOT = Path(__file__).resolve().parent
REPOSITORY = None


class Handler(BaseHTTPRequestHandler):
    server_version = "Haushaltsplaner/0.11.5"

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
                return self.json_response({"status": "ok", "version": "0.11.5"})
            if path == "/api/households":
                return self.json_response({"items": REPOSITORY.list_households()})
            if path == "/api/dashboard":
                hid = (query.get("household_id") or [""])[0]
                as_of = (query.get("as_of") or [None])[0]
                return self.json_response(REPOSITORY.dashboard(hid, as_of))
            if path == "/api/cash-flows":
                hid = (query.get("household_id") or [""])[0]
                kind = (query.get("kind") or [""])[0]
                as_of = (query.get("as_of") or [None])[0]
                return self.json_response({"items": REPOSITORY.list_cash_flows(hid, kind, as_of)})
            if path == "/api/diagnostics":
                hid = (query.get("household_id") or [""])[0]
                as_of = (query.get("as_of") or [None])[0]
                return self.json_response(REPOSITORY.cash_flow_diagnostics(hid, as_of))
            if path == "/api/transfers":
                hid = (query.get("household_id") or [""])[0]
                return self.json_response({"items": REPOSITORY.list_transfers(hid)})
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
        except Exception as exc:
            self.json_response({"error": str(exc)}, 400)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            if path in ("/api/setup", "/api/households"):
                return self.json_response(REPOSITORY.create_household(self.read_json()), 201)
            if path == "/api/accounts":
                return self.json_response(REPOSITORY.create_account(self.read_json()), 201)
            if path == "/api/cash-flows":
                return self.json_response(REPOSITORY.create_cash_flow(self.read_json()), 201)
            if path == "/api/transfers":
                return self.json_response(REPOSITORY.create_transfer(self.read_json()), 201)
            if path == "/api/dashboard/simulation":
                payload = self.read_json()
                return self.json_response(REPOSITORY.simulation_dashboard(
                    payload.get("household_id"), payload.get("as_of"), payload.get("account_ids") or [],
                    payload.get("excluded_cash_flow_ids") or []))
            if path == "/api/preview/monthly":
                payload = self.read_json()
                return self.json_response(REPOSITORY.monthly_preview(
                    payload.get("household_id"), payload.get("month"), payload.get("account_ids") or []))
            self.json_response({"error": "Nicht gefunden."}, 404)
        except (ValueError, json.JSONDecodeError) as exc:
            self.json_response({"error": str(exc)}, 400)
        except Exception:
            self.json_response({"error": "Die Anfrage konnte nicht verarbeitet werden."}, 500)

    def do_PUT(self):
        path = urlparse(self.path).path
        try:
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
            if path.startswith("/api/accounts/") and "/balances/" in path:
                parts = path.strip("/").split("/")
                if len(parts) != 5:
                    return self.json_response({"error": "Nicht gefunden."}, 404)
                return self.json_response(REPOSITORY.delete_balance_entry(hid, parts[2], parts[4]))
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


def run(port=8798):
    global REPOSITORY
    REPOSITORY = Repository()
    print(f"Haushaltsplaner läuft auf http://0.0.0.0:{port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
