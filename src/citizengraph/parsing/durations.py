"""Parse charter processing-time cells into structured durations.

Handles minutes, hours, days, weeks, ranges and combinations, tolerating the charter's
inconsistent grammar ("1 hours, 14 minutes", "30 min/s"). ``- - -`` or blank means not stated.
Anything else is returned with the raw text kept, never guessed (CLAUDE.md rule 7):

* ``unparsed``: text the parser does not understand.
* ``ambiguous``: a decimal such as "1.15 min", which could be 1 h 15 min or 1.15 minutes. Not
  converted; ``review`` says why.
* ``stated`` with ``normalizations``: a known unit typo ("dsys") was read as its unit and the
  reading is recorded so a reviewer can see it.

``day_type`` is always ``"unknown"``: the charters do not say whether "10 days" or "1 week" are
calendar or working days (docs/charter_data.md section 5). Weeks are their own axis and are never
turned into days.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

Unit = Literal["minute", "hour", "day", "week"]
Status = Literal["stated", "not_stated", "unparsed", "ambiguous"]

_MINUTES_PER = {"minute": 1, "hour": 60, "day": 24 * 60, "week": 7 * 24 * 60}

_UNIT_WORDS = {
    "minute": r"min/s|minutes?|mins?",
    "hour": r"hours?|hrs?",
    "day": r"days?",
    "week": r"weeks?|wks?",
}
# Typos seen in the charters, read as their unit and recorded. Extend only with typos that are
# unmistakable; anything else stays unparsed.
_TYPO_UNITS: dict[str, Unit] = {"dsys": "day", "dys": "day", "dyas": "day"}
_UNIT_PATTERN = "|".join(f"(?P<{u}>{w})" for u, w in _UNIT_WORDS.items())
_UNIT_PATTERN += "|(?P<typo>" + "|".join(_TYPO_UNITS) + ")"
_NUM = r"\d+(?:\.\d+)?"
_COMPONENT = re.compile(
    rf"(?P<lo>{_NUM})(?:\s*(?:-|–|to)\s*(?P<hi>{_NUM}))?\s*(?:{_UNIT_PATTERN})\b",
    re.IGNORECASE,
)
_DECIMAL = re.compile(r"\d\.\d")
_PARENTHETICAL = re.compile(r"\([^)]*\)")
_JOINERS = re.compile(r"\band\b|&|,", re.IGNORECASE)
_NOT_STATED = re.compile(r"^[\s\-–—]*$")


@dataclass(frozen=True)
class DurationComponent:
    value_min: float
    value_max: float
    unit: Unit

    def to_dict(self) -> dict[str, Any]:
        return {
            "value_min": _num(self.value_min),
            "value_max": _num(self.value_max),
            "unit": self.unit,
        }


@dataclass(frozen=True)
class Duration:
    status: Status
    components: tuple[DurationComponent, ...]
    raw: str | None
    day_type: Literal["unknown"] = "unknown"
    review: str | None = None
    normalizations: tuple[str, ...] = ()

    def _sum(self, units: tuple[Unit, ...], attr: str) -> float:
        return sum(
            getattr(c, attr) * _MINUTES_PER[c.unit] for c in self.components if c.unit in units
        )

    @property
    def stated(self) -> bool:
        return self.status == "stated"

    @property
    def days_min(self) -> float | None:
        return self._sum(("day",), "value_min") / _MINUTES_PER["day"] if self.stated else None

    @property
    def days_max(self) -> float | None:
        return self._sum(("day",), "value_max") / _MINUTES_PER["day"] if self.stated else None

    @property
    def weeks_min(self) -> float | None:
        return self._sum(("week",), "value_min") / _MINUTES_PER["week"] if self.stated else None

    @property
    def weeks_max(self) -> float | None:
        return self._sum(("week",), "value_max") / _MINUTES_PER["week"] if self.stated else None

    @property
    def clock_minutes_min(self) -> float | None:
        return self._sum(("minute", "hour"), "value_min") if self.stated else None

    @property
    def clock_minutes_max(self) -> float | None:
        return self._sum(("minute", "hour"), "value_max") if self.stated else None

    @property
    def minutes_min(self) -> float | None:
        """Benchmark-only total; a day counts as 1,440 minutes (day_type is unknown)."""
        return self._sum(("minute", "hour", "day", "week"), "value_min") if self.stated else None

    @property
    def minutes_max(self) -> float | None:
        return self._sum(("minute", "hour", "day", "week"), "value_max") if self.stated else None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "status": self.status,
            "components": [c.to_dict() for c in self.components],
            "minutes_min": _num(self.minutes_min),
            "minutes_max": _num(self.minutes_max),
            "day_type": self.day_type,
            "raw": self.raw,
        }
        if self.review:
            out["review"] = self.review
        if self.normalizations:
            out["normalizations"] = list(self.normalizations)
        return out


def _num(value: float | None) -> int | float | None:
    if value is None:
        return None
    return int(value) if float(value).is_integer() else value


def parse_duration(text: str | None) -> Duration:
    """Parse one processing-time cell. Never raises."""
    if text is None or _NOT_STATED.match(text):
        return Duration("not_stated", (), text)

    cleaned = _PARENTHETICAL.sub(" ", text)
    if _DECIMAL.search(cleaned):
        review = (
            "decimal value: could be clock notation (e.g. 1.15 = 1 h 15 min) or a fraction "
            "(1.15 min); not converted, ask the LGU"
        )
        return Duration("ambiguous", (), text, review=review)

    components: list[DurationComponent] = []
    normalizations: list[str] = []
    for m in _COMPONENT.finditer(cleaned):
        if m.group("typo"):
            typo = m.group("typo").lower()
            unit: Unit = _TYPO_UNITS[typo]
            normalizations.append(f"{typo} -> {unit}")
        else:
            unit = next(u for u in _UNIT_WORDS if m.group(u))  # type: ignore[assignment]
        lo = float(m.group("lo"))
        hi = float(m.group("hi")) if m.group("hi") else lo
        if hi < lo:
            return Duration("unparsed", (), text)
        components.append(DurationComponent(lo, hi, unit))

    leftover = _JOINERS.sub(" ", _COMPONENT.sub(" ", cleaned)).strip()
    if not components or leftover:
        return Duration("unparsed", (), text)
    return Duration("stated", tuple(components), text, normalizations=tuple(normalizations))
