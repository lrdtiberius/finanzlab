import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from app.application.excel_export import build_forecast_workbook
from app.infrastructure.repository import Repository


class PlanningModelV011Tests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repository = Repository(Path(self.temp_dir.name) / "planner.db")
        household = self.repository.create_household(
            {"name": "Testhaushalt", "mode": "single", "person_a": "Alex"}
        )
        self.household_id = household["id"]
        detail = self.repository.create_account(
            {
                "household_id": self.household_id,
                "name": "Girokonto",
                "owner": "A",
                "balance_cents": 100_000,
                "anchor_date": "2026-08-15",
                "bookings_applied": False,
                "overdraft_limit_cents": 50_000,
            }
        )
        self.giro_id = detail["accounts"][0]["id"]

    def tearDown(self):
        self.temp_dir.cleanup()

    def flow(self, **overrides):
        payload = {
            "household_id": self.household_id,
            "kind": "expense",
            "name": "Rate",
            "category": "other_expense",
            "amount_cents": 10_000,
            "recurrence": "once",
            "due_date": "2026-08-15",
            "effective_from": "2026-08-01",
            "account_id": self.giro_id,
            "owner": "A",
            "active": True,
        }
        payload.update(overrides)
        return payload

    def account_update(self, **overrides):
        payload = {
            "household_id": self.household_id,
            "name": "Girokonto",
            "owner": "A",
            "balance_cents": 100_000,
            "anchor_date": "2026-08-15",
            "bookings_applied": False,
            "overdraft_limit_cents": 50_000,
            "overdraft_apr": "0",
            "is_default": True,
        }
        payload.update(overrides)
        return payload

    def test_same_day_checkbox_controls_projection_and_history_is_retained(self):
        self.repository.create_cash_flow(self.flow())
        open_day = self.repository.dashboard(self.household_id, "2026-08-15")
        self.assertEqual(90_000, open_day["household"]["accounts"][0]["projected_balance_cents"])

        self.repository.update_account(
            self.giro_id, self.account_update(bookings_applied=True)
        )
        closed_day = self.repository.dashboard(self.household_id, "2026-08-15")
        self.assertEqual(100_000, closed_day["household"]["accounts"][0]["projected_balance_cents"])

        self.repository.update_account(
            self.giro_id,
            self.account_update(
                balance_cents=95_000,
                anchor_date="2026-08-16",
                bookings_applied=False,
            ),
        )
        history = self.repository.list_balance_history(
            self.household_id, self.giro_id
        )
        self.assertEqual(["2026-08-16", "2026-08-15"], [row["anchor_date"] for row in history])
        self.assertEqual([0, 1], [row["bookings_applied"] for row in history])

    def test_account_can_be_deleted_without_deleting_linked_cash_flows(self):
        detail = self.repository.create_account(
            {
                "household_id": self.household_id,
                "name": "Ersatzkonto",
                "owner": "A",
                "balance_cents": 25_000,
                "anchor_date": "2026-08-15",
                "bookings_applied": True,
            }
        )
        replacement_id = next(
            account["id"] for account in detail["accounts"] if account["name"] == "Ersatzkonto"
        )
        income = self.repository.create_cash_flow(
            self.flow(
                kind="income",
                name="Zugeordnete Einnahme",
                category="salary",
                account_id=self.giro_id,
            )
        )
        self.repository.create_transfer(
            {
                "household_id": self.household_id,
                "name": "Zum Ersatzkonto",
                "source_account_id": self.giro_id,
                "target_account_id": replacement_id,
                "amount_cents": 5_000,
                "recurrence": "once",
                "due_date": "2026-08-15",
                "active": True,
            }
        )

        result = self.repository.delete_account(self.household_id, self.giro_id)
        self.assertTrue(result["deleted"])
        self.assertEqual(1, result["unassigned_cash_flow_count"])
        self.assertEqual(1, result["deleted_transfer_count"])
        self.assertGreaterEqual(result["deleted_history_count"], 1)

        remaining = self.repository.household_detail(self.household_id, "2026-08-15")["accounts"]
        self.assertEqual([replacement_id], [account["id"] for account in remaining])
        self.assertTrue(remaining[0]["is_default"])
        unassigned = next(
            item
            for item in self.repository.list_cash_flows(
                self.household_id, "income", "2026-08-15"
            )
            if item["id"] == income["id"]
        )
        self.assertIsNone(unassigned["account_id"])
        self.assertTrue(all(version["account_id"] is None for version in unassigned["versions"]))
        self.assertEqual([], self.repository.list_transfers(self.household_id))

        reopened = Repository(Path(self.temp_dir.name) / "planner.db")
        self.assertEqual(
            [replacement_id],
            [account["id"] for account in reopened.household_detail(self.household_id)["accounts"]],
        )
        reopened.delete_account(self.household_id, replacement_id)
        self.assertEqual([], reopened.household_detail(self.household_id)["accounts"])
        recreated = reopened.create_account(
            {
                "household_id": self.household_id,
                "name": "Neues erstes Konto",
                "owner": "A",
                "balance_cents": 0,
                "anchor_date": "2026-08-16",
                "bookings_applied": False,
            }
        )
        self.assertEqual(1, len(recreated["accounts"]))
        self.assertTrue(recreated["accounts"][0]["is_default"])

    def test_balance_and_same_day_checkbox_survive_a_repository_restart(self):
        self.repository.create_cash_flow(self.flow())
        self.repository.update_account(
            self.giro_id,
            self.account_update(balance_cents=123_456, bookings_applied=True),
        )

        reopened = Repository(Path(self.temp_dir.name) / "planner.db")
        history = reopened.list_balance_history(self.household_id, self.giro_id)
        same_day = [row for row in history if row["anchor_date"] == "2026-08-15"]
        self.assertEqual(1, len(same_day))
        self.assertEqual(123_456, same_day[0]["balance_cents"])
        self.assertEqual(1, same_day[0]["bookings_applied"])
        self.assertEqual(
            123_456,
            reopened.dashboard(self.household_id, "2026-08-15")["household"]["accounts"][0]["projected_balance_cents"],
        )

        reopened.update_account(
            self.giro_id,
            self.account_update(balance_cents=130_000, bookings_applied=False),
        )
        reopened_again = Repository(Path(self.temp_dir.name) / "planner.db")
        history = reopened_again.list_balance_history(self.household_id, self.giro_id)
        same_day = [row for row in history if row["anchor_date"] == "2026-08-15"]
        self.assertEqual(1, len(same_day))
        self.assertEqual(130_000, same_day[0]["balance_cents"])
        self.assertEqual(0, same_day[0]["bookings_applied"])
        self.assertEqual(
            120_000,
            reopened_again.dashboard(self.household_id, "2026-08-15")["household"]["accounts"][0]["projected_balance_cents"],
        )

    def test_first_account_rejects_an_invalid_balance_date_before_saving(self):
        with self.assertRaisesRegex(ValueError, "Stichtag.*gültiges Datum"):
            self.repository.create_household(
                {
                    "name": "Ungültiger Haushalt",
                    "mode": "single",
                    "person_a": "Alex",
                    "account": {
                        "name": "Startkonto",
                        "anchor_date": "31.02.2026",
                        "balance_cents": 100_000,
                    },
                }
            )
        self.assertNotIn(
            "Ungültiger Haushalt",
            {item["name"] for item in self.repository.list_households()},
        )

    def test_exactly_one_default_account_and_credit_is_an_expense_category(self):
        initial = self.repository.household_detail(self.household_id, "2026-08-15")
        self.assertTrue(initial["accounts"][0]["is_default"])
        detail = self.repository.create_account(
            {
                "household_id": self.household_id,
                "name": "Tagesgeld",
                "owner": "A",
                "balance_cents": 20_000,
                "anchor_date": "2026-08-15",
                "bookings_applied": False,
                "is_default": True,
            }
        )
        defaults = [account for account in detail["accounts"] if account["is_default"]]
        self.assertEqual(["Tagesgeld"], [account["name"] for account in defaults])
        credit = self.repository.create_credit(
            {
                "household_id": self.household_id,
                "name": "Testkredit",
                "credit_type": "credit",
                "opening_balance_cents": 50_000,
            }
        )
        expense = self.repository.create_cash_flow(
            self.flow(category="credit", credit_id=credit["id"])
        )
        self.assertEqual("expense", expense["kind"])
        self.assertEqual("credit", expense["category"])

    def test_credit_history_annuity_split_and_preview_are_separate_from_accounts(self):
        today = date.today()
        tomorrow = today + timedelta(days=1)
        credit = self.repository.create_credit(
            {
                "household_id": self.household_id,
                "name": "Annuitätendarlehen",
                "credit_type": "consumer_credit",
                "opening_balance_cents": 100_000,
                "note": "400 Euro Rate, davon 320 Euro Tilgung",
            }
        )
        self.repository.create_credit(
            {
                "household_id": self.household_id,
                "name": "Privatkredit",
                "credit_type": "credit",
                "opening_balance_cents": 50_000,
            }
        )
        self.repository.create_credit(
            {
                "household_id": self.household_id,
                "name": "Von Familie geliehen",
                "credit_type": "borrowed",
                "opening_balance_cents": 25_000,
            }
        )
        expense = self.repository.create_cash_flow(
            self.flow(
                name="Kreditrate",
                category="consumer_credit",
                amount_cents=40_000,
                credit_id=credit["id"],
                credit_reduction_cents=32_000,
                due_date=today.isoformat(),
                effective_from=today.isoformat(),
            )
        )
        self.repository.add_credit_payment(
            credit["id"],
            {
                "household_id": self.household_id,
                "payment_date": today.isoformat(),
                "amount_cents": 5_000,
                "note": "Zusätzliche Tilgung",
            },
        )
        self.repository.add_credit_payment(
            credit["id"],
            {
                "household_id": self.household_id,
                "payment_date": tomorrow.isoformat(),
                "amount_cents": 10_000,
                "note": "Geplante Sondertilgung",
            },
        )

        current = self.repository.credit_detail(self.household_id, credit["id"])
        self.assertEqual(63_000, current["remaining_balance_cents"])
        self.assertEqual(
            {"expense", "manual"}, {payment["source"] for payment in current["payments"]}
        )
        future = next(
            payment for payment in current["payments"] if payment["date"] == tomorrow.isoformat()
        )
        self.assertTrue(future["future"])
        self.assertFalse(future["applied"])

        dashboard = self.repository.dashboard(self.household_id, today.isoformat())
        account = dashboard["household"]["accounts"][0]
        self.assertEqual(60_000, account["projected_balance_cents"])
        groups = {item["credit_type"]: item for item in dashboard["credit_summary"]["groups"]}
        self.assertEqual((1, 63_000), (groups["consumer_credit"]["count"], groups["consumer_credit"]["balance_cents"]))
        self.assertEqual((1, 50_000), (groups["credit"]["count"], groups["credit"]["balance_cents"]))
        self.assertEqual((1, 25_000), (groups["borrowed"]["count"], groups["borrowed"]["balance_cents"]))

        preview = self.repository.monthly_preview(
            self.household_id, today.strftime("%Y-%m"), [self.giro_id], [credit["id"]]
        )
        self.assertEqual(60_000, preview["totals"]["closing_balance_cents"])
        self.assertEqual(53_000, preview["credit_totals"]["closing_balance_cents"])
        self.assertEqual(47_000, preview["credit_totals"]["reduction_cents"])
        tomorrow_row = next(row for row in preview["days"] if row["date"] == tomorrow.isoformat())
        self.assertEqual(53_000, tomorrow_row["credits"][0]["remaining_balance_cents"])
        self.assertEqual(10_000, tomorrow_row["credits"][0]["reduction_cents"])
        self.assertEqual([], tomorrow_row["movements"])
        self.assertEqual(expense["id"], next(payment for payment in current["payments"] if payment["source"] == "expense")["source_id"])

    def test_credit_link_requires_matching_type_and_valid_principal_share(self):
        credit = self.repository.create_credit(
            {
                "household_id": self.household_id,
                "name": "Konsum",
                "credit_type": "consumer_credit",
                "opening_balance_cents": 100_000,
            }
        )
        with self.assertRaisesRegex(ValueError, "Ausgabenart und Kreditart"):
            self.repository.create_cash_flow(
                self.flow(category="credit", credit_id=credit["id"])
            )
        with self.assertRaisesRegex(ValueError, "zwischen 0,00 €"):
            self.repository.create_cash_flow(
                self.flow(
                    category="consumer_credit",
                    credit_id=credit["id"],
                    amount_cents=10_000,
                    credit_reduction_cents=12_000,
                )
            )
        linked = self.repository.create_cash_flow(
            self.flow(
                name="Später verwaiste Rate",
                category="consumer_credit",
                credit_id=credit["id"],
                amount_cents=10_000,
                credit_reduction_cents=8_000,
            )
        )
        self.repository.delete_credit(self.household_id, credit["id"])
        diagnostics = self.repository.cash_flow_diagnostics(
            self.household_id, date.today().isoformat()
        )
        orphan = next(item for item in diagnostics["items"] if item["id"] == linked["id"])
        self.assertIn("missing_credit", {issue["code"] for issue in orphan["issues"]})
        self.assertTrue(orphan["not_considered"])

    def test_transfer_moves_money_between_accounts_without_changing_total(self):
        detail = self.repository.create_account(
            {
                "household_id": self.household_id,
                "name": "Tagesgeld",
                "owner": "A",
                "balance_cents": 20_000,
                "anchor_date": "2026-08-15",
                "bookings_applied": False,
            }
        )
        savings_id = next(a["id"] for a in detail["accounts"] if a["name"] == "Tagesgeld")
        transfer = self.repository.create_transfer(
            {
                "household_id": self.household_id,
                "name": "Rücklage",
                "source_account_id": self.giro_id,
                "target_account_id": savings_id,
                "amount_cents": 30_000,
                "recurrence": "once",
                "due_date": "2026-08-15",
                "active": True,
            }
        )
        dashboard = self.repository.dashboard(self.household_id, "2026-08-15")
        balances = {a["name"]: a["projected_balance_cents"] for a in dashboard["household"]["accounts"]}
        self.assertEqual({"Girokonto": 70_000, "Tagesgeld": 50_000}, balances)
        self.assertEqual(120_000, dashboard["metrics"]["balance_cents"])
        preview = self.repository.monthly_preview(
            self.household_id, "2026-08", [self.giro_id, savings_id]
        )
        legs = [item for item in preview["movements"] if item["source_id"] == transfer["id"]]
        self.assertEqual({"transfer_out", "transfer_in"}, {item["kind"] for item in legs})
        self.assertEqual(0, sum(item["amount_cents"] for item in legs))
        self.assertEqual(31, len(preview["days"]))
        transfer_day = next(day for day in preview["days"] if day["date"] == "2026-08-15")
        self.assertEqual(2, transfer_day["movement_count"])
        self.assertEqual(
            {"Girokonto": 70_000, "Tagesgeld": 50_000},
            {item["name"]: item["projected_balance_cents"] for item in transfer_day["balances"]},
        )

    def test_semiannual_income_and_expense_repeat_every_six_months(self):
        income = self.repository.create_cash_flow(
            self.flow(
                kind="income",
                name="Halbjährliche Einnahme",
                category="other_income",
                amount_cents=60_000,
                recurrence="semiannual",
                due_date="2026-08-20",
            )
        )
        expense = self.repository.create_cash_flow(
            self.flow(
                name="Halbjährliche Ausgabe",
                amount_cents=30_000,
                recurrence="semiannual",
                due_date="2026-08-20",
            )
        )

        august = self.repository.monthly_preview(
            self.household_id, "2026-08", [self.giro_id]
        )
        september = self.repository.monthly_preview(
            self.household_id, "2026-09", [self.giro_id]
        )
        february = self.repository.monthly_preview(
            self.household_id, "2027-02", [self.giro_id]
        )
        self.assertEqual(
            {income["id"], expense["id"]},
            {
                item["source_id"]
                for item in august["movements"]
                if item["source_id"] in (income["id"], expense["id"])
            },
        )
        self.assertFalse(
            any(
                item["source_id"] in (income["id"], expense["id"])
                for item in september["movements"]
            )
        )
        self.assertEqual(
            {income["id"], expense["id"]},
            {
                item["source_id"]
                for item in february["movements"]
                if item["source_id"] in (income["id"], expense["id"])
            },
        )

        dashboard = self.repository.dashboard(self.household_id, "2026-09-01")
        self.assertEqual(0, dashboard["metrics"]["income_cents"])
        self.assertEqual(0, dashboard["metrics"]["expenses_cents"])
        diagnostics = self.repository.cash_flow_diagnostics(
            self.household_id, "2026-09-01"
        )
        self.assertNotIn(
            "invalid_recurrence",
            {
                issue["code"]
                for item in diagnostics["items"]
                for issue in item["issues"]
            },
        )
        export_payload = self.repository.excel_export_payload(
            self.household_id, "2026-08", "2027-02"
        )
        with ZipFile(BytesIO(build_forecast_workbook(export_payload))) as archive:
            self.assertIn(
                "Halbjährlich",
                archive.read("xl/worksheets/sheet7.xml").decode("utf-8"),
            )

    def test_dashboard_monthly_totals_use_due_occurrences_and_match_preview(self):
        self.repository.create_cash_flow(
            self.flow(
                kind="income",
                name="Monatliche Einnahme",
                category="other_income",
                amount_cents=10_000,
                recurrence="monthly",
                due_date="2026-08-20",
            )
        )
        self.repository.create_cash_flow(
            self.flow(
                kind="income",
                name="Vierteljährliche Einnahme",
                category="other_income",
                amount_cents=30_000,
                recurrence="quarterly",
                due_date="2026-08-21",
            )
        )
        self.repository.create_cash_flow(
            self.flow(
                name="Monatliche Ausgabe",
                amount_cents=5_000,
                recurrence="monthly",
                due_date="2026-08-20",
            )
        )
        self.repository.create_cash_flow(
            self.flow(
                name="Vierteljährliche Ausgabe",
                amount_cents=15_000,
                recurrence="quarterly",
                due_date="2026-08-21",
            )
        )
        self.repository.create_cash_flow(
            self.flow(
                name="Einmalige September-Ausgabe",
                amount_cents=7_000,
                recurrence="once",
                due_date="2026-09-03",
            )
        )

        september_dashboard = self.repository.dashboard(
            self.household_id, "2026-09-01"
        )
        september_preview = self.repository.monthly_preview(
            self.household_id, "2026-09", [self.giro_id]
        )
        self.assertEqual(10_000, september_dashboard["metrics"]["income_cents"])
        self.assertEqual(12_000, september_dashboard["metrics"]["expenses_cents"])
        self.assertEqual(
            september_preview["totals"]["income_cents"],
            september_dashboard["metrics"]["income_cents"],
        )
        self.assertEqual(
            september_preview["totals"]["expense_cents"],
            september_dashboard["metrics"]["expenses_cents"],
        )
        self.assertNotIn(
            "Vierteljährliche Ausgabe",
            {item["label"] for item in september_dashboard["breakdowns"]["expenses"]},
        )

        november_dashboard = self.repository.dashboard(
            self.household_id, "2026-11-01"
        )
        self.assertEqual(40_000, november_dashboard["metrics"]["income_cents"])
        self.assertEqual(20_000, november_dashboard["metrics"]["expenses_cents"])

    def test_completed_movement_stays_visible_but_is_not_projected(self):
        expense = self.repository.create_cash_flow(
            self.flow(
                name="Erledigbare Ausgabe",
                amount_cents=10_000,
                due_date="2026-08-16",
            )
        )
        occurrence_key=f"cash-flow:{expense['id']}:2026-08-16"

        before = self.repository.monthly_preview(
            self.household_id, "2026-08", [self.giro_id]
        )
        before_movement = next(
            item for item in before["movements"] if item["source_id"] == expense["id"]
        )
        self.assertFalse(before_movement["completed"])
        self.assertTrue(before_movement["completion_allowed"])
        self.assertTrue(before_movement["applied_to_projection"])
        self.assertEqual(90_000, before["totals"]["closing_balance_cents"])
        self.assertEqual(10_000, before["totals"]["expense_cents"])

        self.repository.set_movement_completion(
            {
                "household_id": self.household_id,
                "occurrence_key": occurrence_key,
                "completed": True,
            }
        )
        completed = self.repository.monthly_preview(
            self.household_id, "2026-08", [self.giro_id]
        )
        completed_movement = next(
            item for item in completed["movements"] if item["source_id"] == expense["id"]
        )
        self.assertTrue(completed_movement["completed"])
        self.assertFalse(completed_movement["applied_to_projection"])
        self.assertEqual(100_000, completed["totals"]["closing_balance_cents"])
        self.assertEqual(0, completed["totals"]["expense_cents"])
        completed_day = next(day for day in completed["days"] if day["date"] == "2026-08-16")
        self.assertEqual(0, completed_day["delta_cents"])
        self.assertEqual(
            100_000,
            self.repository.dashboard(self.household_id, "2026-08-16")["metrics"]["balance_cents"],
        )
        export_payload = self.repository.excel_export_payload(
            self.household_id, "2026-08", "2026-08"
        )
        with ZipFile(BytesIO(build_forecast_workbook(export_payload))) as archive:
            movements_xml=archive.read("xl/worksheets/sheet5.xml").decode("utf-8")
            self.assertIn("Vorgang erledigt", movements_xml)
            self.assertIn("Erledigbare Ausgabe", movements_xml)

        reopened = Repository(Path(self.temp_dir.name) / "planner.db")
        persisted = reopened.monthly_preview(
            self.household_id, "2026-08", [self.giro_id]
        )
        self.assertTrue(
            next(item for item in persisted["movements"] if item["source_id"] == expense["id"])["completed"]
        )
        reopened.set_movement_completion(
            {
                "household_id": self.household_id,
                "occurrence_key": occurrence_key,
                "completed": False,
            }
        )
        reopened_preview = reopened.monthly_preview(
            self.household_id, "2026-08", [self.giro_id]
        )
        self.assertEqual(90_000, reopened_preview["totals"]["closing_balance_cents"])
        self.assertEqual(10_000, reopened_preview["totals"]["expense_cents"])

    def test_completed_transfer_is_removed_from_both_accounts_together(self):
        detail = self.repository.create_account(
            {
                "household_id": self.household_id,
                "name": "Tagesgeld für Erledigt-Test",
                "owner": "A",
                "balance_cents": 20_000,
                "anchor_date": "2026-08-15",
                "bookings_applied": False,
            }
        )
        savings_id = next(
            account["id"] for account in detail["accounts"]
            if account["name"] == "Tagesgeld für Erledigt-Test"
        )
        transfer = self.repository.create_transfer(
            {
                "household_id": self.household_id,
                "name": "Erledigte Umbuchung",
                "source_account_id": self.giro_id,
                "target_account_id": savings_id,
                "amount_cents": 30_000,
                "recurrence": "once",
                "due_date": "2026-08-16",
                "active": True,
            }
        )
        occurrence_key=f"transfer:{transfer['id']}:2026-08-16"
        self.repository.set_movement_completion(
            {
                "household_id": self.household_id,
                "occurrence_key": occurrence_key,
                "completed": True,
            }
        )

        preview = self.repository.monthly_preview(
            self.household_id, "2026-08", [self.giro_id, savings_id]
        )
        legs=[item for item in preview["movements"] if item["source_id"] == transfer["id"]]
        self.assertEqual(2, len(legs))
        self.assertTrue(all(item["completed"] for item in legs))
        self.assertTrue(all(not item["applied_to_projection"] for item in legs))
        self.assertEqual(0, preview["totals"]["transfer_volume_cents"])
        balances={item["name"]:item["closing_balance_cents"] for item in preview["accounts"]}
        self.assertEqual(
            {"Girokonto":100_000,"Tagesgeld für Erledigt-Test":20_000}, balances
        )

        self.repository.delete_transfer(self.household_id, transfer["id"])
        with self.repository.connect() as connection:
            remaining=connection.execute(
                "SELECT COUNT(*) FROM movement_completions WHERE source_id=?",(transfer["id"],)
            ).fetchone()[0]
        self.assertEqual(0, remaining)

    def test_transfer_can_be_limited_by_inclusive_end_date_or_occurrence_count(self):
        detail = self.repository.create_account(
            {
                "household_id": self.household_id,
                "name": "Tagesgeld",
                "owner": "A",
                "balance_cents": 20_000,
                "anchor_date": "2026-08-15",
                "bookings_applied": False,
            }
        )
        savings_id = next(a["id"] for a in detail["accounts"] if a["name"] == "Tagesgeld")
        common = {
            "household_id": self.household_id,
            "source_account_id": self.giro_id,
            "target_account_id": savings_id,
            "amount_cents": 5_000,
            "recurrence": "monthly",
            "active": True,
        }
        by_end = self.repository.create_transfer(
            {
                **common,
                "name": "Bis Oktober",
                "due_date": "2026-08-15",
                "end_date": "2026-10-15",
            }
        )
        by_count = self.repository.create_transfer(
            {
                **common,
                "name": "Zweimal",
                "due_date": "2026-08-20",
                "occurrence_count": 2,
            }
        )
        matching_limits = self.repository.create_transfer(
            {
                **common,
                "name": "Passende Grenzen",
                "due_date": "2026-08-25",
                "end_date": "2026-09-25",
                "occurrence_count": 2,
            }
        )
        self.assertEqual("2026-10-15", by_end["end_date"])
        self.assertEqual(2, by_count["occurrence_count"])

        september = self.repository.monthly_preview(
            self.household_id, "2026-09", [self.giro_id, savings_id]
        )
        october = self.repository.monthly_preview(
            self.household_id, "2026-10", [self.giro_id, savings_id]
        )
        november = self.repository.monthly_preview(
            self.household_id, "2026-11", [self.giro_id, savings_id]
        )
        self.assertEqual(
            2,
            sum(1 for item in october["movements"] if item["source_id"] == by_end["id"]),
        )
        self.assertEqual(
            0,
            sum(1 for item in november["movements"] if item["source_id"] == by_end["id"]),
        )
        self.assertEqual(
            2,
            sum(1 for item in september["movements"] if item["source_id"] == by_count["id"]),
        )
        self.assertEqual(
            0,
            sum(1 for item in october["movements"] if item["source_id"] == by_count["id"]),
        )
        self.assertEqual(
            2,
            sum(1 for item in september["movements"] if item["source_id"] == matching_limits["id"]),
        )
        self.assertEqual(
            0,
            sum(1 for item in october["movements"] if item["source_id"] == matching_limits["id"]),
        )

    def test_transfer_limits_are_validated(self):
        detail = self.repository.create_account(
            {
                "household_id": self.household_id,
                "name": "Tagesgeld",
                "owner": "A",
                "balance_cents": 20_000,
                "anchor_date": "2026-08-15",
                "bookings_applied": False,
            }
        )
        savings_id = next(a["id"] for a in detail["accounts"] if a["name"] == "Tagesgeld")
        payload = {
            "household_id": self.household_id,
            "name": "Begrenzt",
            "source_account_id": self.giro_id,
            "target_account_id": savings_id,
            "amount_cents": 5_000,
            "recurrence": "monthly",
            "due_date": "2026-08-15",
            "active": True,
        }
        with self.assertRaisesRegex(ValueError, "nicht vor"):
            self.repository.create_transfer({**payload, "end_date": "2026-08-14"})
        with self.assertRaisesRegex(ValueError, "zwischen 1 und 1.200"):
            self.repository.create_transfer({**payload, "occurrence_count": 0})
        with self.assertRaisesRegex(ValueError, "erste Fälligkeit ist erforderlich"):
            self.repository.create_transfer({**payload, "due_date": ""})
        with self.assertRaisesRegex(ValueError, "passen nicht zusammen"):
            self.repository.create_transfer(
                {
                    **payload,
                    "occurrence_count": 12,
                    "end_date": "2027-06-15",
                }
            )
        matching = self.repository.create_transfer(
            {
                **payload,
                "name": "Zwölf passende Ausführungen",
                "occurrence_count": 12,
                "end_date": "2027-07-15",
            }
        )
        self.assertEqual(12, matching["occurrence_count"])
        self.assertEqual("2027-07-15", matching["end_date"])
        semiannual = self.repository.create_transfer(
            {
                **payload,
                "name": "Drei halbjährliche Ausführungen",
                "recurrence": "semiannual",
                "occurrence_count": 3,
                "end_date": "2027-08-15",
            }
        )
        self.assertEqual("semiannual", semiannual["recurrence"])
        self.assertEqual("2027-08-15", semiannual["end_date"])
        with self.assertRaisesRegex(ValueError, "nur eine Ausführung"):
            self.repository.create_transfer(
                {**payload, "recurrence": "once", "occurrence_count": 2}
            )

    def test_inconsistent_transfer_update_is_rejected_without_overwriting_data(self):
        detail = self.repository.create_account(
            {
                "household_id": self.household_id,
                "name": "Rücklage",
                "owner": "A",
                "balance_cents": 0,
                "anchor_date": "2026-08-15",
                "bookings_applied": False,
            }
        )
        target_id = next(a["id"] for a in detail["accounts"] if a["name"] == "Rücklage")
        payload = {
            "household_id": self.household_id,
            "name": "Monatliche Rücklage",
            "source_account_id": self.giro_id,
            "target_account_id": target_id,
            "amount_cents": 5_000,
            "recurrence": "monthly",
            "due_date": "2026-08-31",
            "end_date": "2026-09-30",
            "occurrence_count": 2,
            "active": True,
        }
        transfer = self.repository.create_transfer(payload)
        with self.assertRaisesRegex(ValueError, "Enddatum.*30.11.2026"):
            self.repository.update_transfer(
                transfer["id"], {**payload, "occurrence_count": 4}
            )
        unchanged = next(
            item
            for item in self.repository.list_transfers(self.household_id)
            if item["id"] == transfer["id"]
        )
        self.assertEqual(2, unchanged["occurrence_count"])
        self.assertEqual("2026-09-30", unchanged["end_date"])

    def test_overdraft_warning_appears_after_limit_is_exceeded(self):
        self.repository.update_account(
            self.giro_id,
            self.account_update(
                balance_cents=-40_000,
                anchor_date="2026-08-15",
                bookings_applied=True,
            ),
        )
        self.repository.create_cash_flow(
            self.flow(amount_cents=20_000, due_date="2026-08-16")
        )
        dashboard = self.repository.dashboard(self.household_id, "2026-08-16")
        account = dashboard["household"]["accounts"][0]
        self.assertEqual(-60_000, account["projected_balance_cents"])
        self.assertTrue(account["overdraft_exceeded"])
        self.assertEqual(10_000, account["overdraft_overage_cents"])
        self.assertEqual(1, dashboard["metrics"]["overdraft_warning_count"])

        self.repository.create_cash_flow(
            self.flow(
                kind="income",
                name="Ausgleich",
                category="other_income",
                amount_cents=30_000,
                due_date="2026-08-20",
            )
        )
        preview = self.repository.monthly_preview(
            self.household_id, "2026-08", [self.giro_id]
        )
        self.assertEqual(-30_000, preview["accounts"][0]["closing_balance_cents"])
        self.assertEqual(-60_000, preview["accounts"][0]["minimum_balance_cents"])
        self.assertTrue(preview["accounts"][0]["overdraft_exceeded_during_month"])
        self.assertEqual(10_000, preview["overdraft_warnings"][0]["overage_cents"])

    def test_diagnostics_still_report_unassigned_and_inactive_items(self):
        invalid = self.repository.create_cash_flow(
            self.flow(name="Unklar", account_id="", amount_cents=0, active=False)
        )
        diagnostics = self.repository.cash_flow_diagnostics(
            self.household_id, "2026-08-15"
        )
        item = next(row for row in diagnostics["items"] if row["id"] == invalid["id"])
        self.assertEqual(
            {"missing_account", "zero_amount", "inactive"},
            {issue["code"] for issue in item["issues"]},
        )
        self.assertTrue(item["not_considered"])

    def test_interest_and_gross_values_are_ignored(self):
        detail = self.repository.update_account(
            self.giro_id,
            self.account_update(overdraft_apr="19.75"),
        )
        account = next(item for item in detail["accounts"] if item["id"] == self.giro_id)
        self.assertNotIn("overdraft_apr", account)
        income = self.repository.create_cash_flow(
            self.flow(
                kind="income",
                name="Gehalt",
                category="salary",
                amount_cents=200_000,
                gross_amount_cents=300_000,
            )
        )
        self.assertNotIn("gross_amount_cents", income)

    def test_expense_can_end_by_duration_or_explicit_date(self):
        limited = self.repository.create_cash_flow(
            self.flow(
                name="Zwölf Monatsraten",
                recurrence="monthly",
                due_date="2026-08-15",
                duration_months=12,
            )
        )
        self.assertEqual("2027-08-15", limited["end_date"])
        self.assertEqual(12, limited["duration_months"])

        july = self.repository.monthly_preview(
            self.household_id, "2027-07", [self.giro_id]
        )
        august = self.repository.monthly_preview(
            self.household_id, "2027-08", [self.giro_id]
        )
        self.assertEqual(
            1,
            sum(1 for item in july["movements"] if item["source_id"] == limited["id"]),
        )
        self.assertEqual(
            1,
            sum(1 for item in august["movements"] if item["source_id"] == limited["id"]),
        )

        explicit = self.repository.create_cash_flow(
            self.flow(
                name="Bis November",
                recurrence="monthly",
                due_date="2026-08-20",
                end_date="2026-11-20",
            )
        )
        self.assertEqual("2026-11-20", explicit["end_date"])
        self.assertEqual(3, explicit["duration_months"])

        november = self.repository.monthly_preview(
            self.household_id, "2026-11", [self.giro_id]
        )
        december = self.repository.monthly_preview(
            self.household_id, "2026-12", [self.giro_id]
        )
        self.assertEqual(
            1,
            sum(1 for item in november["movements"] if item["source_id"] == explicit["id"]),
        )
        self.assertEqual(
            0,
            sum(1 for item in december["movements"] if item["source_id"] == explicit["id"]),
        )

    def test_end_date_itself_is_included_and_only_the_following_day_is_excluded(self):
        one_day = self.repository.create_cash_flow(
            self.flow(name="Nur am Enddatum", end_date="2026-08-15")
        )
        on_end_date = self.repository.list_cash_flows(
            self.household_id, "expense", "2026-08-15"
        )
        after_end_date = self.repository.list_cash_flows(
            self.household_id, "expense", "2026-08-16"
        )
        self.assertEqual(
            1, next(item for item in on_end_date if item["id"] == one_day["id"])["active"]
        )
        self.assertEqual(
            0, next(item for item in after_end_date if item["id"] == one_day["id"])["active"]
        )

    def test_duration_and_end_date_must_match(self):
        with self.assertRaisesRegex(ValueError, "passen nicht zusammen"):
            self.repository.create_cash_flow(
                self.flow(
                    recurrence="monthly",
                    due_date="2026-08-15",
                    duration_months=12,
                    end_date="2027-09-15",
                )
            )

    def test_cash_flow_changes_are_persisted_on_the_selected_effective_date(self):
        original = self.repository.create_cash_flow(
            self.flow(
                name="Alte Rate",
                amount_cents=10_000,
                due_date="2026-08-15",
                effective_from="2026-08-01",
            )
        )
        changed_payload = self.flow(
            name="Neue Rate",
            amount_cents=12_500,
            due_date="2026-08-20",
            effective_from="2026-08-10",
        )
        self.repository.update_cash_flow(original["id"], changed_payload)
        before = next(
            item
            for item in self.repository.list_cash_flows(
                self.household_id, "expense", "2026-08-09"
            )
            if item["id"] == original["id"]
        )
        after = next(
            item
            for item in self.repository.list_cash_flows(
                self.household_id, "expense", "2026-08-10"
            )
            if item["id"] == original["id"]
        )
        self.assertEqual(("Alte Rate", 10_000), (before["name"], before["amount_cents"]))
        self.assertEqual(("Neue Rate", 12_500), (after["name"], after["amount_cents"]))

        self.repository.update_cash_flow(
            original["id"], {**changed_payload, "amount_cents": 13_000}
        )
        updated = next(
            item
            for item in self.repository.list_cash_flows(
                self.household_id, "expense", "2026-08-10"
            )
            if item["id"] == original["id"]
        )
        self.assertEqual(13_000, updated["amount_cents"])
        self.assertEqual(2, len(updated["versions"]))

    def test_import_entry_points_are_disabled(self):
        with self.assertRaisesRegex(ValueError, "vollständig deaktiviert"):
            self.repository.save_bank_statement_preview(
                self.household_id, self.giro_id, {}
            )

    def test_excel_export_contains_forecasts_and_all_entered_positions(self):
        credit = self.repository.create_credit(
            {
                "household_id": self.household_id,
                "name": "Exportkredit",
                "credit_type": "credit",
                "opening_balance_cents": 100_000,
            }
        )
        self.repository.add_credit_payment(
            credit["id"],
            {
                "household_id": self.household_id,
                "payment_date": date.today().isoformat(),
                "amount_cents": 10_000,
                "note": "Exporttilgung",
            },
        )
        income = self.repository.create_cash_flow(
            self.flow(
                kind="income",
                name="Gehalt",
                category="salary",
                amount_cents=250_000,
                recurrence="monthly",
                due_date="2026-08-28",
            )
        )
        expense = self.repository.create_cash_flow(
            self.flow(
                name="Deaktivierte Rate",
                amount_cents=12_500,
                recurrence="monthly",
                due_date="2026-08-20",
                active=False,
            )
        )
        payload = self.repository.excel_export_payload(
            self.household_id, "2026-08", "2026-10"
        )
        self.assertEqual(3, payload["month_count"])
        self.assertEqual(
            {income["id"]}, {item["id"] for item in payload["incomes"]}
        )
        self.assertIn(expense["id"], {item["id"] for item in payload["expenses"]})
        self.assertEqual(
            750_000, sum(item["income_cents"] for item in payload["months"])
        )
        self.assertFalse(
            any(item["source_id"] == expense["id"] for item in payload["movements"])
        )
        self.assertEqual({credit["id"]}, {item["id"] for item in payload["credits"]})
        self.assertIn("Exporttilgung", {item["label"] for item in payload["credit_payments"]})

        workbook = build_forecast_workbook(payload)
        with ZipFile(BytesIO(workbook)) as archive:
            names = set(archive.namelist())
            self.assertIn("xl/styles.xml", names)
            self.assertIn("xl/worksheets/sheet10.xml", names)
            workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
            overview_xml = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
            self.assertIn('name="Tagesvorschau"', workbook_xml)
            self.assertIn('name="Ausgaben"', workbook_xml)
            self.assertIn('name="Kredite"', workbook_xml)
            self.assertIn('name="Kreditzahlungen"', workbook_xml)
            self.assertIn('name="Kreditvorschau"', workbook_xml)
            self.assertIn("SUM('Monatsvorschau'!E5:E7)", overview_xml)
            self.assertIn("Deaktivierte Rate", archive.read("xl/worksheets/sheet8.xml").decode("utf-8"))
            self.assertIn("Exportkredit", archive.read("xl/worksheets/sheet9.xml").decode("utf-8"))

    def test_excel_export_rejects_more_than_twenty_four_months(self):
        with self.assertRaisesRegex(ValueError, "höchstens 24 Monate"):
            self.repository.excel_export_payload(
                self.household_id, "2026-01", "2028-01"
            )


