"""Synthetic regressions: shortening a partially repaid credit's future schedule.

No financial data from an actual user is loaded or recorded.
"""
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from app.infrastructure.repository import Repository
from app.archive_support import install_repository_archive_support


class TestRepository(Repository):
    pass


install_repository_archive_support(TestRepository)


class FixedDate(date):
    @classmethod
    def today(cls):
        return cls(2026, 10, 16)


class ShortenedCreditPlansTests(TestCase):
    def setUp(self):
        self.clock = patch("app.infrastructure.repository.date", FixedDate)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.tmp = TemporaryDirectory(prefix="fl-243-synthetic-")
        self.addCleanup(self.tmp.cleanup)
        self.repo = TestRepository(Path(self.tmp.name) / "demo.db")
        self.household = self.repo.create_household({
            "name": "Test", "mode": "single", "person_a": "Testperson",
            "account": {"name": "Testkonto", "owner": "A", "balance_cents": 500000,
                        "anchor_date": "2026-10-16", "bookings_applied": True},
        })
        self.hid = self.household["id"]
        self.account_id = self.household["accounts"][0]["id"]

    def create_and_shorten(self, kind, apr="0", balloon=0):
        payload = {
            "household_id": self.hid, "name": f"Demo-{kind}",
            "credit_type": kind, "opening_balance_cents": 270000,
            "interest_rate": apr, "automatic_interest": True,
            "balloon_payment_cents": balloon,
            "payment_plan": {"amount_cents": 33750,
                             "first_due_date": "2026-10-30",
                             "occurrence_count": 8,
                             "account_id": self.account_id, "owner": "A"},
        }
        if kind == "consumer_credit":
            payload.update({"product_price_cents": 270000,
                            "financing_price_cents": 270000})
        if kind == "mortgage":
            payload.update({"original_principal_cents": 270000,
                            "balance_as_of": "2026-10-16",
                            "repayment_rate": "2", "special_repayment_percent": "0"})
        created = self.repo.create_credit(payload)
        self.repo.add_credit_payment(created["id"], {
            "household_id": self.hid,
            "payment_date": "2026-10-05",
            "amount_cents": 138100,
        })
        current = self.repo.credit_detail(self.hid, created["id"])
        self.assertEqual(131900, current["remaining_balance_cents"])
        plan = dict(payload["payment_plan"])
        plan.update({"occurrence_count": 4,
                     "flow_id": current["payment_plan"]["flow_id"],
                     "effective_from": "2026-10-16"})
        payload["payment_plan"] = plan
        updated = self.repo.update_credit(created["id"], payload)
        return updated

    def test_four_types_use_remaining_principal_and_no_phantom_debit(self):
        for kind in ("borrowed", "credit", "consumer_credit", "mortgage"):
            with self.subTest(kind=kind):
                result = self.create_and_shorten(kind)
                expenses = sorted((row for row in result["payments"]
                                  if row["source"] == "expense"),
                                  key=lambda row: row["date"])
                self.assertEqual(4, len(expenses))
                self.assertEqual([33750, 33750, 33750, 30650],
                                 [row["account_amount_cents"] for row in expenses])
                self.assertEqual(0, expenses[-1]["remaining_after_cents"])
                self.assertEqual(4, result["payment_plan"]["occurrence_count"])
                self.assertFalse(any(row["account_amount_cents"] < 0 for row in expenses))

    def test_interest_bearing_standard_credit_still_amortizes(self):
        for kind in ("borrowed", "credit", "mortgage"):
            with self.subTest(kind=kind):
                result = self.create_and_shorten(kind, apr="6")
                expenses = sorted((row for row in result["payments"]
                                  if row["source"] == "expense"),
                                  key=lambda row: row["date"])
                self.assertEqual(4, len(expenses))
                self.assertGreater(expenses[0]["interest_cents"], 0)
                self.assertEqual(0, expenses[-1]["remaining_after_cents"])
                self.assertGreater(expenses[-1]["account_amount_cents"], 30650)
                self.assertTrue(all(x["account_amount_cents"] >= 0 for x in expenses))

    def test_future_installments_remain_as_skipped_not_real_charges(self):
        result = self.create_and_shorten("borrowed")
        credit_id = result["id"]
        current = self.repo.credit_detail(self.hid, credit_id)
        payload = {"household_id": self.hid, "name": current["name"],
                   "credit_type": "borrowed", "opening_balance_cents": 270000,
                   "interest_rate": "0", "automatic_interest": True,
                   "balloon_payment_cents": 0,
                   "payment_plan": {"amount_cents": 33750,
                                    "first_due_date": "2026-10-30",
                                    "occurrence_count": 8,
                                    "account_id": self.account_id, "owner": "A",
                                    "flow_id": current["payment_plan"]["flow_id"],
                                    "effective_from": "2026-10-16"}}
        longer = self.repo.update_credit(credit_id, payload)
        expenses = [p for p in longer["payments"] if p["source"] == "expense"]
        self.assertEqual(8, len(expenses))
        self.assertEqual(4, sum(not p["skipped"] for p in expenses))
        self.assertTrue(all(p["account_amount_cents"] == 0 for p in expenses if p["skipped"]))

    def test_plan_change_does_not_multiply_monthly_series(self):
        result = self.create_and_shorten("borrowed")
        with self.repo.connect() as con:
            flows = con.execute("""SELECT COUNT(DISTINCT f.id) FROM cash_flows f
                JOIN cash_flow_versions v ON v.cash_flow_id=f.id
                WHERE v.credit_id=? AND v.recurrence='monthly'""", (result["id"],)).fetchone()[0]
            self.assertEqual(1, flows)

    def test_balloon_is_preserved_for_normal_credit(self):
        result = self.create_and_shorten("credit", balloon=20000)
        expenses = sorted((row for row in result["payments"]
                          if row["source"] == "expense"),
                          key=lambda row: row["date"])
        self.assertEqual(20000, expenses[-1]["remaining_after_cents"])
        self.assertEqual([33750, 33750, 33750, 10650],
                         [row["account_amount_cents"] for row in expenses])
