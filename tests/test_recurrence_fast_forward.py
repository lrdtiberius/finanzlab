import random
from datetime import date, timedelta

from app.domain.recurrence import (
    RECURRENCE_MONTHS,
    WEEKLY_DAYS,
    _as_date,
    add_months_anchored,
    next_weekday,
    planned_booking_dates,
    previous_friday,
    recurrence_dates,
)


def _legacy_recurrence_dates(
    first_due_date,
    recurrence,
    start_exclusive,
    end_inclusive,
    active_from=None,
    active_to_exclusive=None,
    stream_start=None,
    stream_end=None,
    max_occurrences=None,
):
    """Reference implementation used before the 2.6.0 fast-forward."""
    if not first_due_date:
        return []
    first = _as_date(first_due_date)
    start = _as_date(start_exclusive)
    end = _as_date(end_inclusive)
    valid_from = _as_date(active_from) if active_from else first
    valid_to = _as_date(active_to_exclusive) if active_to_exclusive else None
    stream_from = _as_date(stream_start) if stream_start else valid_from
    stream_until = _as_date(stream_end) if stream_end else None

    def effective(day):
        return (
            start < day <= end
            and day >= valid_from
            and (valid_to is None or day < valid_to)
            and day >= stream_from
            and (stream_until is None or day <= stream_until)
        )

    occurrence_limit = None
    if max_occurrences not in (None, ""):
        occurrence_limit = int(max_occurrences)
        if occurrence_limit < 1:
            return []
    if recurrence == "once":
        return [first] if effective(first) and occurrence_limit != 0 else []
    if recurrence == "weekly":
        result = []
        occurrence_number = 0
        while True:
            if occurrence_limit is not None and occurrence_number >= occurrence_limit:
                break
            due = first + timedelta(days=occurrence_number * WEEKLY_DAYS)
            if due > end:
                break
            if effective(due):
                result.append(due)
            occurrence_number += 1
        return result
    months = RECURRENCE_MONTHS.get(recurrence)
    if months is None:
        raise ValueError(f"Unbekannter Zahlungsrhythmus: {recurrence}")
    result = []
    offset = 0
    occurrence_number = 0
    while True:
        if occurrence_limit is not None and occurrence_number >= occurrence_limit:
            break
        due = add_months_anchored(first, offset)
        if due > end:
            break
        if effective(due):
            result.append(due)
        offset += months
        occurrence_number += 1
    return result


def _legacy_planned_booking_dates(
    first_due_date,
    recurrence,
    start_exclusive,
    end_inclusive,
    active_from=None,
    active_to_exclusive=None,
    stream_start=None,
    stream_end=None,
    max_occurrences=None,
    move_weekends_forward=False,
):
    start = _as_date(start_exclusive)
    end = _as_date(end_inclusive)
    contractual_dates = _legacy_recurrence_dates(
        first_due_date,
        recurrence,
        start - timedelta(days=2),
        end + timedelta(days=2),
        active_from,
        active_to_exclusive,
        stream_start,
        stream_end,
        max_occurrences,
    )
    result = []
    for due in contractual_dates:
        booking_date = next_weekday(due) if move_weekends_forward else previous_friday(due)
        if start < booking_date <= end:
            result.append(booking_date)
    return result


def test_month_end_and_leap_year_cases_match_legacy():
    cases = [
        (date(2000, 1, 31), "monthly", date(2025, 1, 1), date(2028, 3, 31)),
        (date(2000, 2, 29), "yearly", date(2024, 2, 28), date(2032, 3, 1)),
        (date(1999, 8, 31), "semiannual", date(2025, 2, 27), date(2027, 9, 1)),
        (date(2020, 11, 30), "quarterly", date(2026, 2, 28), date(2028, 12, 31)),
    ]
    for first, recurrence, start, end in cases:
        expected = _legacy_recurrence_dates(first, recurrence, start, end)
        assert recurrence_dates(first, recurrence, start, end) == expected


def test_occurrence_limit_counts_historical_occurrences():
    assert recurrence_dates(
        date(2010, 1, 31),
        "monthly",
        date(2026, 1, 1),
        date(2026, 12, 31),
        max_occurrences=100,
    ) == []
    assert recurrence_dates(
        date(2020, 1, 4),
        "weekly",
        date(2026, 1, 1),
        date(2026, 2, 1),
        max_occurrences=500,
    ) == _legacy_recurrence_dates(
        date(2020, 1, 4),
        "weekly",
        date(2026, 1, 1),
        date(2026, 2, 1),
        max_occurrences=500,
    )


def test_weekend_booking_shifts_match_legacy_in_both_directions():
    args = (
        date(2000, 1, 1),
        "monthly",
        date(2026, 1, 1),
        date(2027, 12, 31),
    )
    for forward in (False, True):
        assert planned_booking_dates(*args, move_weekends_forward=forward) == (
            _legacy_planned_booking_dates(*args, move_weekends_forward=forward)
        )


def test_unknown_recurrence_still_raises_for_an_empty_interval():
    try:
        recurrence_dates(date(2026, 1, 1), "invalid", date(2027, 1, 1), date(2027, 1, 1))
    except ValueError as exc:
        assert "Unbekannter Zahlungsrhythmus" in str(exc)
    else:
        raise AssertionError("unknown recurrence must raise ValueError")


def test_randomized_differential_against_legacy():
    randomizer = random.Random(2600)
    recurrences = ("once", "weekly", "monthly", "quarterly", "semiannual", "yearly")
    epoch = date(1990, 1, 1)

    for _ in range(50_000):
        first = epoch + timedelta(days=randomizer.randrange(0, 12_000))
        start = first + timedelta(days=randomizer.randrange(-60, 8_000))
        end = start + timedelta(days=randomizer.randrange(0, 1_100))
        active_from = first + timedelta(days=randomizer.randrange(0, 1_000)) if randomizer.random() < 0.45 else None
        active_to = (
            first + timedelta(days=randomizer.randrange(0, 9_000))
            if randomizer.random() < 0.35
            else None
        )
        stream_from = (
            first + timedelta(days=randomizer.randrange(0, 1_500))
            if randomizer.random() < 0.35
            else None
        )
        stream_end = (
            first + timedelta(days=randomizer.randrange(0, 9_000))
            if randomizer.random() < 0.35
            else None
        )
        max_occurrences = randomizer.choice((None, "", 0, 1, 2, 12, 100, 1_000))
        recurrence = randomizer.choice(recurrences)
        args = (
            first,
            recurrence,
            start,
            end,
            active_from,
            active_to,
            stream_from,
            stream_end,
            max_occurrences,
        )
        assert recurrence_dates(*args) == _legacy_recurrence_dates(*args)

