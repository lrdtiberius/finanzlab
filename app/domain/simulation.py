from collections import defaultdict
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from .model import Event

def simulate_daily(anchor, events, through):
    if through < anchor.anchor_date: raise ValueError("end precedes anchor")
    grouped=defaultdict(list)
    for event in events:
        if event.account_id==anchor.account_id and anchor.anchor_date < event.effective_date <= through: grouped[event.effective_date].append(event)
    day=anchor.anchor_date; balance=anchor.balance_cents; result=[]
    while day <= through:
        today=grouped[day]; balance += sum(e.amount_cents for e in today)
        result.append({"date":day.isoformat(),"balance_cents":balance,"events":[e.label for e in today]}); day += timedelta(days=1)
    return result

def overdraft_interest(rows, annual_rate: Decimal, basis=365):
    if basis not in (360,365,366): raise ValueError("unsupported basis")
    raw=sum((Decimal(max(0,-r["balance_cents"]))*annual_rate/Decimal(basis) for r in rows),Decimal(0))
    return int(raw.quantize(Decimal("1"),rounding=ROUND_HALF_UP))

def transfer_events(key, source, target, day, amount_cents):
    if amount_cents <= 0 or source == target: raise ValueError("invalid transfer")
    label=f"Umbuchung {key}"
    return Event(source,day,day,-amount_cents,label),Event(target,day,day,amount_cents,label)
