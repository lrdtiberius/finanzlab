from datetime import date, timedelta
from .model import ShiftRule

def is_business_day(day: date, holidays=frozenset()):
    return day.weekday() < 5 and day not in holidays

def shift_to_business_day(day: date, rule: ShiftRule, holidays=frozenset()):
    if rule == ShiftRule.KEEP or is_business_day(day, holidays): return day
    delta = -1 if rule == ShiftRule.PREVIOUS else 1
    while not is_business_day(day, holidays): day += timedelta(days=delta)
    return day
