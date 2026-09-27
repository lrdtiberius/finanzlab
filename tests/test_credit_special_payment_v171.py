import tempfile
import unittest
from pathlib import Path

from app.infrastructure.repository import Repository


class CreditSpecialPaymentV171Tests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "planner.db"
        self.repo = Repository(self.db)

        household = self.repo.create_household({
            "name": "Sondertilgung-Test",
            "mode": "single",
            "person_a": "Alex",
        })
        self.hid = household["id"]

    def tearDown(self):
        self.tmp.cleanup()

    def test_special_payment_can_eliminate_future_financing_costs(self):
        # Entspricht dem CHECK24-Fall:
        #
        # Finanzierungsrest: 150,51 €
        # Produktpreis-Restbasis: 144,57 €
        # manuelle Korrektur: 0,31 €
        # Ablösezahlung: 145,73 €
        #
        # Nach der Korrektur reicht die Ablöse aus, um das eigentliche
        # Kapital vollständig zu tilgen. Noch nicht entstandene künftige
        # Finanzierungskosten dürfen danach keine weitere Rate erzeugen.

        credit = self.repo.create_credit({
            "household_id": self.hid,
            "name": "CHECK24-Test",
            "credit_type": "consumer_credit",
            "opening_balance_cents": 15051,
            "product_price_cents": 14457,
            "financing_price_cents": 15051,
            "interest_rate": "12.2",
            "automatic_interest": True,
            "balloon_payment_cents": 0,
        })

        # Außerplanmäßige Ablöse
        self.repo.create_cash_flow({
            "household_id": self.hid,
            "kind": "expense",
            "name": "Ablöse CHECK24-Test",
            "category": "consumer_credit",
            "amount_cents": 14573,
            "credit_reduction_cents": 1,
            "credit_id": credit["id"],
            "recurrence": "once",
            "due_date": "2030-09-27",
            "active": True,
            "owner": "A",
        })

        # Eigentlich noch kommende monatliche Raten
        self.repo.create_cash_flow({
            "household_id": self.hid,
            "kind": "expense",
            "name": "CHECK24-Test",
            "category": "consumer_credit",
            "amount_cents": 2150,
            "credit_reduction_cents": 1,
            "credit_id": credit["id"],
            "recurrence": "monthly",
            "due_date": "2030-10-04",
            "duration_months": 3,
            "effective_from": "2030-10-01",
            "active": True,
            "owner": "A",
        })

        # Manuelle Saldenkorrektur am Tag der Ablöse.
        self.repo.add_credit_payment(credit["id"], {
            "household_id": self.hid,
            "payment_date": "2030-09-27",
            "amount_cents": 31,
        })

        result = self.repo.list_credits(
            self.hid,
            as_of="2030-09-26",
            through="2030-12-31",
            simulate_future=True,
        )

        item = next(
            c for c in result["items"]
            if c["id"] == credit["id"]
        )

        payments = item["payments"]

        manual = next(
            p for p in payments
            if p["source"] == "manual"
            and p["date"] == "2030-09-27"
        )

        payoff = next(
            p for p in payments
            if p["source"] == "expense"
            and p["date"] == "2030-09-27"
        )

        october = next(
            p for p in payments
            if p["source"] == "expense"
            and p["date"] == "2030-10-04"
        )

        # Erst die 31-Cent-Korrektur.
        self.assertEqual(31, manual["effective_reduction_cents"])
        self.assertEqual(15020, manual["remaining_after_cents"])

        # Dann Ablöse: echter Kontobetrag 145,73 €, Kredit danach 0.
        self.assertEqual(14573, payoff["account_amount_cents"])
        self.assertEqual(15020, payoff["balance_reduction_cents"])
        self.assertEqual(0, payoff["remaining_after_cents"])
        self.assertFalse(payoff["skipped"])

        # Kommende Rate darf weder Konto noch Kredit belasten.
        self.assertTrue(october["skipped"])
        self.assertEqual("credit_repaid", october["skip_reason"])
        self.assertEqual(0, october["account_amount_cents"])
        self.assertEqual(0, october["effective_reduction_cents"])
        self.assertEqual(0, october["remaining_after_cents"])

        self.assertEqual(
            "2030-09-27",
            item["expected_repayment_date"]
        )

        # Auch die Monatsvorschau muss im Folgemonat bei 0 bleiben.
        preview = self.repo.monthly_preview(
            self.hid,
            "2030-10",
            [],
            [credit["id"]],
        )

        day = next(
            d for d in preview["days"]
            if d["date"] == "2030-10-04"
        )

        preview_credit = next(
            c for c in day["credits"]
            if c["id"] == credit["id"]
        )

        self.assertEqual(
            0,
            preview_credit["remaining_balance_cents"]
        )
        self.assertEqual(
            0,
            preview_credit["reduction_cents"]
        )


if __name__ == "__main__":
    unittest.main()
