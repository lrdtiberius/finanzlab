from dataclasses import dataclass
from datetime import date
from enum import Enum

class ShiftRule(str, Enum):
    PREVIOUS = "previous_business_day"
    NEXT = "next_business_day"
    KEEP = "keep_calendar_day"

@dataclass(frozen=True)
class Event:
    account_id: str
    contractual_date: date
    effective_date: date
    amount_cents: int
    label: str

@dataclass(frozen=True)
class BalanceAnchor:
    account_id: str
    anchor_date: date
    balance_cents: int
