"""Synthetic regressions for replacement plans and borrowed-loan interest filtering.

The test fixtures never load user financial data.
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


class CreditPlanReplacementTests(TestCase):
    def setUp(self):
        clock = patch('app.infrastructure.repository.date', FixedDate)
        clock.start()
        self.addCleanup(clock.stop)
        tmp = TemporaryDirectory(prefix='fl-replacement-')
        self.addCleanup(tmp.cleanup)
        self.repo = TestRepository(Path(tmp.name) / 'demo.db')
        home = self.repo.create_household({
            'name': 'Demo', 'mode': 'single', 'person_a': 'Testperson',
            'account': {'name': 'Testkonto', 'owner': 'A',
                        'balance_cents': 500000, 'anchor_date': '2026-10-16',
                        'bookings_applied': True},
        })
        self.hid = home['id']
        self.account_id = home['accounts'][0]['id']

    def create_loan(self, name, kind='borrowed', opening=270000,
                    amount=33750, due='2026-10-30', count=8, apr='0'):
        return self.repo.create_credit({
            'household_id': self.hid, 'name': name,
            'credit_type': kind, 'opening_balance_cents': opening,
            'interest_rate': apr, 'automatic_interest': kind != 'borrowed',
            'payment_plan': {'amount_cents': amount,
                             'first_due_date': due,
                             'occurrence_count': count,
                             'account_id': self.account_id, 'owner': 'A'},
        })

    def extra_flow(self, credit, cents, due, recurrence='once', count=None):
        return self.repo.create_cash_flow({
            'household_id': self.hid, 'kind': 'expense',
            'name': 'Synthetic debt payment', 'category': credit['credit_type'],
            'credit_id': credit['id'], 'amount_cents': cents,
            'recurrence': recurrence, 'due_date': due,
            'duration_months': count, 'account_id': self.account_id,
            'owner': 'A', 'active': True,
            'effective_from': min(due, '2026-10-16'),
        })

    def update_plan(self, loan, amount=33750, count=4, effective='2026-10-16'):
        return self.repo.update_credit(loan['id'], {
            'household_id': self.hid, 'name': loan['name'],
            'credit_type': loan['credit_type'],
            'opening_balance_cents': loan['opening_balance_cents'],
            'interest_rate': '0', 'automatic_interest': False,
            'balloon_payment_cents': 0,
            'payment_plan': {
                'amount_cents': amount, 'first_due_date': '2026-10-30',
                'occurrence_count': count, 'account_id': self.account_id,
                'owner': 'A', 'flow_id': loan['payment_plan']['flow_id'],
                'effective_from': effective,
            },
        })

    def test_borrowed_replaces_competing_monthly_series_and_keeps_oneoffs(self):
        loan = self.create_loan('Example-Borrowed')
        paid1 = self.extra_flow(loan, 135000, '2026-09-16')
        paid2 = self.extra_flow(loan, 3100, '2026-10-03')
        obsolete = self.extra_flow(loan, 45000, '2026-12-03', 'monthly', 8)
        with self.repo.lock, self.repo.connect() as con:
            con.execute('UPDATE cash_flow_versions SET version_from=?,stream_start=? WHERE cash_flow_id=?',
                        ('2026-08-25','2026-08-25',obsolete['id']))
        self.assertEqual(131900, self.repo.credit_detail(self.hid, loan['id'], '2026-10-16')['remaining_balance_cents'])
        # Ghost installment exists before replacement.
        before = self.repo.monthly_preview(self.hid, '2026-12', [self.account_id], [loan['id']])
        self.assertTrue(any(obsolete['id'] in str(m.get('occurrence_key')) for m in before['movements']))

        updated = self.update_plan(loan)
        self.assertEqual(131900, updated['remaining_balance_cents'])
        scheduled = sorted((p for p in updated['payments'] if p['source'] == 'expense' and p['date'] >= '2026-10-16'), key=lambda p: p['date'])
        self.assertEqual([33750, 33750, 33750, 30650], [p['account_amount_cents'] for p in scheduled])
        self.assertEqual('2027-01-30', updated['contractual_end_date'])
        # The old plan must disappear completely, not survive as a zero-euro line.
        after = self.repo.monthly_preview(self.hid, '2026-12', [self.account_id], [loan['id']])
        self.assertFalse(any(obsolete['id'] in str(m.get('occurrence_key')) for m in after['movements']))
        with self.repo.connect() as con:
            old = con.execute('SELECT * FROM cash_flow_versions WHERE cash_flow_id=?', (obsolete['id'],)).fetchone()
            self.assertEqual('2026-10-16', old['version_to'])
            once = con.execute('SELECT COUNT(*) FROM cash_flow_versions WHERE cash_flow_id IN (?,?) AND active=1', (paid1['id'], paid2['id'])).fetchone()[0]
            self.assertEqual(2, once)

    def test_original_completed_installment_is_preserved_when_plan_changes(self):
        loan = self.create_loan('Earlier-Schedule', opening=360000,
                                amount=45000, due='2026-09-03')
        with self.repo.lock, self.repo.connect() as con:
            con.execute('UPDATE cash_flow_versions SET version_from=?,stream_start=? WHERE cash_flow_id=?',
                        ('2026-09-01','2026-09-01',loan['payment_plan']['flow_id']))
        baseline = self.repo.credit_detail(self.hid, loan['id'], '2026-10-16')
        self.assertEqual(270000, baseline['remaining_balance_cents'])
        updated = self.repo.update_credit(loan['id'], {
            'household_id': self.hid, 'name': loan['name'],
            'credit_type': 'borrowed', 'opening_balance_cents': 360000,
            'interest_rate': '0', 'automatic_interest': False,
            'payment_plan': {'amount_cents': 45000,
                             'first_due_date': '2026-11-03',
                             'occurrence_count': 6, 'account_id': self.account_id,
                             'owner': 'A', 'flow_id': loan['payment_plan']['flow_id'],
                             'effective_from': '2026-10-16'},
        })
        self.assertEqual(baseline['remaining_balance_cents'], updated['remaining_balance_cents'])
        old_payments = [p for p in updated['payments'] if p['source']=='expense' and p['date'] < '2026-10-16']
        self.assertEqual(2, len(old_payments))
        self.assertEqual(90000, sum(p['account_amount_cents'] for p in old_payments))

    def test_future_only_old_versions_disabled_and_repeated_edits_idempotent(self):
        loan = self.create_loan('Next-Series')
        obsolete = self.extra_flow(loan, 45000, '2026-12-03', 'monthly', 8)
        # Historical version is from current date, with a future replacement
        # that should be disabled by the new plan.
        with self.repo.lock, self.repo.connect() as con:
            con.execute('UPDATE cash_flow_versions SET version_from=? WHERE cash_flow_id=?',
                        ('2026-12-01', obsolete['id']))
        self.update_plan(loan, amount=33750)
        self.update_plan(loan, amount=33750)
        with self.repo.connect() as con:
            old = con.execute('SELECT * FROM cash_flow_versions WHERE cash_flow_id=?', (obsolete['id'],)).fetchone()
            self.assertEqual(0, old['active'])
        dec = self.repo.monthly_preview(self.hid, '2026-12', [self.account_id], [loan['id']])
        self.assertFalse(any(obsolete['id'] in str(m.get('occurrence_key')) for m in dec['movements']))

    def test_other_loan_plan_unchanged_after_manual_special_payment(self):
        standard = self.create_loan('Ordinary-Credit', 'credit', 270000, apr='6')
        plan = standard['payment_plan']['flow_id']
        self.repo.add_credit_payment(standard['id'], {
            'household_id': self.hid, 'payment_date': '2026-10-10',
            'amount_cents': 10000,
        })
        with self.repo.connect() as con:
            rows = con.execute('SELECT COUNT(*),MAX(version_to) FROM cash_flow_versions WHERE cash_flow_id=?', (plan,)).fetchone()
        self.assertEqual(1, rows[0])
        self.assertIsNone(rows[1])

    def test_borrowed_excluded_from_interest_overview_and_bookings(self):
        borrowed = self.create_loan('Borrowed-With-Interest', opening=100000, apr='6')
        standard = self.create_loan('Interest-Bearing-Credit', kind='credit', opening=100000, apr='6')
        with self.assertRaisesRegex(ValueError, 'Geliehen'):
            self.repo.create_interest_booking({
                'household_id': self.hid, 'credit_id': borrowed['id'],
                'booking_date': '2026-10-15', 'amount_cents': 500,
                'account_id': self.account_id,
            })
        normal_interest = self.repo.create_interest_booking({
            'household_id': self.hid, 'credit_id': standard['id'],
            'booking_date': '2026-10-15', 'amount_cents': 300,
            'account_id': self.account_id,
        })
        # Simulate an old, formally associated legacy interest booking of a
        # borrowed loan. It must not reappear via the linked generic expense.
        legacy_flow = self.repo.create_cash_flow({
            'household_id': self.hid, 'kind': 'expense',
            'name': 'Historical loan interest', 'category': 'interest',
            'amount_cents': 125, 'recurrence': 'once',
            'due_date': '2026-10-12', 'account_id': self.account_id,
            'owner': 'A', 'active': True,
        })
        with self.repo.lock, self.repo.connect() as con:
            con.execute('''INSERT INTO credit_interest_bookings(
                    id,household_id,credit_id,booking_date,amount_cents,account_id,cash_flow_id
                 ) VALUES(?,?,?,?,?,?,?)''',
                ('legacy-borrowed-test', self.hid, borrowed['id'], '2026-10-12', 125,
                 self.account_id, legacy_flow['id']))
        interest = self.repo.list_interest(self.hid, '2026-10-16')
        self.assertNotIn(borrowed['id'], [row['credit_id'] for row in interest['items']])
        self.assertIn(standard['id'], [row['credit_id'] for row in interest['items']])
        self.assertNotIn(borrowed['id'], [row['credit_id'] for row in interest['bookings']])
        self.assertFalse(any(row.get('cash_flow_id')==legacy_flow['id'] for row in interest['account_interest_bookings']))
        self.assertEqual(300, sum(r['amount_cents'] for r in interest['bookings']))
        self.assertEqual(0, interest['totals']['checking_account_interest_cents'])
