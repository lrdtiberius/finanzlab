"""Regression cases for v2.4.4, using synthetic SQLite fixtures only."""
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


class BorrowedOverridesAndInterestOrderTests(TestCase):
    def setUp(self):
        clock = patch('app.infrastructure.repository.date', FixedDate)
        clock.start()
        self.addCleanup(clock.stop)
        tmp = TemporaryDirectory(prefix='finanzlab-244-synthetic-')
        self.addCleanup(tmp.cleanup)
        self.repo = TestRepository(Path(tmp.name) / 'fixture.db')
        home = self.repo.create_household({
            'name': 'Sample household', 'mode': 'single', 'person_a': 'Example',
            'account': {'name': 'Example account', 'owner': 'A', 'balance_cents': 500000,
                        'anchor_date': '2026-10-16', 'bookings_applied': True},
        })
        self.hid = home['id']
        self.account_id = home['accounts'][0]['id']

    def credit(self, kind='borrowed', name='Sample borrowed credit', opening=270000, count=4):
        payload = {
            'household_id': self.hid, 'name': name,
            'credit_type': kind, 'opening_balance_cents': opening,
            'interest_rate': '0', 'automatic_interest': False,
            'payment_plan': {'amount_cents': 33750, 'first_due_date': '2026-10-30',
                             'occurrence_count': count, 'account_id': self.account_id,
                             'owner': 'A'},
        }
        if kind == 'mortgage':
            payload.update({'original_principal_cents': opening,
                            'balance_as_of': '2026-10-16',
                            'repayment_rate': '2', 'special_repayment_percent': '0'})
        return self.repo.create_credit(payload)

    def manual(self, credit, cents, when):
        self.repo.add_credit_payment(credit['id'], {
            'household_id': self.hid, 'payment_date': when,
            'amount_cents': cents,
        })

    def override(self, credit, cents=None, when='2026-10-30'):
        self.repo.set_movement_amount({
            'household_id': self.hid,
            'occurrence_key': f"cash-flow:{credit['payment_plan']['flow_id']}:{when}",
            'amount_cents': cents,
        })

    def pay_events(self, credit):
        record = self.repo.credit_detail(self.hid, credit['id'], '2026-10-16')
        monthly = sorted((p for p in record['payments'] if p['source'] == 'expense'), key=lambda p:p['date'])
        return record, monthly

    def test_override_changes_borrowed_ledger_and_final_payment(self):
        loan = self.credit()
        self.manual(loan, 135000, '2026-09-16')
        self.manual(loan, 3100, '2026-10-05')
        self.override(loan, 30650)
        record, monthly = self.pay_events(loan)
        self.assertEqual(131900, record['remaining_balance_cents'])
        self.assertEqual([30650, 33750, 33750, 33750], [p['account_amount_cents'] for p in monthly])
        self.assertEqual([30650, 33750, 33750, 33750], [p['effective_reduction_cents'] for p in monthly])
        self.assertEqual(33750, monthly[0]['planned_amount_cents'])
        self.assertTrue(monthly[0]['amount_overridden'])
        self.assertFalse(any(p['amount_overridden'] for p in monthly[1:]))
        self.assertEqual(0, monthly[-1]['remaining_after_cents'])
        self.assertEqual(138100, sum(p['effective_reduction_cents'] for p in record['payments'] if p['source']=='manual'))
        # Both the credit ledger and cash account must use exactly 306.50 EUR.
        october = self.repo.monthly_preview(self.hid, '2026-10', [self.account_id], [loan['id']])
        changed = [m for m in october['movements'] if m.get('occurrence_key') ==
                   f"cash-flow:{loan['payment_plan']['flow_id']}:2026-10-30"]
        self.assertEqual(1, len(changed))
        self.assertEqual(-30650, changed[0]['amount_cents'])
        self.assertEqual(30650, changed[0]['credit_reduction_cents'])
        self.assertEqual(33750, changed[0]['planned_amount_cents'])

    def test_clearing_override_restores_old_contractual_schedule(self):
        loan = self.credit()
        self.manual(loan, 138100, '2026-10-05')
        self.override(loan, 30650)
        self.override(loan, None)
        _, payments = self.pay_events(loan)
        self.assertEqual([33750,33750,33750,30650], [p['account_amount_cents'] for p in payments])
        self.assertFalse(any(p['amount_overridden'] for p in payments))

    def test_overridden_borrowed_payment_is_never_charged_above_outstanding(self):
        loan = self.credit(opening=10000)
        self.override(loan, 33750)
        _, payments = self.pay_events(loan)
        self.assertEqual(10000, payments[0]['account_amount_cents'])
        oct_preview=self.repo.monthly_preview(self.hid, '2026-10', [self.account_id], [loan['id']])
        october_movements=[m for m in oct_preview['movements'] if m.get('credit_id')==loan['id']]
        self.assertEqual([-10000], [m['amount_cents'] for m in october_movements if m.get('applied_to_projection',True)])

    def test_zero_override_defers_borrowed_repayment(self):
        loan = self.credit(opening=90000)
        self.override(loan, 0)
        _, payments = self.pay_events(loan)
        self.assertEqual(0, payments[0]['account_amount_cents'])
        self.assertEqual(90000, payments[0]['remaining_after_cents'])
        self.assertEqual(0, payments[-1]['remaining_after_cents'])
        self.assertEqual(22500, payments[-1]['account_amount_cents'])

    def test_other_credit_types_keep_old_ledger_behavior(self):
        for kind in ('credit', 'consumer_credit', 'mortgage'):
            with self.subTest(kind=kind):
                loan = self.credit(kind=kind, name=f'Sample {kind}', opening=135000)
                self.override(loan, 30650)
                _, payments = self.pay_events(loan)
                self.assertEqual(33750, payments[0]['effective_reduction_cents'])
                self.assertEqual(33750, payments[0]['account_amount_cents'])
                self.assertFalse(payments[0]['amount_overridden'])

    def test_interest_active_first_completed_last_and_borrowed_excluded(self):
        completed = self.credit('credit','Already repaid', opening=10000)
        self.manual(completed, 10000, '2026-10-05')
        borrowed = self.credit('borrowed','Borrowed excluded', opening=100000)
        active = self.credit('credit','Still running', opening=100000)
        # Preserve an old interest booking for a completed loan.
        self.repo.create_interest_booking({
            'household_id': self.hid, 'credit_id':completed['id'],
            'booking_date':'2026-10-04', 'amount_cents':125,
            'account_id':self.account_id,
        })
        view = self.repo.list_interest(self.hid, '2026-10-16')
        ids = [row['credit_id'] for row in view['items']]
        self.assertNotIn(borrowed['id'], ids)
        self.assertEqual([active['id'],completed['id']], ids)
        self.assertFalse(view['items'][0]['completed'])
        self.assertTrue(view['items'][1]['completed'])
        self.assertTrue(any(row['credit_id']==completed['id'] for row in view['bookings']))

    def test_manually_archived_credit_is_at_bottom(self):
        active = self.credit('credit','Open item', opening=150000)
        archived = self.credit('credit','Manually closed', opening=120000)
        self.repo.set_credit_archived(archived['id'], {'household_id':self.hid,'archived':True})
        view=self.repo.list_interest(self.hid, '2026-10-16')
        self.assertEqual([active['id'],archived['id']], [c['credit_id'] for c in view['items']])
        self.assertTrue(view['items'][-1]['completed'])
