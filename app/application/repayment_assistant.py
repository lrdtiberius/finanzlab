"""Read-only FinanzLab liquidity warnings and repayment decision support.

Recommendations are NEVER inserted into the database. Existing special-payment
expense flows are already included in the repository's authoritative timelines.
"""
from calendar import monthrange
from datetime import date, timedelta

SAFETY_RESERVE_CENTS = 10_000
LARGE_DEBIT_CENTS = 40_000


def following_month(month):
    year, number = map(int, month.split('-'))
    return f'{year + (number == 12):04d}-{number % 12 + 1:02d}'


def month_end(month):
    year, number = map(int, month.split('-'))
    return f'{month}-{monthrange(year, number)[1]:02d}'


def worst_daily_balance(day, account_id):
    """Conservative low on one day: debits may precede all scheduled receipts."""
    acc = next((a for a in day['accounts'] if a['id'] == account_id), None)
    if not acc or acc.get('projected_balance_cents') is None:
        return None
    receipts = sum(max(0, int(e['amount_cents']))
                   for e in day['movements'] if e.get('account_id') == account_id
                   and e.get('applied_to_projection', True))
    return int(acc['projected_balance_cents']) - receipts


def projected_loan_balance(credit, through):
    reduction = sum(int(p.get('balance_reduction_cents', p.get('effective_reduction_cents', 0)) or 0)
                    for p in credit.get('payments', ()) if p['date'] <= through and not p.get('skipped'))
    return max(0, int(credit['opening_balance_cents']) - reduction)


def future_regular_installments(credit, after):
    return [p for p in credit.get('payments', ())
            if p['date'] > after and p.get('source') == 'expense'
            and p.get('credit_payment_type', 'regular') == 'regular'
            and not p.get('skipped') and int(p.get('account_amount_cents') or 0) > 0]


