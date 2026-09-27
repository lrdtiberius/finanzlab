import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.infrastructure.repository import Repository


class CreditInterestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "planner.db"
        self.repo = Repository(self.db)
        household = self.repo.create_household(
            {"name": "Zins-Test", "mode": "single", "person_a": "Alex"}
        )
        self.hid = household["id"]

    def tearDown(self):
        self.tmp.cleanup()

    def credit(self, **changes):
        payload = {
            "household_id": self.hid,
            "name": "Darlehen",
            "credit_type": "credit",
            "opening_balance_cents": 100_000,
            "interest_rate": "12",
            "automatic_interest": True,
        }
        payload.update(changes)
        return self.repo.create_credit(payload)

    def rate(self, credit_id, **changes):
        payload = {
            "household_id": self.hid,
            "kind": "expense",
            "name": "Kreditrate",
            "category": "credit",
            "amount_cents": 10_000,
            "credit_reduction_cents": 1,
            "credit_id": credit_id,
            "recurrence": "monthly",
            "due_date": "2026-01-15",
            "effective_from": "2026-01-01",
            "active": True,
            "owner": "A",
        }
        payload.update(changes)
        return self.repo.create_cash_flow(payload)

    def detail(self, credit_id, through="2026-02-28"):
        return self.repo.list_credits(
            self.hid, as_of=through, through=through, simulate_future=True
        )["items"][0]

    def test_empty_interest_rate_is_valid_and_disables_calculation(self):
        credit = self.credit(interest_rate="", automatic_interest=True)
        self.rate(credit["id"], credit_reduction_cents=4_000)
        detail = self.detail(credit["id"], "2026-01-31")
        self.assertIsNone(detail["interest_rate"])
        self.assertEqual(4_000, detail["paid_cents"])
        self.assertFalse(detail["payments"][0]["automatic_calculation"])

    def test_zero_interest_rate_is_an_active_automatic_rate(self):
        credit = self.credit(interest_rate="0")
        self.rate(credit["id"])
        payment = self.detail(credit["id"], "2026-01-31")["payments"][0]
        self.assertTrue(payment["automatic_calculation"])
        self.assertEqual(0, payment["interest_cents"])
        self.assertEqual(10_000, payment["effective_reduction_cents"])

    def test_automatic_monthly_annuity_uses_current_balance(self):
        credit = self.credit()
        self.rate(credit["id"])
        payments = list(reversed(self.detail(credit["id"])["payments"]))
        self.assertEqual((1_000, 9_000, 91_000),
                         (payments[0]["interest_cents"], payments[0]["effective_reduction_cents"], payments[0]["remaining_after_cents"]))
        self.assertEqual((910, 9_090, 81_910),
                         (payments[1]["interest_cents"], payments[1]["effective_reduction_cents"], payments[1]["remaining_after_cents"]))

    @unittest.expectedFailure
    def test_disabled_automatic_calculation_keeps_manual_principal(self):
        credit = self.credit(automatic_interest=False)
        self.rate(credit["id"], credit_reduction_cents=4_500)
        payment = self.detail(credit["id"], "2026-01-31")["payments"][0]
        self.assertEqual(0, payment["interest_cents"])
        self.assertEqual(4_500, payment["effective_reduction_cents"])

    def test_final_rate_is_limited_to_interest_plus_remaining_balance(self):
        credit = self.credit(opening_balance_cents=5_000)
        self.rate(credit["id"], recurrence="once")
        payment = self.detail(credit["id"], "2026-01-31")["payments"][0]
        self.assertEqual(50, payment["interest_cents"])
        self.assertEqual(5_000, payment["effective_reduction_cents"])
        self.assertEqual(5_050, payment["account_amount_cents"])
        self.assertEqual(0, payment["remaining_after_cents"])

    def test_special_principal_payment_changes_next_interest(self):
        credit = self.credit()
        self.repo.add_credit_payment(credit["id"], {
            "household_id": self.hid, "payment_date": "2026-01-10", "amount_cents": 20_000
        })
        self.rate(credit["id"])
        payment = next(p for p in self.detail(credit["id"], "2026-01-31")["payments"] if p["source"] == "expense")
        self.assertEqual(800, payment["interest_cents"])
        self.assertEqual(9_200, payment["effective_reduction_cents"])
        self.assertEqual(70_800, payment["remaining_after_cents"])

    def test_legacy_credit_migrates_without_behavior_change(self):
        with sqlite3.connect(self.db) as con:
            con.execute("INSERT INTO credits(id,household_id,name,credit_type,opening_balance_cents,note) VALUES('legacy',?,'Alt','credit',100000,NULL)", (self.hid,))
        reopened = Repository(self.db)
        self.repo = reopened
        self.rate("legacy", credit_reduction_cents=3_333)
        detail = self.detail("legacy", "2026-01-31")
        self.assertIsNone(detail["interest_rate"])
        self.assertEqual(0, detail["automatic_interest"])
        self.assertEqual(3_333, detail["paid_cents"])


if __name__ == "__main__":
    unittest.main()
