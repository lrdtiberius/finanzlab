import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.archive_support import install_repository_archive_support
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

    def test_disabled_automatic_calculation_keeps_manual_principal(self):
        credit = self.credit(automatic_interest=False)
        self.rate(credit["id"], credit_reduction_cents=4_500)
        payment = self.detail(credit["id"], "2026-01-31")["payments"][0]
        self.assertEqual(5_500, payment["interest_cents"])
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

    def test_negative_manual_payment_increases_balance_for_all_credit_types(self):
        for credit_type in ("consumer_credit", "credit", "borrowed"):
            with self.subTest(credit_type=credit_type):
                credit = self.credit(name=f"Aufstockung {credit_type}", credit_type=credit_type)
                self.repo.add_credit_payment(credit["id"], {
                    "household_id": self.hid, "payment_date": "2026-01-10", "amount_cents": -20_000
                })
                self.rate(credit["id"], category=credit_type)
                detail = next(item for item in self.repo.list_credits(
                    self.hid, as_of="2026-01-31", through="2026-01-31", simulate_future=True
                )["items"] if item["id"] == credit["id"])
                increase = next(item for item in detail["payments"] if item["source"] == "manual")
                rate = next(item for item in detail["payments"] if item["source"] == "expense")
                self.assertEqual(-20_000, increase["effective_reduction_cents"])
                self.assertEqual(120_000, increase["remaining_after_cents"])
                self.assertEqual(1_200, rate["interest_cents"])
                self.assertEqual(111_200, detail["remaining_balance_cents"])

    def test_zero_manual_payment_is_rejected(self):
        credit = self.credit()
        with self.assertRaisesRegex(ValueError, "darf nicht 0,00 € sein"):
            self.repo.add_credit_payment(credit["id"], {
                "household_id": self.hid, "payment_date": "2026-01-10", "amount_cents": 0
            })

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

    def test_expected_repayment_date_includes_special_payments(self):
        credit = self.credit(opening_balance_cents=20_000, interest_rate="0")
        self.rate(credit["id"], end_date="2026-06-15")
        self.repo.add_credit_payment(credit["id"], {
            "household_id": self.hid, "payment_date": "2026-02-10", "amount_cents": 5_000
        })
        detail = self.repo.list_credits(
            self.hid, as_of="2026-01-01", through="2026-06-30", simulate_future=True
        )["items"][0]
        self.assertEqual("2026-06-15", detail["contractual_end_date"])
        self.assertEqual("2026-02-13", detail["expected_repayment_date"])

    def test_rates_after_expected_repayment_are_skipped(self):
        credit = self.credit(opening_balance_cents=20_000, interest_rate="0")
        self.rate(credit["id"], end_date="2026-06-15")
        self.repo.add_credit_payment(credit["id"], {
            "household_id": self.hid, "payment_date": "2026-02-10", "amount_cents": 5_000
        })
        detail = self.repo.list_credits(
            self.hid, as_of="2026-01-01", through="2026-06-30", simulate_future=True
        )["items"][0]
        march = next(payment for payment in detail["payments"] if payment["date"] == "2026-03-13")
        self.assertTrue(march["skipped"])
        self.assertEqual("credit_repaid", march["skip_reason"])
        self.assertEqual(0, march["account_amount_cents"])

    def test_legacy_manual_principal_also_gets_expected_end(self):
        credit = self.credit(opening_balance_cents=25_000, interest_rate="", automatic_interest=False)
        self.rate(credit["id"], credit_reduction_cents=10_000, end_date="2026-05-15")
        detail = self.repo.list_credits(
            self.hid, as_of="2026-01-01", through="2026-05-31", simulate_future=True
        )["items"][0]
        self.assertEqual("2026-03-13", detail["expected_repayment_date"])
        self.assertEqual("2026-05-15", detail["contractual_end_date"])

    def test_twelve_monthly_payments_mean_exactly_twelve_occurrences(self):
        credit = self.credit(opening_balance_cents=120_000, interest_rate="0")
        flow = self.rate(credit["id"], amount_cents=10_000, duration_months="12")
        self.assertEqual("2026-12-15", flow["end_date"])
        self.assertEqual(12, flow["duration_months"])
        detail = self.repo.list_credits(
            self.hid, as_of="2026-01-01", through="2026-12-31", simulate_future=True
        )["items"][0]
        effective = [payment for payment in detail["payments"] if not payment["skipped"]]
        self.assertEqual(12, len(effective))
        self.assertEqual("2026-12-15", detail["expected_repayment_date"])

    def test_credit_creation_can_create_its_payment_plan_atomically(self):
        account = self.repo.create_account({
            "household_id": self.hid, "name": "Giro", "owner": "A",
            "anchor_date": "2026-01-01", "balance_cents": 0,
        })["accounts"][0]
        credit = self.credit(opening_balance_cents=120_000, interest_rate="0", payment_plan={
            "amount_cents": 10_000, "first_due_date": "2026-01-15",
            "occurrence_count": 12, "account_id": account["id"], "owner": "A",
        })
        self.assertEqual("2026-01-15", credit["payment_plan"]["due_date"])
        self.assertEqual("2026-12-15", credit["payment_plan"]["stream_end"])
        self.assertEqual(12, credit["payment_plan"]["occurrence_count"])
        linked = self.repo.list_cash_flows(self.hid, "expense", "2026-01-01")
        self.assertEqual(1, len(linked))
        self.assertEqual(credit["id"], linked[0]["credit_id"])

    def test_updated_payment_count_is_returned_after_reopen(self):
        account = self.repo.create_account({
            "household_id": self.hid, "name": "Giro", "owner": "A",
            "anchor_date": "2026-01-01", "balance_cents": 0,
        })["accounts"][0]
        credit = self.credit(opening_balance_cents=800_000, interest_rate="5", payment_plan={
            "amount_cents": 13_080, "first_due_date": "2026-09-13",
            "occurrence_count": 40, "account_id": account["id"], "owner": "A",
        })
        plan = credit["payment_plan"]
        self.repo.update_credit(credit["id"], {
            "household_id": self.hid, "name": "Darlehen", "credit_type": "credit",
            "opening_balance_cents": 800_000, "interest_rate": "5", "automatic_interest": True,
            "balloon_payment_cents": 250_000, "payment_plan": {
                "flow_id": plan["flow_id"], "amount_cents": 13_080,
                "first_due_date": "2026-09-13", "occurrence_count": "73",
                "account_id": account["id"], "owner": "A", "effective_from": "2026-09-14",
            },
        })
        reopened = self.repo.credit_detail(self.hid, credit["id"], "2026-09-13")
        self.assertEqual(73, reopened["payment_plan"]["occurrence_count"])
        self.assertEqual(73, reopened["payment_count"])
        self.assertEqual("2032-09-13", reopened["payment_plan"]["stream_end"])
        self.assertEqual(250_000, reopened["balloon_payment_cents"])
        with sqlite3.connect(self.db) as con:
            self.assertEqual(73, con.execute(
                "SELECT payment_count FROM credits WHERE id=?", (credit["id"],)
            ).fetchone()[0])

    def test_consumer_prices_keep_provider_and_derive_surcharge(self):
        credit = self.credit(name="PayPal Laptop", credit_type="consumer_credit",
            opening_balance_cents=1_199_00, provider="PayPal",
            product_price_cents=1_000_00, financing_price_cents=1_199_00)
        self.assertEqual("PayPal", credit["provider"])
        self.assertEqual(19_900, credit["installment_surcharge_cents"])

    def test_paypal_financing_uses_product_price_as_automatic_opening_balance(self):
        account = self.repo.create_account({"household_id": self.hid, "name": "Giro", "owner": "A",
            "anchor_date": "2026-10-01", "balance_cents": 0})["accounts"][0]
        credit = self.credit(name="Zelda Switch 2", credit_type="consumer_credit",
            opening_balance_cents=58_629, provider="PayPal", product_price_cents=51_999,
            financing_price_cents=58_629, installment_surcharge_cents=6_601,
            interest_rate="11.8033", automatic_interest=True, payment_plan={
                "amount_cents": 2_443, "first_due_date": "2026-10-15",
                "occurrence_count": 24, "account_id": account["id"], "owner": "A"})
        self.assertEqual(51_999, credit["opening_balance_cents"])
        self.assertEqual("11.8033", credit["interest_rate"])
        detail = self.repo.list_credits(self.hid, as_of="2028-09-30", through="2028-09-30",
            simulate_future=True)["items"][0]
        payments = [payment for payment in detail["payments"] if not payment["skipped"]]
        self.assertEqual(24, len(payments))
        self.assertEqual(0, detail["remaining_balance_cents"])

    def test_consumer_financing_rejects_non_rounding_plan_difference(self):
        account = self.repo.create_account({"household_id": self.hid, "name": "Giro", "owner": "A",
            "anchor_date": "2026-10-01", "balance_cents": 0})["accounts"][0]
        with self.assertRaisesRegex(ValueError, "passen nicht zum Finanzierungspreis"):
            self.credit(name="Falscher Plan", credit_type="consumer_credit",
                opening_balance_cents=51_999, product_price_cents=51_999,
                financing_price_cents=58_629, interest_rate="11.8033", automatic_interest=True,
                payment_plan={"amount_cents": 2_500, "first_due_date": "2026-10-15",
                    "occurrence_count": 24, "account_id": account["id"], "owner": "A"})

    def test_manual_consumer_credit_keeps_financing_price_as_opening_balance(self):
        credit = self.credit(name="Manueller PayPal-Plan", credit_type="consumer_credit",
            opening_balance_cents=58_629, product_price_cents=51_999,
            financing_price_cents=58_629, interest_rate="11.8033", automatic_interest=False)
        self.assertEqual(58_629, credit["opening_balance_cents"])
        self.assertEqual("11.8033", credit["interest_rate"])

    def test_interest_booking_is_an_expense_and_is_reported(self):
        account = self.repo.create_account({"household_id": self.hid, "name": "Giro", "owner": "A",
            "anchor_date": "2026-01-01", "balance_cents": 0})["accounts"][0]
        credit = self.credit(opening_balance_cents=20_000, interest_rate="12")
        self.rate(credit["id"], amount_cents=10_000, credit_reduction_cents=9_800,
            due_date="2026-01-15", recurrence="once")
        result = self.repo.create_interest_booking({"household_id": self.hid, "credit_id": credit["id"],
            "booking_date": "2026-01-15", "amount_cents": 200, "account_id": account["id"]})
        self.assertEqual(200, result["totals"]["booked_interest_cents"])
        expenses = self.repo.list_cash_flows(self.hid, "expense", "2026-01-15")
        self.assertTrue(any(item["category"] == "interest" and item["amount_cents"] == 200 for item in expenses))

    def test_manual_plan_derives_interest_from_payment_minus_principal(self):
        credit = self.credit(opening_balance_cents=20_000, interest_rate="", automatic_interest=False)
        self.rate(credit["id"], amount_cents=1_000, credit_reduction_cents=900,
            due_date="2026-01-15", recurrence="once")
        payment = self.detail(credit["id"], "2026-01-31")["payments"][0]
        self.assertEqual(100, payment["interest_cents"])

    def test_missing_interest_rate_is_inferred_from_bounded_payment_plan(self):
        account = self.repo.create_account({"household_id": self.hid, "name": "Giro", "owner": "A",
            "anchor_date": "2026-12-01", "balance_cents": 0})["accounts"][0]
        credit = self.credit(opening_balance_cents=100_000, interest_rate="", automatic_interest=True,
            payment_plan={"amount_cents": 9_000, "first_due_date": "2027-01-15",
                "occurrence_count": 12, "account_id": account["id"], "owner": "A"})
        self.assertIsNone(credit["interest_rate"])
        self.assertTrue(credit["interest_rate_inferred"])
        self.assertGreater(float(credit["calculated_interest_rate"]), 0)
        detail = self.repo.list_credits(self.hid, as_of="2026-12-31", through="2027-12-31",
            simulate_future=True)["items"][0]
        first = list(reversed(detail["payments"]))[0]
        self.assertTrue(first["automatic_calculation"])
        self.assertGreater(first["interest_cents"], 0)
        interest = self.repo.list_interest(self.hid, "2026-12-31")
        self.assertGreater(interest["totals"]["future_interest_cents"], 0)
        self.assertEqual(
            interest["totals"]["calculated_interest_cents"] + interest["totals"]["future_interest_cents"],
            interest["totals"]["expected_total_interest_cents"],
        )

    def test_contractual_residual_remains_after_final_regular_payment(self):
        account = self.repo.create_account({"household_id": self.hid, "name": "Autokonto", "owner": "A",
            "anchor_date": "2026-12-01", "balance_cents": 0})["accounts"][0]
        credit = self.credit(opening_balance_cents=100_000, interest_rate="0", balloon_payment_cents=40_000,
            payment_plan={"amount_cents": 5_000, "first_due_date": "2027-01-15",
                "occurrence_count": 12, "account_id": account["id"], "owner": "A"})
        detail = self.repo.list_credits(self.hid, as_of="2027-12-31", through="2027-12-31",
            simulate_future=True)["items"][0]
        self.assertEqual(40_000, detail["remaining_balance_cents"])
        self.assertEqual("2027-12-15", detail["contractual_end_date"])
        self.assertIsNone(detail["expected_repayment_date"])

    def test_update_without_flow_id_keeps_new_payment_count(self):
        account = self.repo.create_account({"household_id": self.hid, "name": "Ratenkonto", "owner": "A",
            "anchor_date": "2026-09-01", "balance_cents": 0})["accounts"][0]
        credit = self.credit(opening_balance_cents=800_000, interest_rate="5", payment_plan={
            "amount_cents": 13_080, "first_due_date": "2026-09-13", "occurrence_count": 40,
            "account_id": account["id"], "owner": "A"})
        self.repo.update_credit(credit["id"], {"household_id": self.hid, "name": "Darlehen",
            "credit_type": "credit", "opening_balance_cents": 800_000, "interest_rate": "5",
            "automatic_interest": True, "payment_plan": {"amount_cents": 13_080,
                "first_due_date": "2026-09-13", "occurrence_count": 73,
                "account_id": account["id"], "owner": "A", "effective_from": "2026-09-14"}})
        reopened = self.repo.credit_detail(self.hid, credit["id"], "2026-09-13")
        self.assertEqual(73, reopened["payment_plan"]["occurrence_count"])
        self.assertEqual(73, reopened["payment_plan"]["derived_occurrence_count"])

    def test_interest_is_available_as_regular_expense_category(self):
        account = self.repo.create_account({"household_id": self.hid, "name": "Zinskonto", "owner": "A",
            "anchor_date": "2026-01-01", "balance_cents": 0})["accounts"][0]
        flow = self.repo.create_cash_flow({"household_id": self.hid, "kind": "expense",
            "name": "Sollzinsen", "category": "interest", "amount_cents": 250,
            "recurrence": "once", "due_date": "2026-01-31", "account_id": account["id"],
            "owner": "A", "active": True, "effective_from": "2026-01-01"})
        self.assertEqual("interest", flow["category"])
        overview = self.repo.list_interest(self.hid, "2026-01-31")
        self.assertEqual(250, overview["totals"]["booked_interest_cents"])
        self.assertEqual(250, overview["totals"]["unassigned_interest_cents"])
        self.assertEqual(250, overview["totals"]["checking_account_interest_cents"])
        self.assertEqual(
            overview["totals"]["credit_interest_cents"] + 250,
            overview["totals"]["total_interest_cents"],
        )
        self.assertEqual(1, len(overview["account_interest_bookings"]))
        self.assertTrue(any(item["source"] == "expense" and item["amount_cents"] == 250
            and item["credit_name"] == "Sollzinsen" for item in overview["bookings"]))

    def test_interest_selection_filters_credit_rows_and_totals(self):
        first = self.credit(name="Ausgewählter Kredit", opening_balance_cents=20_000)
        second = self.credit(name="Nicht ausgewählter Kredit", opening_balance_cents=30_000)
        self.rate(first["id"], amount_cents=10_000, recurrence="once")
        self.rate(second["id"], amount_cents=10_000, recurrence="once")
        selected = self.repo.list_interest(self.hid, "2026-01-31", [first["id"]])
        self.assertEqual([first["id"]], [item["credit_id"] for item in selected["items"]])
        self.assertEqual(200, selected["totals"]["credit_interest_cents"])
        self.assertEqual(200, selected["totals"]["total_interest_cents"])
        account = self.repo.create_account({
            "household_id": self.hid, "name": "Giro", "owner": "A",
            "anchor_date": "2026-01-01", "balance_cents": 0,
        })["accounts"][0]
        self.repo.create_cash_flow({
            "household_id": self.hid, "kind": "expense", "name": "Girozinsen",
            "category": "interest", "amount_cents": 250, "recurrence": "once",
            "due_date": "2026-01-31", "account_id": account["id"], "owner": "A",
            "active": True, "effective_from": "2026-01-01",
        })
        none = self.repo.list_interest(self.hid, "2026-01-31", [])
        self.assertEqual([], none["items"])
        self.assertEqual(0, none["totals"]["credit_interest_cents"])
        self.assertEqual(250, none["totals"]["checking_account_interest_cents"])
        self.assertEqual(250, none["totals"]["total_interest_cents"])

    def test_backdated_one_time_interest_expense_is_visible(self):
        account = self.repo.create_account({"household_id": self.hid, "name": "Sparkasse", "owner": "A",
            "anchor_date": "2026-09-01", "balance_cents": 0})["accounts"][0]
        self.repo.create_cash_flow({"household_id": self.hid, "kind": "expense",
            "name": "zinsen", "category": "interest", "amount_cents": 891,
            "recurrence": "once", "due_date": "2026-09-01", "account_id": account["id"],
            "owner": "A", "active": True, "effective_from": "2026-09-13"})
        overview = self.repo.list_interest(self.hid, "2026-09-13")
        self.assertEqual(891, overview["totals"]["booked_interest_cents"])
        booking = next(item for item in overview["bookings"] if item["source"] == "expense")
        self.assertEqual("2026-09-01", booking["booking_date"])
        self.assertEqual("Sparkasse", booking["account_name"])


