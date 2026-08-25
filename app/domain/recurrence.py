import calendar
from datetime import date, timedelta


RECURRENCE_MONTHS={"monthly":1,"quarterly":3,"semiannual":6,"yearly":12}
WEEKLY_DAYS=7


def _as_date(value):
    if isinstance(value,date): return value
    return date.fromisoformat(str(value))


def add_months_anchored(first_due_date,offset):
    first=_as_date(first_due_date)
    month_index=first.month-1+int(offset)
    year=first.year+month_index//12
    month=month_index%12+1
    return date(year,month,min(first.day,calendar.monthrange(year,month)[1]))


def last_occurrence_date(first_due_date,recurrence,occurrence_count):
    """Return the contractual date of the final numbered occurrence."""
    first=_as_date(first_due_date)
    count=int(occurrence_count)
    if count<1: raise ValueError("occurrence_count must be positive")
    if recurrence=="once":
        if count!=1: raise ValueError("a one-time recurrence has exactly one occurrence")
        return first
    if recurrence=="weekly":
        return first+timedelta(days=(count-1)*WEEKLY_DAYS)
    months=RECURRENCE_MONTHS.get(recurrence)
    if months is None: raise ValueError(f"Unbekannter Zahlungsrhythmus: {recurrence}")
    return add_months_anchored(first,(count-1)*months)


def last_occurrence_on_or_before(first_due_date,recurrence,end_date):
    """Return the final contractual occurrence not later than ``end_date``."""
    first=_as_date(first_due_date); end=_as_date(end_date)
    if end<first: return None
    if recurrence=="once": return first
    if recurrence=="weekly":
        return first+timedelta(days=((end-first).days//WEEKLY_DAYS)*WEEKLY_DAYS)
    months=RECURRENCE_MONTHS.get(recurrence)
    if months is None: raise ValueError(f"Unbekannter Zahlungsrhythmus: {recurrence}")
    month_distance=(end.year-first.year)*12+end.month-first.month
    occurrence_index=max(0,month_distance//months)
    candidate=add_months_anchored(first,occurrence_index*months)
    while candidate>end and occurrence_index>0:
        occurrence_index-=1
        candidate=add_months_anchored(first,occurrence_index*months)
    return candidate if candidate<=end else None


def recurrence_dates(first_due_date,recurrence,start_exclusive,end_inclusive,
                     active_from=None,active_to_exclusive=None,stream_start=None,stream_end=None,
                     max_occurrences=None):
    """Materialize contractual due dates in a bounded interval.

    The cadence always remains anchored to the original due date.  Version and
    stream boundaries only decide whether an occurrence is effective; they do
    not silently move the cadence.
    """
    if not first_due_date: return []
    first=_as_date(first_due_date); start=_as_date(start_exclusive); end=_as_date(end_inclusive)
    valid_from=_as_date(active_from) if active_from else first
    valid_to=_as_date(active_to_exclusive) if active_to_exclusive else None
    stream_from=_as_date(stream_start) if stream_start else valid_from
    stream_until=_as_date(stream_end) if stream_end else None

    def effective(day):
        return (start<day<=end and day>=valid_from and (valid_to is None or day<valid_to)
                and day>=stream_from and (stream_until is None or day<=stream_until))

    occurrence_limit=None
    if max_occurrences not in (None,""):
        occurrence_limit=int(max_occurrences)
        if occurrence_limit<1: return []
    if recurrence=="once": return [first] if effective(first) and occurrence_limit!=0 else []
    if recurrence=="weekly":
        result=[]; occurrence_number=0
        while True:
            if occurrence_limit is not None and occurrence_number>=occurrence_limit: break
            due=first+timedelta(days=occurrence_number*WEEKLY_DAYS)
            if due>end: break
            if effective(due): result.append(due)
            occurrence_number+=1
        return result
    months=RECURRENCE_MONTHS.get(recurrence)
    if months is None: raise ValueError(f"Unbekannter Zahlungsrhythmus: {recurrence}")
    result=[]; offset=0; occurrence_number=0
    while True:
        if occurrence_limit is not None and occurrence_number>=occurrence_limit: break
        due=add_months_anchored(first,offset)
        if due>end: break
        if effective(due): result.append(due)
        offset+=months; occurrence_number+=1
    return result