def compute_from_forecasts(*, today, month, accounts, daily, liquidity_current,
                           liquidity_next, credits, reserve=SAFETY_RESERVE_CENTS,
                           large_debit=LARGE_DEBIT_CENTS):
    current = date.fromisoformat(today)
    selected_start = date.fromisoformat(month + '-01')
    next_month = following_month(month)
    start = max(current, selected_start)
    window_end = month_end(next_month)
    bank_accounts = {a['id']: a for a in accounts if a.get('kind') != 'credit_line'}
    limits = {aid: int(a.get('overdraft_limit_cents') or 0)
              for aid, a in bank_accounts.items()}
    known = {aid for aid, a in bank_accounts.items() if a.get('anchor_date')}
    days = sorted((d for d in daily if start.isoformat() <= d['date'] <= window_end),
                  key=lambda d: d['date'])
    # Authoritative net change in regular bank accounts, including financing
    # transfers. Bank-internal transfers cancel out in this aggregate. The
    # account-by-account daily check remains a hard limit, so a positive monthly
    # change does not by itself authorize a payment.
    next_shortfall = max(0, -int(liquidity_next))
    liquidity_budget = max(0, int(liquidity_current) - next_shortfall)
    ready = bool(days and known and selected_start >= current.replace(day=1))

    # Alerts belong strictly to the selected dashboard month.  In the current
    # month old days are excluded; for future months the entire month can be
    # reviewed.  'imminent' marks an upcoming event within the next 3 days.
    warn_end = month_end(month)
    warnings = []
    for day in days:
        if day['date'][:7] != month or day['date'] > warn_end:
            continue
        for aid, account in bank_accounts.items():
            debits = [e for e in day['movements']
                      if e.get('account_id') == aid and e.get('applied_to_projection', True)
                      and int(e.get('amount_cents') or 0) < 0]
            if not debits:
                continue
            lowest = worst_daily_balance(day, aid)
            if lowest is None:
                continue
            gap = lowest + limits[aid]
            large = [e for e in debits if -int(e['amount_cents']) >= large_debit]
            total = sum(-int(e['amount_cents']) for e in debits)
            if gap >= reserve and not large and total < large_debit:
                continue
            warnings.append({
                'date': day['date'], 'account_id': aid, 'account_name': account['name'],
                'available_headroom_cents': gap, 'worst_balance_cents': lowest,
                'debit_total_cents': total,
                'labels': [e.get('label') or 'Abbuchung' for e in (large or debits)][:4],
                'critical': gap < 0, 'under_reserve': gap < reserve,
                'imminent': day['date'] <= (current + timedelta(days=3)).isoformat(),
            })

    result = {
        'as_of': today, 'month': month, 'warning_month': month, 'next_month': next_month,
        'liquidity_current_cents': int(liquidity_current),
        'liquidity_next_cents': int(liquidity_next),
        'negative_next_month_reserve_cents': next_shortfall,
        'max_liquidity_amount_cents': liquidity_budget,
        'safety_reserve_cents': reserve,
        'large_debit_threshold_cents': large_debit,
        'warn_days': 3, 'warnings': warnings,
        'already_planned': [], 'recommendations': [], 'candidates': [],
        'status': 'ok' if ready else 'insufficient_data',
        'notes': ['Prognosen berücksichtigen nur erfasste Buchungen; unbekannte Zinsen und Gebühren können abweichen.',
                  'Am selben Tag zählen Geldeingänge vorsichtshalber erst nach Abbuchungen.'],
    }
    missing_anchors = [a['name'] for aid, a in bank_accounts.items() if aid not in known]
    if missing_anchors:
        result['notes'].append('Konten ohne aktuellen Kontostandanker: ' + ', '.join(missing_anchors))
    if not ready:
        return result

    for credit in credits:
        if credit.get('credit_type') != 'consumer_credit' or credit.get('archived'):
            continue
        plan = credit.get('payment_plan') or {}
        aid = plan.get('account_id')
        payments = future_regular_installments(credit, today)
        monthly_rate = int(plan.get('amount_cents') or 0)
        if monthly_rate <= 0 and payments:
            monthly_rate = max(int(p.get('account_amount_cents') or 0) for p in payments)
        # A loan without a future installment has nothing to free up.
        if not payments or monthly_rate <= 0:
            continue
        pending = [p for p in credit.get('payments', ())
                   if p.get('source') == 'expense' and p.get('credit_payment_type') == 'special'
                   and p['date'] >= today and not p.get('skipped')]
        if pending:
            result['already_planned'].append({'credit_id': credit['id'], 'name': credit['name'],
                                               'date': min(p['date'] for p in pending)})
        # No holiday calendar: use ordinary weekdays. Never infer a bank's
        # booking order or an early value date from a public holiday.
        candidate_days = [d for d in days if d['date'][:7] == month
                          and date.fromisoformat(d['date']).weekday() < 5]
        if not candidate_days:
            continue
        first_day = candidate_days[0]['date']
        balance = projected_loan_balance(credit, first_day)
        if balance <= 0:
            continue
        entry = {
            'credit_id': credit['id'], 'name': credit['name'],
            'amount_cents': balance, 'monthly_rate_cents': monthly_rate,
            'regular_end': credit.get('expected_repayment_date') or credit.get('contractual_end_date'),
            'account_name': bank_accounts.get(aid, {}).get('name', 'Nicht zugeordnet'),
            'date': first_day, 'status': 'blocked', 'reason': '',
            'max_daily_payoff_cents': 0, 'shortfall_cents': 0,
        }
        if pending:
            entry.update(status='planned', reason='Sondertilgung bereits als Ausgabe erfasst')
        elif not credit.get('free_special_repayment'):
            entry.update(reason='Kostenlose Sondertilgung für diesen Kredit nicht aktiviert')
        elif aid not in known:
            entry.update(reason='Tilgungskonto ohne gültigen Kontostandanker oder nicht zugeordnet')
        elif liquidity_budget <= 0:
            entry.update(reason='Kein positiver Liquiditätsspielraum nach Reservierung des Folgemonats')
        else:
            # Simulate a one-time payoff on EACH prospective day, then
            # validate EVERY calendar day through the end of the next month.
            # This avoids approving a 1 Jan payment that causes a breach on
            # 2 Jan (or any other later day). Weekends still appear in the
            # daily safety simulation; holidays are deliberately ignored.
            most_available = 0
            for day in candidate_days:
                payoff_date = day['date']
                amount = projected_loan_balance(credit, payoff_date)
                if amount <= 0:
                    continue
                # No ambiguous same-day ordering with a contractual rate.
                # A payoff on that day could run before the regular payment.
                if any(p['date'] == payoff_date for p in
                       future_regular_installments(credit, (date.fromisoformat(payoff_date) - timedelta(days=1)).isoformat())):
                    continue
                saved = future_regular_installments(credit, payoff_date)
                if not saved:
                    continue
                future_days = [d for d in days if d['date'] >= payoff_date]
                if not future_days:
                    continue
                # The forecast must have no missing days, including weekends,
                # from the proposed value date through next month's end.
                last = date.fromisoformat(window_end)
                expected_days = (last - date.fromisoformat(payoff_date)).days + 1
                if (len(future_days) != expected_days or
                    any(d['date'] != (date.fromisoformat(payoff_date) + timedelta(days=i)).isoformat()
                        for i, d in enumerate(future_days))):
                    continue
                minimum_headroom = None
                minimum_day = None
                safe = True
                for coming in future_days:
                    due = coming['date']
                    low = worst_daily_balance(coming, aid)
                    if low is None:
                        safe = False
                        break
                    # Monthly installments disappear after full repayment.
                    # These savings are only counted once each installment's
                    # original due date has actually been reached.
                    saved_to_account = sum(int(p['account_amount_cents'])
                           for p in saved if p['date'] <= due
                           and (p.get('account_id') or aid) == aid)
                    headroom = low + limits[aid] - reserve + saved_to_account
                    if minimum_headroom is None or headroom < minimum_headroom:
                        minimum_headroom, minimum_day = headroom, due
                    # This repayment only changes its linked payment account.
                    # Other bank accounts (e.g. Sparkasse) must not veto a payoff
                    # from ING because of an unrelated existing overdraft.
                    # Global overdraft alerts remain unaffected; the selected
                    # account still has to satisfy its reserve on *every* day.
                if minimum_headroom is None:
                    continue
                if safe:
                    most_available = max(most_available,
                                         min(liquidity_budget, max(0, minimum_headroom)))
                if not safe or amount > liquidity_budget or amount > minimum_headroom:
                    continue
                # A saved instalment is one scheduled, non-skipped regular
                # account debit, including a potentially smaller final rate.
                # Never estimate the count by dividing the balance by the rate.
                # The repository deliberately projects only a bounded credit
                # horizon; label the count as a LOWER BOUND if the known
                # schedule has not yet reached its end.
                avoided_dates = sorted(p['date'] for p in saved)
                known_end = (credit.get('expected_repayment_date') or
                             plan.get('stream_end'))
                horizon_end = credit.get('through')
                complete = bool(known_end and horizon_end and known_end <= horizon_end)
                entry.update(status='recommended', date=payoff_date, amount_cents=amount,
                             max_daily_payoff_cents=minimum_headroom,
                             rate_freed_from=avoided_dates[0],
                             avoided_installment_count=len(avoided_dates),
                             avoided_installment_dates=avoided_dates,
                             avoided_installments_complete=complete,
                             headroom_above_reserve_cents=minimum_headroom - amount,
                             minimum_dispo_headroom_after_cents=minimum_headroom - amount + reserve,
                             minimum_dispo_headroom_date=minimum_day,
                             checked_through=window_end)
                result['recommendations'].append(dict(entry))
                break
            if entry['status'] != 'recommended':
                entry['max_daily_payoff_cents'] = most_available
                if balance > liquidity_budget:
                    entry['reason'] = 'Ablösebetrag übersteigt den Liquiditäts-Spielraum aus Monat und Folgemonat'
                    entry['shortfall_cents'] = balance - liquidity_budget
                elif most_available < balance:
                    entry['reason'] = 'Tagesgenauer Dispopuffer reicht für eine vollständige Ablösung nicht aus'
                    entry['shortfall_cents'] = balance - most_available
                else:
                    entry['reason'] = 'Keine sichere Buchung innerhalb des gewählten Monats gefunden'
        result['candidates'].append(entry)

    key = lambda item: (-item['monthly_rate_cents'] / max(1, item['amount_cents']),
                        -item['monthly_rate_cents'], item['name'])
    result['recommendations'].sort(key=key)
    result['recommendations'] = result['recommendations'][:5]
    result['candidates'].sort(key=lambda item: (
        {'recommended': 0, 'blocked': 1, 'planned': 2}.get(item['status'], 2), *key(item)))
    if not result['recommendations']:
        result['notes'].append('Zurzeit keine sichere vollständige Ablösung. Gründe stehen bei den Kreditkandidaten; Teiltilgungen ändern die Rate nicht automatisch.')
    return result


