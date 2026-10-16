"""Isolated, synthetic regressions for the 2.4.2 forecast cache."""
import tempfile
import unittest
from pathlib import Path

from app.infrastructure.repository import Repository
from app.archive_support import install_repository_archive_support


class TestRepository(Repository):
    """The release's archive additions installed on a disposable subclass."""


install_repository_archive_support(TestRepository)


class ForecastCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="finanzlab242-test-")
        self.addCleanup(self.tmp.cleanup)
        self.repo = TestRepository(Path(self.tmp.name) / "planner.db")
        household = self.repo.create_household({
            "name": "Testhaushalt", "mode": "single", "person_a": "Demo",
            "account": {"name": "Demokonto", "owner": "A",
                        "balance_cents": 100000, "anchor_date": "2026-10-16",
                        "bookings_applied": True, "overdraft_limit_cents": 0},
        })
        self.hid = household["id"]
        self.account_id = household["accounts"][0]["id"]

    def preview(self):
        return self.repo.monthly_preview(self.hid, "2026-10", [self.account_id], [])

    def test_month_preview_cached_and_immutable_to_callers(self):
        first = self.preview()
        self.assertEqual(1, len(self.repo._forecast_cache_months))
        second = self.preview()
        self.assertEqual(first, second)
        first["totals"]["closing_balance_cents"] = -987654321
        self.assertNotEqual(first, self.preview())

    def test_successful_write_invalidates_preview(self):
        before = self.preview()
        self.repo.create_cash_flow({
            "household_id": self.hid, "kind": "expense", "name": "Testausgabe",
            "category": "food", "amount_cents": 175, "recurrence": "once",
            "due_date": "2026-10-20", "account_id": self.account_id,
            "owner": "A", "active": True, "effective_from": "2026-10-16",
        })
        after = self.preview()
        self.assertEqual(before["totals"]["closing_balance_cents"] - 175,
                         after["totals"]["closing_balance_cents"])

    def test_interest_backend_remains_available(self):
        result = self.repo.list_interest(self.hid, "2026-10-16")
        self.assertIn("totals", result)
        self.assertIn("items", result)


if __name__ == "__main__":
    unittest.main()
