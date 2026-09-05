import tempfile
import unittest
from pathlib import Path

from app.infrastructure.repository import Repository


class IncomeArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Repository(Path(self.tmp.name) / "test.db")
        household = self.repo.create_household({"name": "Musterhaushalt", "mode": "single", "person_a": "Person A"})
        self.household_id = household["id"]
        detail = self.repo.create_account({
            "household_id": self.household_id,
            "name": "Giro",
            "owner": "A",
            "balance_cents": 0,
            "anchor_date": "2025-01-01",
        })
        self.account_id = detail["accounts"][0]["id"]

    def tearDown(self):
        self.tmp.cleanup()

    def create_income(self, name, recurrence, due_date):
        return self.repo.create_cash_flow({
            "household_id": self.household_id,
            "kind": "income",
            "name": name,
            "category": "other_income",
            "amount_cents": 10000,
            "recurrence": recurrence,
            "effective_from": "2025-01-01",
            "due_date": due_date,
            "account_id": self.account_id,
            "owner": "A",
            "active": True,
        })

    def test_past_one_time_income_is_archived_but_recurring_income_stays_active(self):
        self.create_income("Vergangene Erstattung", "once", "2025-01-15")
        self.create_income("Laufende Rente", "monthly", "2025-01-20")

        items = self.repo.list_cash_flows(self.household_id, "income", "2025-02-01")
        statuses = {item["name"]: item["lifecycle_status"] for item in items}

        self.assertEqual("ended", statuses["Vergangene Erstattung"])
        self.assertEqual("current", statuses["Laufende Rente"])

    def test_income_view_contains_active_and_archive_filter(self):
        static_root = Path(__file__).parents[1] / "app" / "static"
        html = (static_root / "index.html").read_text(encoding="utf-8")
        javascript = (static_root / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="income-filter"', html)
        self.assertIn('id="income-list-title">Aktive Einnahmen', html)
        self.assertIn("function renderIncomes()", javascript)
        self.assertIn("data-income-filter", javascript)
        self.assertIn("Archivierte Einnahmen", javascript)

    def test_settings_places_excel_export_beside_energylab(self):
        static_root = Path(__file__).parents[1] / "app" / "static"
        html = (static_root / "index.html").read_text(encoding="utf-8")
        css = (static_root / "styles.css").read_text(encoding="utf-8")

        energylab_position = html.index('class="panel energylab-panel"')
        export_position = html.index('class="panel export-panel"')
        diagnostics_position = html.index('class="panel diagnostics-panel"')
        self.assertLess(energylab_position, export_position)
        self.assertLess(export_position, diagnostics_position)
        self.assertIn(".diagnostics-panel{grid-column:1/-1}", css)
        self.assertNotIn(".diagnostics-panel,.export-panel{grid-column:1/-1}", css)
        self.assertIn(".export-panel{display:flex;flex-direction:column}", css)

    def test_recurring_income_amount_change_preserves_history(self):
        income = self.create_income("Gehalt", "monthly", "2025-01-25")
        self.repo.update_cash_flow(income["id"], {
            "household_id": self.household_id,
            "kind": "income",
            "name": "Gehalt",
            "category": "salary",
            "amount_cents": 115000,
            "recurrence": "monthly",
            "effective_from": "2025-07-01",
            "due_date": "2025-01-25",
            "account_id": self.account_id,
            "owner": "A",
            "active": True,
        })

        before = next(item for item in self.repo.list_cash_flows(self.household_id, "income", "2025-06-30") if item["id"] == income["id"])
        after = next(item for item in self.repo.list_cash_flows(self.household_id, "income", "2025-07-01") if item["id"] == income["id"])

        self.assertEqual(10000, before["amount_cents"])
        self.assertEqual(115000, after["amount_cents"])
        self.assertEqual(2, len(after["versions"]))
        self.assertEqual("2025-07-01", before["next_version"]["version_from"])

    def test_income_amount_change_dialog_is_available_for_recurring_income(self):
        static_root = Path(__file__).parents[1] / "app" / "static"
        html = (static_root / "index.html").read_text(encoding="utf-8")
        javascript = (static_root / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="income-change-dialog"', html)
        self.assertIn('name="effective_from"', html)
        self.assertIn('name="amount" type="number" min="0.01"', html)
        self.assertIn("data-income-change", javascript)
        self.assertIn("effective_from:form.effective_from.value", javascript)


if __name__ == "__main__":
    unittest.main()
