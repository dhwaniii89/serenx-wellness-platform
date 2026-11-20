"""Recurrence logic.

We do NOT run a background scheduler. An assignment stores (frequency, start_date).
Whenever someone opens the app we calculate which due dates have arrived.
That is simple, reliable, and works on free hosting that sleeps.
"""
import calendar
from datetime import date, timedelta

FREQUENCIES = ("once", "daily", "weekly", "monthly")


def _add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def nth_due(start: date, freq: str, i: int) -> date:
    if freq == "once":
        return start
    if freq == "daily":
        return start + timedelta(days=i)
    if freq == "weekly":
        return start + timedelta(weeks=i)
    if freq == "monthly":
        return _add_months(start, i)
    raise ValueError(f"bad frequency: {freq}")


def due_dates(start: date, freq: str, upto: date) -> list[date]:
    """All due dates from start up to and including `upto`."""
    if start > upto:
        return []
    if freq == "once":
        return [start]
    out, i = [], 0
    while True:
        d = nth_due(start, freq, i)
        if d > upto:
            return out
        out.append(d)
        i += 1


def next_due(start: date, freq: str, today: date) -> date | None:
    """First due date strictly after today (None for a finished one-time item)."""
    if freq == "once":
        return start if start > today else None
    i = 0
    while True:
        d = nth_due(start, freq, i)
        if d > today:
            return d
        i += 1


def streak(dues: list[date], done: set[str]) -> int:
    """Consecutive completed due dates counting back from the latest one.

    The latest due date is allowed to still be open (it should not break a streak).
    """
    s = 0
    for i, d in enumerate(reversed(dues)):
        if d.isoformat() in done:
            s += 1
        elif i == 0:
            continue
        else:
            break
    return s