class ArchivedCreditInterestSelectionTests(unittest.TestCase):
    def setUp(self):
        class ArchivedRepository(Repository):
            pass

        install_repository_archive_support(ArchivedRepository)
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = ArchivedRepository(Path(self.tmp.name) / "planner.db")
        self.hid = self.repo.create_household(
            {"name": "Archiv-Zins-Test", "mode": "single", "person_a": "Alex"}
        )["id"]

    def tearDown(self):
        self.tmp.cleanup()

    def test_archived_credit_is_optional_and_included_when_selected(self):
        credit = self.repo.create_credit({
            "household_id": self.hid,
            "name": "Abbezahlter Kredit",
            "credit_type": "credit",
            "opening_balance_cents": 5_000,
            "interest_rate": "12",
            "automatic_interest": True,
        })
        self.repo.create_cash_flow({
            "household_id": self.hid,
            "kind": "expense",
            "name": "Letzte Kreditrate",
            "category": "credit",
            "amount_cents": 5_050,
            "credit_reduction_cents": 1,
            "credit_id": credit["id"],
            "recurrence": "once",
            "due_date": "2026-01-15",
            "effective_from": "2026-01-01",
            "active": True,
            "owner": "A",
        })

        default = self.repo.list_interest(self.hid, "2026-01-31")
        self.assertEqual([], default["items"])

        selected = self.repo.list_interest(self.hid, "2026-01-31", [credit["id"]])
        self.assertEqual([credit["id"]], [item["credit_id"] for item in selected["items"]])
        self.assertEqual(50, selected["totals"]["credit_interest_cents"])
        self.assertEqual(50, selected["totals"]["total_interest_cents"])

    def test_manually_archived_credit_keeps_past_interest_but_not_future_interest(self):
        credit = self.repo.create_credit({
            "household_id": self.hid,
            "name": "Manuell archivierter Kredit",
            "credit_type": "credit",
            "opening_balance_cents": 20_000,
            "interest_rate": "12",
            "automatic_interest": True,
        })
        self.repo.create_cash_flow({
            "household_id": self.hid,
            "kind": "expense",
            "name": "Kreditrate",
            "category": "credit",
            "amount_cents": 10_000,
            "credit_reduction_cents": 1,
            "credit_id": credit["id"],
            "recurrence": "monthly",
            "due_date": "2026-01-15",
            "effective_from": "2026-01-01",
            "active": True,
            "owner": "A",
        })
        self.repo.set_credit_archived(credit["id"], {
            "household_id": self.hid,
            "archived": True,
        })

        selected = self.repo.list_interest(self.hid, "2026-09-14", [credit["id"]])
        self.assertEqual([credit["id"]], [item["credit_id"] for item in selected["items"]])
        self.assertEqual(305, selected["totals"]["credit_interest_cents"])
        self.assertEqual(0, selected["totals"]["planned_credit_interest_cents"])


if __name__ == "__main__":
    unittest.main()