def build_dashboard_assistant(repository, household_id, month=None, as_of=None,
                              reserve_cents=SAFETY_RESERVE_CENTS,
                              large_debit_cents=LARGE_DEBIT_CENTS):
    reserve_cents = int(reserve_cents)
    large_debit_cents = int(large_debit_cents)
    if not 0 <= reserve_cents <= 100_000 or not 0 <= large_debit_cents <= 5_000_000:
        raise ValueError('Ungültige Assistent-Einstellungen.')
    today = date.fromisoformat(as_of or date.today().isoformat()).isoformat()
    month = month or today[:7]
    date.fromisoformat(month + '-01')
    household = repository.household_detail(household_id, today)
    if not household:
        raise ValueError('Haushalt nicht gefunden.')
    bank_ids = [a['id'] for a in household['accounts'] if a.get('kind') != 'credit_line']
    current = repository.dashboard(household_id, month_end(month), include_credit_summary=False)
    next_month = following_month(month)
    following = repository.dashboard(household_id, month_end(next_month), include_credit_summary=False)
    first_preview = repository.monthly_preview(household_id, month, bank_ids, [])
    next_preview = repository.monthly_preview(household_id, next_month, bank_ids, [])
    credit_horizon = f'{int(month[:4]) + 2:04d}-{month[5:7]}'
    credits = repository.list_credits(household_id, today, month_end(credit_horizon))
    return compute_from_forecasts(
        today=today, month=month, accounts=household['accounts'],
        daily=first_preview['days'] + next_preview['days'],
        liquidity_current=current['metrics']['liquidity_delta_cents'],
        liquidity_next=following['metrics']['liquidity_delta_cents'],
        credits=credits['items'], reserve=reserve_cents, large_debit=large_debit_cents)
