"""Working-day arithmetic. Plain code, never model output.

A day is a working day unless it falls on a weekend, on a supplied holiday, or on a declared work
suspension. The repository ships an EMPTY holiday list (``config/calendar.yaml``): nothing is
invented. Tests build their own fixture calendars.

Convention: ``working_days_elapsed(start, end)`` counts working days ``d`` with
``start < d <= end``. The day of receipt is day 0, so an application received on a Monday has
used 3 working days on Thursday.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CALENDAR = REPO_ROOT / "config" / "calendar.yaml"

# Calbayog local time. Fixed offset, no daylight saving, so plain arithmetic is exact.
PHT = timezone(timedelta(hours=8), "PHT")

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DEFAULT_WEEKEND = frozenset({5, 6})  # Saturday, Sunday (Monday = 0)


def as_date(value: date | datetime) -> date:
    """Reduce a date or datetime to a date; anything else is a TypeError."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raise TypeError(f"expected date or datetime, got {type(value).__name__}")


def _parse_iso_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not _ISO_DATE.match(value):
        raise ValueError(f"calendar dates must be YYYY-MM-DD strings, got {value!r}")
    return date.fromisoformat(value)


def _entries(raw: Any, key: str) -> dict[date, str]:
    out: dict[date, str] = {}
    for item in raw or []:
        if isinstance(item, dict):
            when = _parse_iso_date(item.get("date"))
            out[when] = str(item.get("reason") or item.get("name") or key)
        else:
            out[_parse_iso_date(item)] = key
    return out


@dataclass(frozen=True)
class SuspensionCheck:
    date: date
    suspended: bool  # a declared work suspension (typhoon, etc.)
    working_day: bool
    reason: str | None  # the suspension's own reason text when suspended
    non_working_reason: str | None  # "suspension" | "holiday" | "weekend" | None


@dataclass(frozen=True)
class Calendar:
    holidays: dict[date, str] = field(default_factory=dict)
    suspensions: dict[date, str] = field(default_factory=dict)
    weekend: frozenset[int] = DEFAULT_WEEKEND

    @classmethod
    def from_yaml(cls, path: str | Path | None = None, weekend: frozenset[int] | None = None):
        data = yaml.safe_load(Path(path or DEFAULT_CALENDAR).read_text(encoding="utf-8")) or {}
        return cls(
            holidays=_entries(data.get("holidays"), "holiday"),
            suspensions=_entries(data.get("work_suspensions"), "work suspension"),
            weekend=weekend if weekend is not None else DEFAULT_WEEKEND,
        )

    def with_suspensions(self, days: dict[date, str]) -> Calendar:
        return Calendar({**self.holidays}, {**self.suspensions, **days}, self.weekend)

    def without_suspensions(self) -> Calendar:
        return Calendar({**self.holidays}, {}, self.weekend)

    def non_working_reason(self, day: date | datetime) -> str | None:
        d = as_date(day)
        if d in self.suspensions:
            return "suspension"
        if d in self.holidays:
            return "holiday"
        if d.weekday() in self.weekend:
            return "weekend"
        return None

    def is_working_day(self, day: date | datetime) -> bool:
        return self.non_working_reason(day) is None

    def add_working_days(self, start: date | datetime, n: int) -> date:
        """The date ``n`` working days after ``start`` (``n = 0`` returns ``start``)."""
        if n < 0:
            raise ValueError("n must not be negative")
        d = as_date(start)
        left = n
        while left:
            d += timedelta(days=1)
            if self.is_working_day(d):
                left -= 1
        return d

    def subtract_working_days(self, end: date | datetime, n: int) -> date:
        """The latest working date ``d`` with exactly ``n`` working days in ``(d, end]``.

        ``n = 0`` gives ``end``'s date, or the working day before it when ``end`` is not one.
        """
        if n < 0:
            raise ValueError("n must not be negative")
        d = as_date(end)
        left = n
        while left:
            if self.is_working_day(d):
                left -= 1
            d -= timedelta(days=1)
        while not self.is_working_day(d):
            d -= timedelta(days=1)
        return d


def working_days_elapsed(
    start: date | datetime, end: date | datetime, calendar: Calendar | None = None
) -> int:
    """Working days ``d`` with ``start < d <= end`` under ``calendar``."""
    cal = calendar or Calendar()
    a, b = as_date(start), as_date(end)
    if b < a:
        raise ValueError("end is before start")
    count = 0
    d = a
    while d < b:
        d += timedelta(days=1)
        if cal.is_working_day(d):
            count += 1
    return count


def check_work_suspension(
    day: date | datetime, calendar: Calendar | None = None
) -> SuspensionCheck:
    cal = calendar or Calendar()
    d = as_date(day)
    reason = cal.non_working_reason(d)
    return SuspensionCheck(
        date=d,
        suspended=d in cal.suspensions,
        working_day=reason is None,
        reason=cal.suspensions.get(d),
        non_working_reason=reason,
    )
