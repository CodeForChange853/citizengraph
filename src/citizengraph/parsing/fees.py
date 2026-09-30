"""Parse charter fee cells into structured fee items.

Handles ``none``, ``- - -``, single amounts, ranges, ``per copy`` / ``/ cock`` units, labelled
multi-item cells, qualifier lines such as ``₱215.00 (individual)``, and asterisk notes. Text that
carries no amount (e.g. "As determined by the CSWMO") is kept as a note, never turned into a
number (CLAUDE.md rule 7).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

Status = Literal["none", "not_stated", "amounts", "text_only"]

_AMT = r"(?<![A-Za-z])(?:₱|PHP|Php|P)\s*(\d[\d,]*(?:\.\d+)?)"
_AMOUNT = re.compile(rf"{_AMT}(?:\s*(?:-|–|—|to)\s*{_AMT})?")
_DASHES = "-–—"
_NOT_STATED = re.compile(r"^[\s\-–—]*$")
_NONE = re.compile(r"^\s*none\b(?P<rest>.*)$", re.IGNORECASE | re.DOTALL)
_LIST_MARKER = re.compile(r"^\s*(?:[A-Za-z]|\d+(?:\.\d+)*)[.)]\s+")
_UNIT = re.compile(
    r"^\s*(?:/|per\b)\s*(?P<unit>[A-Za-z]+(?: [A-Za-z]+)*?)\s*(?=$|\s[-–—]\s|\()", re.I
)
_PARENS = re.compile(r"\(([^)]*)\)")


@dataclass(frozen=True)
class FeeItem:
    label: str | None
    amount_min: float
    amount_max: float
    unit: str | None = None
    qualifier: str | None = None
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "amount_min": _num(self.amount_min),
            "amount_max": _num(self.amount_max),
            "unit": self.unit,
            "qualifier": self.qualifier,
            "note": self.note,
        }


@dataclass(frozen=True)
class FeeParse:
    status: Status
    items: tuple[FeeItem, ...]
    notes: tuple[str, ...]
    raw: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "items": [i.to_dict() for i in self.items],
            "notes": list(self.notes),
            "raw": self.raw,
        }


def _num(value: float) -> int | float:
    return int(value) if float(value).is_integer() else value


def _to_float(text: str) -> float:
    return float(text.replace(",", ""))


def _clean_label(text: str) -> str | None:
    text = _LIST_MARKER.sub("", text)
    text = text.strip().strip(_DASHES + ":").strip()
    return text or None


def _join_wrapped(lines: list[str]) -> list[str]:
    """Join a label line with the following amount line when the cell wrapped between them."""
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        while (
            i + 1 < len(lines)
            and not line.startswith("*")
            and not _AMOUNT.search(line)
            and (
                line.endswith(tuple(_DASHES))
                or lines[i + 1].startswith(tuple(_DASHES))
                or _AMOUNT.match(lines[i + 1])
            )
        ):
            line = f"{line} {lines[i + 1]}"
            i += 1
        out.append(line)
        i += 1
    return out


def _parse_line(line: str, prev_label: str | None) -> list[FeeItem]:
    matches = list(_AMOUNT.finditer(line))
    items: list[FeeItem] = []
    for idx, m in enumerate(matches):
        before = line[matches[idx - 1].end() if idx else 0 : m.start()]
        after = line[m.end() : matches[idx + 1].start() if idx + 1 < len(matches) else len(line)]

        lo = _to_float(m.group(1))
        hi = _to_float(m.group(2)) if m.group(2) else lo

        qualifier = None
        pm = _PARENS.search(after)
        if pm:
            qualifier = pm.group(1).strip() or None
            after = after[: pm.start()] + after[pm.end() :]

        unit = note = None
        um = _UNIT.match(after)
        if um:
            word = um.group("unit").strip()
            if word.lower() == "fixed":
                note = "fixed"
            else:
                unit = f"per {word}"
            after = after[um.end() :]

        label = _clean_label(before)
        if label is None:
            label = _clean_label(after)
        if label is None and qualifier is not None:
            label = prev_label
        items.append(FeeItem(label, lo, hi, unit, qualifier, note))
        prev_label = label
    return items


def parse_fees(text: str | None) -> FeeParse:
    """Parse one fee cell. Never raises."""
    if text is None or _NOT_STATED.match(text):
        return FeeParse("not_stated", (), (), text)

    m = _NONE.match(text)
    if m and not _AMOUNT.search(text):
        rest = m.group("rest").strip()
        notes = tuple(n.strip() for n in _PARENS.findall(rest) if n.strip())
        if not notes and rest.strip(" ()"):
            notes = (rest.strip(),)
        return FeeParse("none", (), notes, text)

    lines = [ln.strip() for ln in text.replace("\r", "").split("\n")]
    lines = _join_wrapped([ln for ln in lines if ln])

    items: list[FeeItem] = []
    notes: list[str] = []
    has_free_text = False
    prev_label: str | None = None
    for line in lines:
        if line.startswith("*"):
            notes.append(line.strip("* ").strip())
        elif _AMOUNT.search(line):
            parsed = _parse_line(line, prev_label)
            items.extend(parsed)
            prev_label = parsed[-1].label
        elif not _NOT_STATED.match(line):
            has_free_text = True
            notes.append(line)

    if items:
        status: Status = "amounts"
    elif has_free_text:
        status = "text_only"
    else:
        status = "not_stated"
    return FeeParse(status, tuple(items), tuple(notes), text)
