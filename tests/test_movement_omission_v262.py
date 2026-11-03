import tempfile
import unittest
from pathlib import Path

from app.infrastructure.repository import Repository


class MovementOmissionV262Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "planner.db"
        self.repo = Repository(self.db)
        household = self.repo.create_household({
            "name": "Entfällt-Test",
            "mode": "single",
            "person_a": "Alex",
        })
        self.hid = household["id"]
        detail = self.repo.create_account({
            "household_id": self.hid,
            "name": "Girokonto",
            "owner": "A",
            "balance_cents": 100_000,
            "anchor_date": "2026-10-31",
            "bookings_applied": True,
        })
        self.account_id = detail["accounts"][0]["id"]

    def tearDown(self):
        self.tmp.cleanup()

    def cash_flow(self, kind, name, amount_cents, due_date):
        return self.repo.create_cash_flow({
            "household_id": self.hid,
            "kind": kind,
            "name": name,
            "category": "salary" if kind == "income" else "mobility",
            "amount_cents": amount_cents,
            "recurrence": "once",
            "due_date": due_date,
            "effective_from": "2026-10-01",
            "account_id": self.account_id,
            "owner": "A",
            "active": True,
        })

    def test_amount_override_and_omission_update_balance_and_both_dashboard_metrics(self):
        self.cash_flow("income", "Gehalt", 200_000, "2026-11-05")
        fuel = self.cash_flow("expense", "Tanken", 50_000, "2026-11-10")
        key = f"cash-flow:{fuel['id']}:2026-11-10"

        initial = self.repo.dashboard(self.hid, "2026-11-30", include_credit_summary=False)
        self.assertEqual(250_000, initial["metrics"]["balance_cents"])
        self.assertEqual(50_000, initial["metrics"]["expenses_cents"])
        self.assertEqual(150_000, initial["metrics"]["operating_surplus_cents"])
        self.assertEqual(150_000, initial["metrics"]["liquidity_delta_cents"])

        self.repo.set_movement_amount({
            "household_id": self.hid,
            "occurrence_key": key,
            "amount_cents": 20_000,
        })
        changed = self.repo.dashboard(self.hid, "2026-11-30", include_credit_summary=False)
        self.assertEqual(280_000, changed["metrics"]["balance_cents"])
        self.assertEqual(20_000, changed["metrics"]["expenses_cents"])
        self.assertEqual(180_000, changed["metrics"]["operating_surplus_cents"])
        self.assertEqual(180_000, changed["metrics"]["liquidity_delta_cents"])

        self.repo.set_movement_omission({
            "household_id": self.hid,
            "occurrence_key": key,
            "omitted": True,
        })
        omitted = self.repo.dashboard(self.hid, "2026-11-30", include_credit_summary=False)
        self.assertEqual(300_000, omitted["metrics"]["balance_cents"])
        self.assertEqual(0, omitted["metrics"]["expenses_cents"])
        self.assertEqual(200_000, omitted["metrics"]["operating_surplus_cents"])
        self.assertEqual(200_000, omitted["metrics"]["liquidity_delta_cents"])

        preview = self.repo.monthly_preview(self.hid, "2026-11", [self.account_id])
        movement = next(item for item in preview["movements"] if item["occurrence_key"] == key)
        self.assertTrue(movement["omitted"])
        self.assertFalse(movement["completed"])
        self.assertFalse(movement["applied_to_projection"])
        self.assertEqual(-20_000, movement["amount_cents"])
        self.assertEqual(0, preview["totals"]["expense_cents"])

        # The status and the individual override both survive a restart.
        reopened = Repository(self.db)
        persisted = reopened.dashboard(self.hid, "2026-11-30", include_credit_summary=False)
        self.assertEqual(300_000, persisted["metrics"]["balance_cents"])
        self.assertEqual(200_000, persisted["metrics"]["operating_surplus_cents"])

        reopened.set_movement_omission({
            "household_id": self.hid,
            "occurrence_key": key,
            "omitted": False,
        })
        restored = reopened.dashboard(self.hid, "2026-11-30", include_credit_summary=False)
        self.assertEqual(280_000, restored["metrics"]["balance_cents"])
        self.assertEqual(20_000, restored["metrics"]["expenses_cents"])
        self.assertEqual(180_000, restored["metrics"]["operating_surplus_cents"])
        self.assertEqual(180_000, restored["metrics"]["liquidity_delta_cents"])

    def test_completed_and_omitted_are_mutually_exclusive(self):
        fuel = self.cash_flow("expense", "Tanken", 50_000, "2026-11-10")
        key = f"cash-flow:{fuel['id']}:2026-11-10"

        self.repo.set_movement_completion({
            "household_id": self.hid,
            "occurrence_key": key,
            "completed": True,
        })
        self.repo.set_movement_omission({
            "household_id": self.hid,
            "occurrence_key": key,
            "omitted": True,
        })
        with self.repo.connect() as con:
            self.assertEqual(0, con.execute(
                "SELECT COUNT(*) FROM movement_completions WHERE household_id=? AND occurrence_key=?",
                (self.hid, key),
            ).fetchone()[0])
            self.assertEqual(1, con.execute(
                "SELECT COUNT(*) FROM movement_omissions WHERE household_id=? AND occurrence_key=?",
                (self.hid, key),
            ).fetchone()[0])

        self.repo.set_movement_completion({
            "household_id": self.hid,
            "occurrence_key": key,
            "completed": True,
        })
        with self.repo.connect() as con:
            self.assertEqual(1, con.execute(
                "SELECT COUNT(*) FROM movement_completions WHERE household_id=? AND occurrence_key=?",
                (self.hid, key),
            ).fetchone()[0])
            self.assertEqual(0, con.execute(
                "SELECT COUNT(*) FROM movement_omissions WHERE household_id=? AND occurrence_key=?",
                (self.hid, key),
            ).fetchone()[0])

    def test_omitted_transfer_removes_both_legs_and_is_cleaned_up_on_delete(self):
        detail = self.repo.create_account({
            "household_id": self.hid,
            "name": "Tagesgeld",
            "owner": "A",
            "balance_cents": 25_000,
            "anchor_date": "2026-10-31",
            "bookings_applied": True,
        })
        savings_id = next(item["id"] for item in detail["accounts"] if item["name"] == "Tagesgeld")
        transfer = self.repo.create_transfer({
            "household_id": self.hid,
            "name": "Rücklage",
            "source_account_id": self.account_id,
            "target_account_id": savings_id,
            "amount_cents": 30_000,
            "recurrence": "once",
            "due_date": "2026-11-15",
            "active": True,
        })
        key = f"transfer:{transfer['id']}:2026-11-15"
        self.repo.set_movement_omission({
            "household_id": self.hid,
            "occurrence_key": key,
            "omitted": True,
        })

        preview = self.repo.monthly_preview(self.hid, "2026-11", [self.account_id, savings_id])
        legs = [item for item in preview["movements"] if item["source_id"] == transfer["id"]]
        self.assertEqual(2, len(legs))
        self.assertTrue(all(item["omitted"] for item in legs))
        self.assertTrue(all(not item["applied_to_projection"] for item in legs))
        balances = {item["name"]: item["closing_balance_cents"] for item in preview["accounts"]}
        self.assertEqual({"Girokonto": 100_000, "Tagesgeld": 25_000}, balances)

        self.repo.delete_transfer(self.hid, transfer["id"])
        with self.repo.connect() as con:
            self.assertEqual(0, con.execute(
                "SELECT COUNT(*) FROM movement_omissions WHERE source_id=?", (transfer["id"],)
            ).fetchone()[0])

    def test_omitted_credit_installment_does_not_reduce_credit_balance(self):
        credit = self.repo.create_credit({
            "household_id": self.hid,
            "name": "Privatdarlehen",
            "credit_type": "borrowed",
            "opening_balance_cents": 90_000,
            "interest_rate": "0",
            "automatic_interest": False,
            "payment_plan": {
                "amount_cents": 30_000,
                "first_due_date": "2026-11-10",
                "occurrence_count": 3,
                "account_id": self.account_id,
                "owner": "A",
            },
        })
        flow_id = credit["payment_plan"]["flow_id"]
        key = f"cash-flow:{flow_id}:2026-11-10"
        self.repo.set_movement_omission({
            "household_id": self.hid,
            "occurrence_key": key,
            "omitted": True,
        })

        view = self.repo.list_credits(
            self.hid,
            as_of="2026-10-31",
            through="2027-02-28",
            simulate_future=True,
        )
        item = next(row for row in view["items"] if row["id"] == credit["id"])
        payments = [row for row in item["payments"] if row["source"] == "expense"]
        first = next(row for row in payments if row["date"] == "2026-11-10")
        self.assertTrue(first["omitted"])
        self.assertEqual(0, first["account_amount_cents"])
        self.assertEqual(0, first["effective_reduction_cents"])
        self.assertEqual(90_000, first["remaining_after_cents"])

        preview = self.repo.monthly_preview(
            self.hid, "2026-11", [self.account_id], [credit["id"]]
        )
        movement = next(row for row in preview["movements"] if row["occurrence_key"] == key)
        self.assertTrue(movement["omitted"])
        self.assertFalse(movement["applied_to_projection"])
        self.assertEqual(-30_000, movement["amount_cents"])
        self.assertEqual(0, preview["credit_totals"]["reduction_cents"])


if __name__ == "__main__":
    unittest.main()
