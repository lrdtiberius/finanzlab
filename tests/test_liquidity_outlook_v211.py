import tempfile
import unittest
from pathlib import Path

from app.infrastructure.repository import Repository


class LiquidityOutlookV211Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Repository(Path(self.tmp.name) / "planner.db")
        household = self.repo.create_household({
            "name": "Vorschau-Test",
            "mode": "single",
            "person_a": "Alex",
        })
        self.hid = household["id"]

        detail = self.repo.create_account({
            "household_id": self.hid,
            "name": "ING Giro",
            "owner": "A",
            "balance_cents": 250_000,
            "anchor_date": "2026-10-02",
            "bookings_applied": False,
            "overdraft_limit_cents": 0,
            "kind": "checking",
            "is_default": True,
        })
        self.ing_id = next(
            account["id"] for account in detail["accounts"]
            if account["name"] == "ING Giro"
        )

        detail = self.repo.create_account({
            "household_id": self.hid,
            "name": "Sparkasse",
            "owner": "A",
            "balance_cents": 125_000,
            "anchor_date": "2026-10-02",
            "bookings_applied": False,
            "overdraft_limit_cents": 0,
            "kind": "checking",
        })
        self.sparkasse_id = next(
            account["id"] for account in detail["accounts"]
            if account["name"] == "Sparkasse"
        )

        detail = self.repo.create_account({
            "household_id": self.hid,
            "name": "Rahmenkredit",
            "owner": "A",
            "balance_cents": -50_000,
            "anchor_date": "2026-10-02",
            "bookings_applied": False,
            "overdraft_limit_cents": 1_000_000,
            "kind": "credit_line",
            "linked_account_id": self.ing_id,
        })
        self.credit_line_id = next(
            account["id"] for account in detail["accounts"]
            if account["name"] == "Rahmenkredit"
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_selected_accounts_are_forecast_separately(self):
        outlook = self.repo.liquidity_outlook(
            self.hid,
            "2026-10",
            6,
            [self.ing_id, self.sparkasse_id],
        )

        self.assertEqual(6, outlook["months"])
        self.assertEqual(
            [self.ing_id, self.sparkasse_id],
            [account["id"] for account in outlook["accounts"]],
        )
        self.assertEqual(6, len(outlook["items"]))
        for month in outlook["items"]:
            self.assertEqual(
                [self.ing_id, self.sparkasse_id],
                [account["account_id"] for account in month["accounts"]],
            )

    def test_one_account_can_be_selected(self):
        outlook = self.repo.liquidity_outlook(
            self.hid,
            "2026-10",
            6,
            [self.sparkasse_id],
        )

        self.assertEqual(
            [self.sparkasse_id],
            [account["id"] for account in outlook["accounts"]],
        )
        self.assertTrue(all(
            [self.sparkasse_id] == [account["account_id"] for account in month["accounts"]]
            for month in outlook["items"]
        ))

    def test_credit_line_cannot_be_selected(self):
        with self.assertRaisesRegex(ValueError, "Rahmenkredit"):
            self.repo.liquidity_outlook(
                self.hid,
                "2026-10",
                6,
                [self.credit_line_id],
            )


class LiquidityOutlookV211StaticUiTests(unittest.TestCase):
    def test_browser_selection_is_household_scoped(self):
        app_js = Path("app/static/app.js").read_text(encoding="utf-8")
        index_html = Path("app/static/index.html").read_text(encoding="utf-8")

        self.assertIn("finanzlab-outlook-accounts-v1:", app_js)
        self.assertIn("state.currentId", app_js)
        self.assertIn("window.localStorage.setItem", app_js)
        self.assertIn('id="dashboard-outlook-selectors"', index_html)


if __name__ == "__main__":
    unittest.main()
