import tempfile
import unittest
from pathlib import Path

from app.infrastructure.repository import Repository


class EnergyLabIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Repository(Path(self.tmp.name) / "test.db")
        self.household = self.repo.create_household({"name": "Musterhaushalt", "mode": "single", "person_a": "Person A"})
        detail = self.repo.create_account({"household_id": self.household["id"], "name": "Giro", "owner": "A", "balance_cents": 0, "anchor_date": "2025-01-01"})
        self.account = detail["accounts"][0]
        self.repo.save_energylab_integration({"household_id": self.household["id"], "base_url": "http://energylab:8090", "account_id": self.account["id"], "enabled": True})

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def payload():
        return {"source": {"app": "EnergieLab", "version": "0.6.3"}, "segments": [
            {"id": "electricity", "contracts": [{"id": 7, "provider": "Octopus", "validFrom": "2025-01-15", "validTo": "2025-12-31", "baseFeeMonthly": 20, "unitPrice": 0.30, "advanceMonthly": 100, "advanceChanges": [{"validFrom": "2025-07-01", "advanceMonthly": 150}]}]},
            {"id": "gas", "contracts": [{"id": 8, "provider": "Musterwerke", "validFrom": "2025-02-01", "validTo": "2026-01-31", "baseFeeMonthly": 30, "advanceMonthly": 80, "advanceChanges": []}]},
            {"id": "water", "contracts": []},
            {"id": "pv", "contracts": [{"id": 99, "validFrom": "2025-01-01", "advanceMonthly": 999}]},
        ]}

    def test_only_advances_become_deduplicated_energy_expenses(self):
        first = self.repo.sync_energylab_contracts(self.household["id"], self.payload())
        second = self.repo.sync_energylab_contracts(self.household["id"], self.payload())
        self.assertEqual(2, first["created"])
        self.assertEqual(0, second["created"])
        expenses = self.repo.list_cash_flows(self.household["id"], "expense", "2025-03-01")
        self.assertEqual(2, len(expenses))
        self.assertEqual({8000, 10000}, {item["amount_cents"] for item in expenses})
        self.assertTrue(all(item["managed_by"] == "energylab" for item in expenses))

    def test_change_and_contract_history_are_preserved(self):
        self.repo.sync_energylab_contracts(self.household["id"], self.payload())
        before = next(item for item in self.repo.list_cash_flows(self.household["id"], "expense", "2025-06-30") if "Octopus" in item["name"])
        after = next(item for item in self.repo.list_cash_flows(self.household["id"], "expense", "2025-07-01") if "Octopus" in item["name"])
        ended = next(item for item in self.repo.list_cash_flows(self.household["id"], "expense", "2026-01-01") if "Octopus" in item["name"])
        self.assertEqual(10000, before["amount_cents"])
        self.assertEqual(15000, after["amount_cents"])
        self.assertEqual("2025-01-15", before["versions"][0]["stream_start"])
        self.assertEqual("2025-12-31", after["stream_end"])
        self.assertEqual("ended", ended["lifecycle_status"])

    def test_forecast_uses_the_advance_valid_in_each_month(self):
        self.repo.sync_energylab_contracts(self.household["id"], self.payload())
        june = self.repo.monthly_preview(self.household["id"], "2025-06", [self.account["id"]], [])
        july = self.repo.monthly_preview(self.household["id"], "2025-07", [self.account["id"]], [])
        self.assertEqual(18000, june["totals"]["expense_cents"])
        self.assertEqual(23000, july["totals"]["expense_cents"])

    def test_managed_expense_cannot_be_changed_in_finanzlab(self):
        self.repo.sync_energylab_contracts(self.household["id"], self.payload())
        item = next(item for item in self.repo.list_cash_flows(self.household["id"], "expense", "2025-03-01") if "Octopus" in item["name"])
        with self.assertRaisesRegex(ValueError, "EnergyLab"):
            self.repo.update_cash_flow(item["id"], {"household_id": self.household["id"], "kind": "expense"})
        with self.assertRaisesRegex(ValueError, "EnergyLab"):
            self.repo.delete_cash_flow(self.household["id"], item["id"])

    def test_individual_account_choice_survives_later_syncs(self):
        second = self.repo.create_account({"household_id": self.household["id"], "name": "Haushaltskonto", "owner": "A", "balance_cents": 0, "anchor_date": "2025-01-01"})
        second_account = next(account for account in second["accounts"] if account["name"] == "Haushaltskonto")
        self.repo.sync_energylab_contracts(self.household["id"], self.payload())
        item = next(item for item in self.repo.list_cash_flows(self.household["id"], "expense", "2025-03-01") if "Octopus" in item["name"])
        flow_id = item["id"]
        self.repo.update_energylab_cash_flow_account(item["id"], {"household_id": self.household["id"], "account_id": second_account["id"], "payment_day": 20})
        self.repo.sync_energylab_contracts(self.household["id"], self.payload())
        refreshed = next(item for item in self.repo.list_cash_flows(self.household["id"], "expense", "2025-03-01") if item["id"] == flow_id)
        self.assertEqual(second_account["id"], refreshed["account_id"])
        self.assertEqual(20, refreshed["payment_day"])
        self.assertEqual("2025-01-20", refreshed["versions"][0]["due_date"])
        self.assertEqual("2025-07-20", refreshed["versions"][1]["due_date"])
        self.assertTrue(all(version["account_id"] == second_account["id"] for version in refreshed["versions"]))

    def test_payment_day_uses_last_day_of_short_months(self):
        self.repo.sync_energylab_contracts(self.household["id"], self.payload())
        item = next(item for item in self.repo.list_cash_flows(self.household["id"], "expense", "2025-03-01") if "Musterwerke" in item["name"])
        self.repo.update_energylab_cash_flow_account(item["id"], {"household_id": self.household["id"], "account_id": self.account["id"], "payment_day": 31})
        february = self.repo.monthly_preview(self.household["id"], "2025-02", [self.account["id"]], [])
        gas = next(movement for movement in february["movements"] if "Musterwerke" in movement["label"])
        self.assertEqual("2025-02-28", gas["date"])

    def test_payment_details_from_energylab_select_matching_account(self):
        second = self.repo.create_account({"household_id": self.household["id"], "name": "Energiekonto", "owner": "A", "balance_cents": 0, "anchor_date": "2025-01-01"})
        second_account = next(account for account in second["accounts"] if account["name"] == "Energiekonto")
        payload = self.payload()
        payload["segments"][0]["contracts"][0].update({"paymentDay": 25, "paymentAccountName": "energiekonto"})
        result = self.repo.sync_energylab_contracts(self.household["id"], payload)
        item = next(item for item in self.repo.list_cash_flows(self.household["id"], "expense", "2025-03-01") if "Octopus" in item["name"])
        self.assertEqual([], result["unmatched_accounts"])
        self.assertEqual(second_account["id"], item["account_id"])
        self.assertEqual(25, item["payment_day"])
        self.assertEqual("2025-01-25", item["versions"][0]["due_date"])


if __name__ == "__main__":
    unittest.main()