class StaticUiTests(unittest.TestCase):
    def test_dashboard_quick_actions_reuse_cash_flow_dialog(self):
        root = Path(__file__).resolve().parents[1]
        html = (root / "app/static/index.html").read_text(encoding="utf-8")
        script = (root / "app/static/app.js").read_text(encoding="utf-8")

        self.assertIn('id="dashboard-new-expense"', html)
        self.assertIn('id="dashboard-new-income"', html)
        self.assertEqual(1, html.count('id="cash-flow-dialog"'))
        self.assertIn(
            "$('#dashboard-new-expense').addEventListener('click',()=>openFlow('expense'))",
            script,
        )
        self.assertIn(
            "$('#dashboard-new-income').addEventListener('click',()=>openFlow('income'))",
            script,
        )

    def test_credit_page_contains_type_filter_with_counts(self):
        root = Path(__file__).resolve().parents[1]
        html = (root / "app/static/index.html").read_text(encoding="utf-8")
        script = (root / "app/static/app.js").read_text(encoding="utf-8")

        self.assertIn('id="credit-filter"', html)
        self.assertIn("data-credit-filter", script)
        self.assertIn("state.creditFilter==='all'", script)
        self.assertIn("aria-pressed", script)
        for credit_type in ("consumer_credit", "credit", "borrowed"):
            self.assertIn(credit_type, script)


class MigrationTests(unittest.TestCase):
    def test_legacy_loan_tables_and_rows_are_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "planner.db"
            with sqlite3.connect(path) as connection:
                connection.execute("CREATE TABLE loans(id TEXT PRIMARY KEY, name TEXT)")
                connection.execute("INSERT INTO loans VALUES('old-loan','Altvertrag')")
            repository = Repository(path)
            with repository.connect() as connection:
                loans_table = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='loans'"
                ).fetchone()
                completion_table = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='movement_completions'"
                ).fetchone()
                migration = connection.execute(
                    "SELECT 1 FROM schema_migrations WHERE name='v0.11-remove-loans-and-validity'"
                ).fetchone()
            self.assertIsNone(loans_table)
            self.assertIsNotNone(completion_table)
            self.assertIsNotNone(migration)


if __name__ == "__main__":
    unittest.main()
