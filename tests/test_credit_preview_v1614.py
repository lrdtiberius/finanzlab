import tempfile
import unittest
from pathlib import Path

from app.infrastructure.repository import Repository


class CreditPreviewV1614Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "planner.db"
        self.repo = Repository(self.db)

        household = self.repo.create_household({
            "name": "Preview-Test",
            "mode": "single",
            "person_a": "Alex",
        })
        self.hid = household["id"]

    def tearDown(self):
        self.tmp.cleanup()

    def test_consumer_financing_is_zero_after_third_rate_in_preview(self):
        # Finanzierung: 148,65 € Gesamtbetrag in genau 3 Raten à 49,55 €.
        # Produktpreis liegt darunter, damit ein echter Zinsanteil vorhanden ist.
        credit = self.repo.create_credit({
            "household_id": self.hid,
            "name": "RAM-Test",
            "credit_type": "consumer_credit",
            "opening_balance_cents": 14865,
            "product_price_cents": 14600,
            "financing_price_cents": 14865,
            "interest_rate": "12",
            "automatic_interest": True,
            "balloon_payment_cents": 0,
        })

        self.repo.create_cash_flow({
            "household_id": self.hid,
            "kind": "expense",
            "name": "RAM-Test Rate",
            "category": "consumer_credit",
            "amount_cents": 4955,
            "credit_reduction_cents": 1,
            "credit_id": credit["id"],
            "recurrence": "monthly",
            "due_date": "2030-01-10",
            "duration_months": 3,
            "effective_from": "2030-01-01",
            "active": True,
            "owner": "A",
        })

        detail = self.repo.list_credits(
            self.hid,
            as_of="2029-12-31",
            through="2030-03-31",
            simulate_future=True,
        )["items"][0]

        payments = sorted(
            [p for p in detail["payments"] if p["source"] == "expense"],
            key=lambda p: p["date"],
        )

        self.assertEqual(3, len(payments))

        # Sicherstellen, dass wir wirklich den problematischen Fall testen:
        # Zinsen sind vorhanden und die angezeigte Tilgung ist deshalb kleiner
        # als die tatsächliche Reduktion der Finanzierungsschuld.
        self.assertGreater(
            sum(p["interest_cents"] for p in payments),
            0,
        )

        self.assertLess(
            sum(p["effective_reduction_cents"] for p in payments),
            14865,
        )

        self.assertEqual(
            14865,
            sum(p["balance_reduction_cents"] for p in payments),
        )

        # Der Tilgungsplan selbst muss nach der dritten Rate bereits 0 anzeigen.
        self.assertEqual(
            0,
            payments[-1]["remaining_after_cents"],
        )

        # Das ist der eigentliche Regressionstest:
        # Auch die Monats-/Tagesvorschau muss nach Rate 3 exakt 0 anzeigen.
        preview = self.repo.monthly_preview(
            self.hid,
            "2030-03",
            [],
            [credit["id"]],
        )

        final_due = payments[-1]["date"]

        day = next(
            d for d in preview["days"]
            if d["date"] == final_due
        )

        credit_row = next(
            c for c in day["credits"]
            if c["id"] == credit["id"]
        )

        self.assertEqual(
            0,
            credit_row["remaining_balance_cents"],
        )


if __name__ == "__main__":
    unittest.main()
