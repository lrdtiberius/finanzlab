import tempfile
import unittest
from pathlib import Path

from app.infrastructure.repository import Repository


class DashboardTodayBalancesV264Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Repository(Path(self.tmp.name) / "planner.db")
        household = self.repo.create_household({
            "name": "Tagesstand-Test",
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

    def flow(self, kind, name, amount_cents):
        return self.repo.create_cash_flow({
            "household_id": self.hid,
            "kind": kind,
            "name": name,
            "category": "salary" if kind == "income" else "mobility",
            "amount_cents": amount_cents,
            "recurrence": "once",
            "due_date": "2026-11-04",
            "effective_from": "2026-11-01",
            "account_id": self.account_id,
            "owner": "A",
            "active": True,
        })

    def today_balance(self):
        result = self.repo.simulation_dashboard(
            self.hid,
            "2026-11-04",
            [self.account_id],
        )
        self.assertEqual("2026-11-04", result["as_of"])
        self.assertEqual([self.account_id], [item["id"] for item in result["accounts"]])
        return result["accounts"][0]["projected_balance_cents"]

    def test_today_balance_uses_amount_override_and_omission(self):
        self.flow("income", "Gehalt", 50_000)
        fuel = self.flow("expense", "Tanken", 20_000)
        key = f"cash-flow:{fuel['id']}:2026-11-04"

        self.assertEqual(130_000, self.today_balance())

        self.repo.set_movement_amount({
            "household_id": self.hid,
            "occurrence_key": key,
            "amount_cents": 5_000,
        })
        self.assertEqual(145_000, self.today_balance())

        self.repo.set_movement_omission({
            "household_id": self.hid,
            "occurrence_key": key,
            "omitted": True,
        })
        self.assertEqual(150_000, self.today_balance())


if __name__ == "__main__":
    unittest.main()
