"""Compare each service's stated TOTAL against the sum of its parsed step fees and times.

Report only: nothing is auto-corrected and the drafts are never modified
(docs/charter_data.md section 4).

Method
------
* Times: sum the *max* of each step's range, separately for days and for clock minutes
  (minutes + 60 x hours), and compare with the stated total's max on each axis. Days are not
  converted to minutes because ``day_type`` is unknown. A cell merged over several steps is
  counted once (the splitter keeps its value on the top-left step only). Steps with no stated
  time add nothing and are listed.
* Fees: sum the max of each step's fee items and compare with the stated total's max.
  Exceptions that follow the shape of the *stated total*: (1) qualifier totals such as
  ``P215 (company)`` are checked per qualifier (unqualified items plus that qualifier's items);
  (2) a total that lists several labelled tiers (e.g. cockfight categories) is compared item by
  item, since the tiers are alternatives, not addends. A per-unit item ("per copy") counts as
  one unit.
* When a stated total is a range and both endpoints can be produced by adding up some subset of
  the step fee items, a *hint* says the steps may list alternatives. It changes no verdict.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from citizengraph.parsing.durations import Duration
from citizengraph.parsing.fees import FeeItem, FeeParse
from citizengraph.parsing.splitter import ServiceDraft

Verdict = Literal["match", "mismatch", "not_comparable"]
_TOL = 0.005
_MAX_SUBSET_ITEMS = 16


@dataclass(frozen=True)
class CheckResult:
    verdict: Verdict
    stated: str
    derived: str
    details: tuple[str, ...] = ()
    hints: tuple[str, ...] = ()


@dataclass(frozen=True)
class ServiceCheck:
    draft_id: str
    name: str | None
    fee: CheckResult
    time: CheckResult

    @property
    def has_mismatch(self) -> bool:
        return "mismatch" in (self.fee.verdict, self.time.verdict)


# --------------------------------------------------------------------------- formatting


def money(value: float) -> str:
    return f"₱{value:,.2f}"


def _item_text(item: FeeItem) -> str:
    amount = (
        money(item.amount_max)
        if item.amount_min == item.amount_max
        else f"{money(item.amount_min)} - {money(item.amount_max)}"
    )
    parts = [item.label + ":" if item.label else "", amount]
    if item.unit:
        parts.append(item.unit)
    if item.qualifier:
        parts.append(f"({item.qualifier})")
    return " ".join(p for p in parts if p)


def _stated_fee_text(fee: FeeParse) -> str:
    if fee.status == "none":
        return "none"
    if fee.status == "not_stated":
        return "not stated"
    if fee.status == "text_only":
        return "; ".join(fee.notes) or "text only"
    return "; ".join(_item_text(i) for i in fee.items)


def _num(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def time_text(days: float, minutes: float, weeks: float = 0) -> str:
    parts = []
    if weeks:
        parts.append(f"{_num(weeks)} week{'s' if weeks != 1 else ''}")
    if days:
        parts.append(f"{_num(days)} day{'s' if days != 1 else ''}")
    if minutes or not parts:
        text = f"{_num(minutes)} min"
        if minutes >= 60 and float(minutes).is_integer():
            text += f" ({int(minutes) // 60} h {int(minutes) % 60} min)"
        parts.append(text)
    return ", ".join(parts)


# --------------------------------------------------------------------------- fees


def _reachable_sums(values: Sequence[float]) -> set[int]:
    sums = {0}
    for v in values:
        cents = round(v * 100)
        sums |= {s + cents for s in sums}
    return sums


def _range_hint(stated: FeeParse, items: Sequence[FeeItem]) -> tuple[str, ...]:
    if len(stated.items) != 1 or len(items) > _MAX_SUBSET_ITEMS:
        return ()
    total = stated.items[0]
    if total.amount_min == total.amount_max:
        return ()
    reachable = _reachable_sums([i.amount_max for i in items])
    if round(total.amount_min * 100) in reachable and round(total.amount_max * 100) in reachable:
        return (
            (
                "both ends of the stated range equal the sum of some subset of the step fees "
                "(a subset sum), so the steps may list alternative fees; confirm with the LGU"
            ),
        )
    return ()


def compare_fees(stated: FeeParse, steps: Sequence[tuple[int, FeeParse]]) -> CheckResult:
    """Compare a stated fee total with the parsed step fees. ``steps`` is (order, fees)."""
    step_items = [(order, item) for order, fees in steps for item in fees.items]
    items = [i for _, i in step_items]
    derived_sum = sum(i.amount_max for i in items)
    details: list[str] = []
    for order, fees in steps:
        if fees.status == "text_only":
            details.append(f"step {order} fee has no amount: {'; '.join(fees.notes)!r}")
    for order, item in step_items:
        if item.unit:
            details.append(f"step {order}: {_item_text(item)} counted as one unit")
    breakdown = [f"step {o}: {_item_text(i)}" for o, i in step_items]

    stated_text = _stated_fee_text(stated)
    derived_text = money(derived_sum) if items else "no amounts"

    if stated.status in ("not_stated", "text_only"):
        details.append("stated total fee is not a number, so nothing to compare")
        return CheckResult("not_comparable", stated_text, derived_text, tuple(details + breakdown))

    if stated.status == "none":
        verdict: Verdict = "match" if not items else "mismatch"
        if items:
            details.append("stated 'none' but steps charge: " + "; ".join(breakdown))
        return CheckResult(verdict, stated_text, derived_text, tuple(details))

    qualified = [i for i in stated.items if i.qualifier]
    if qualified:
        base = sum(i.amount_max for i in items if not i.qualifier)
        parts, ok = [], True
        stated_qualifiers = {i.qualifier.lower() for i in qualified if i.qualifier}
        for total in stated.items:
            q = total.qualifier.lower() if total.qualifier else None
            extra = sum(
                i.amount_max for i in items if i.qualifier and q and i.qualifier.lower() == q
            )
            derived_q = base + extra
            good = abs(derived_q - total.amount_max) <= _TOL
            ok &= good
            label = total.qualifier or "unqualified"
            parts.append(f"{label} {money(derived_q)}")
            details.append(
                f"{label}: stated {money(total.amount_max)}, steps {money(derived_q)}"
                f"{'' if good else f' (steps - stated = {derived_q - total.amount_max:+,.2f})'}"
            )
        for _, i in step_items:
            if i.qualifier and i.qualifier.lower() not in stated_qualifiers:
                details.append(f"step fee with qualifier not in the total: {_item_text(i)}")
                ok = False
        return CheckResult(
            "match" if ok else "mismatch", stated_text, "; ".join(parts), tuple(details + breakdown)
        )

    if len(stated.items) > 1:

        def key(i: FeeItem) -> tuple[str, float, float]:
            return ((i.label or "").lower(), i.amount_min, i.amount_max)

        shown = {key(i): i.label or "(no label)" for i in [*stated.items, *items]}
        want, have = Counter(map(key, stated.items)), Counter(map(key, items))
        missing = want - have
        extra = have - want
        for k in sorted(missing):
            details.append(f"in the total but not in the steps: {shown[k]} {money(k[2])}")
        for k in sorted(extra):
            details.append(f"in the steps but not in the total: {shown[k]} {money(k[2])}")
        details.append("total lists several tiers; compared item by item, not summed")
        verdict = "match" if not missing and not extra else "mismatch"
        derived_tiers = "; ".join(_item_text(i) for i in items) or "no amounts"
        return CheckResult(verdict, stated_text, derived_tiers, tuple(details))

    total = stated.items[0]
    delta = derived_sum - total.amount_max
    good = abs(delta) <= _TOL
    if not good:
        details.append(f"steps - stated = {delta:+,.2f}")
    return CheckResult(
        "match" if good else "mismatch",
        stated_text,
        derived_text,
        tuple(details + ([] if good else breakdown)),
        () if good else _range_hint(stated, items),
    )


# --------------------------------------------------------------------------- times


def compare_times(stated: Duration, steps: Sequence[tuple[int, Duration]]) -> CheckResult:
    """Compare a stated time total with the parsed step times. ``steps`` is (order, time).

    Weeks, days and clock minutes are three separate axes; none is converted into another.
    """
    details: list[str] = []
    stated_text = (
        time_text(stated.days_max or 0, stated.clock_minutes_max or 0, stated.weeks_max or 0)
        if stated.stated
        else "not stated"
    )
    unparsed = [o for o, d in steps if d.status == "unparsed"]
    ambiguous = [o for o, d in steps if d.status == "ambiguous"]
    unstated = [o for o, d in steps if d.status == "not_stated"]
    weeks = sum(d.weeks_max or 0 for _, d in steps if d.stated)
    days = sum(d.days_max or 0 for _, d in steps if d.stated)
    clock = sum(d.clock_minutes_max or 0 for _, d in steps if d.stated)
    derived_text = time_text(days, clock, weeks)

    if unstated:
        details.append("steps with no stated time (add nothing): " + ", ".join(map(str, unstated)))
    for note in stated.normalizations:
        details.append(f"stated total {stated.raw!r} was read with a typo fix ({note})")
    for order, d in steps:
        for note in d.normalizations:
            details.append(f"step {order} time {d.raw!r} was read with a typo fix ({note})")
    if stated.status != "stated":
        details.append(
            {
                "unparsed": "stated total time could not be parsed",
                "ambiguous": "stated total time needs review (kept raw)",
            }.get(stated.status, "stated total time is not stated")
        )
        return CheckResult("not_comparable", stated_text, derived_text, tuple(details))
    if unparsed or ambiguous:
        if unparsed:
            details.append("steps whose time could not be parsed: " + ", ".join(map(str, unparsed)))
        for order, d in steps:
            if d.status == "ambiguous":
                details.append(f"step {order} time {d.raw!r} needs review (kept raw): {d.review}")
        return CheckResult("not_comparable", stated_text, derived_text, tuple(details))

    d_weeks = weeks - (stated.weeks_max or 0)
    d_days = days - (stated.days_max or 0)
    d_clock = clock - (stated.clock_minutes_max or 0)
    if abs(d_weeks) > _TOL:
        details.append(f"weeks: steps - stated = {d_weeks:+g}")
    if abs(d_days) > _TOL:
        details.append(f"days: steps - stated = {d_days:+g}")
    if abs(d_clock) > _TOL:
        details.append(f"minutes: steps - stated = {d_clock:+g}")
    good = abs(d_weeks) <= _TOL and abs(d_days) <= _TOL and abs(d_clock) <= _TOL
    return CheckResult("match" if good else "mismatch", stated_text, derived_text, tuple(details))


# --------------------------------------------------------------------------- per service


def check_service(draft: ServiceDraft) -> ServiceCheck:
    if draft.total is None:
        missing = CheckResult("not_comparable", "no TOTAL row", "", ("no TOTAL row found",))
        return ServiceCheck(draft.draft_id, draft.name, missing, missing)
    fee = compare_fees(draft.total.fee, [(s.order, s.fees) for s in draft.steps])
    time = compare_times(draft.total.time, [(s.order, s.time) for s in draft.steps])
    return ServiceCheck(draft.draft_id, draft.name, fee, time)


# --------------------------------------------------------------------------- reports

_LABEL = {"match": "match", "mismatch": "MISMATCH", "not_comparable": "not comparable"}


def _cell(text: str) -> str:
    return text.replace("\n", " ").replace("|", "\\|")


def _step_table(draft: ServiceDraft) -> list[str]:
    lines = ["| # | Label | Agency action | Fees | Time |", "|---|---|---|---|---|"]
    for s in draft.steps:
        fee = "; ".join(_item_text(i) for i in s.fees.items) or (
            "none" if s.fees.status == "none" else "—"
        )
        if s.time.stated:
            time = time_text(
                s.time.days_max or 0, s.time.clock_minutes_max or 0, s.time.weeks_max or 0
            )
            if s.time.minutes_min != s.time.minutes_max:
                time += " (max of range)"
            if s.time_span > 1:
                time += f" (merged over {s.time_span} steps, counted once)"
        elif s.time.status in ("ambiguous", "unparsed"):
            time = f"needs review: {s.time.raw!r}"
        elif s.time_shared_from:
            time = f"(shared with step {s.time_shared_from})"
        else:
            time = "—"
        action = (s.agency_action or "").split("\n")[0][:70]
        lines.append(f"| {s.order} | {s.label or ''} | {_cell(action)} | {_cell(fee)} | {time} |")
    return lines


def build_report(drafts: Sequence[ServiceDraft]) -> str:
    """Markdown validation report for all services. Deterministic (no timestamps)."""
    checks = [(d, check_service(d)) for d in drafts]
    out = [
        "# Validation report: stated TOTAL vs sum of parsed steps",
        "",
        (
            "Generated by `python -m citizengraph.parsing`. **Nothing in this report is "
            "auto-corrected**; the drafts and `data/raw/` are untouched. Each mismatch needs a human "
            "decision (and, where the charter itself may be wrong, confirmation from the LGU)."
        ),
        "",
        "How the comparison works (see `src/citizengraph/parsing/validate.py`):",
        "",
        (
            "- Times use the *max* of each range, with days and clock minutes compared separately "
            "(day type is unknown, so days are never converted to minutes)."
        ),
        "- A time or fee cell merged over several steps is counted once.",
        "- Steps with no stated time add nothing; they are listed under the service.",
        '- A per-unit fee ("per copy") counts as one unit.',
        (
            "- A total that lists labelled tiers (cockfight) or qualifiers (company / individual) is "
            "compared per tier or per qualifier instead of summed across all items."
        ),
        (
            "- A *hint* is printed when a stated range could be explained by alternative fees; it "
            "does not change the verdict."
        ),
        "",
        "## Summary",
        "",
        "| Service | Name | Fees | Time |",
        "|---|---|---|---|",
    ]
    for d, c in checks:
        out.append(
            f"| {d.draft_id} | {_cell((d.name or '')[:60])} | {_LABEL[c.fee.verdict]} | "
            f"{_LABEL[c.time.verdict]} |"
        )
    n_fee = sum(c.fee.verdict == "mismatch" for _, c in checks)
    n_time = sum(c.time.verdict == "mismatch" for _, c in checks)
    n_svc = sum(c.has_mismatch for _, c in checks)
    out += [
        "",
        (
            f"{len(checks)} services checked. Fee mismatches: {n_fee}. Time mismatches: {n_time}. "
            f"Services with at least one mismatch: {n_svc}."
        ),
        "",
        "## Mismatches",
    ]
    for d, c in checks:
        if not c.has_mismatch:
            continue
        out += ["", f"### {d.draft_id}: {d.name}", ""]
        for title, r in (("Fees", c.fee), ("Time", c.time)):
            out.append(
                f"- **{title}: {_LABEL[r.verdict]}.** Stated: {_cell(r.stated)}. "
                f"Sum of steps: {_cell(r.derived)}."
            )
            out += [f"  - {_cell(x)}" for x in r.details if r.verdict == "mismatch"]
            out += [f"  - hint: {_cell(h)}" for h in r.hints]
        out += ["", *_step_table(d)]

    other = [
        (d, c)
        for d, c in checks
        if not c.has_mismatch and "not_comparable" in (c.fee.verdict, c.time.verdict)
    ]
    if other:
        out += ["", "## Not comparable", ""]
        for d, c in other:
            for title, r in (("Fees", c.fee), ("Time", c.time)):
                if r.verdict == "not_comparable":
                    out.append(
                        f"- {d.draft_id} ({title}): stated {_cell(r.stated)}; steps {_cell(r.derived)}. "
                        + " ".join(_cell(x) for x in r.details)
                    )
    return "\n".join(out).rstrip() + "\n"


def build_flags_report(drafts: Sequence[ServiceDraft]) -> str:
    """Markdown list of everything the splitter could not resolve or had to flag."""
    counts: Counter[str] = Counter()
    for d in drafts:
        counts.update(f["code"] for f in d.flags)
    out = [
        "# Parse flags",
        "",
        (
            "Generated by `python -m citizengraph.parsing`. These are places where the sheet is "
            "blank, merged, or not a number. Nothing was guessed: values are left null or raw. Fold "
            "anything that needs the LGU into `docs/charter_data.md` section 5."
        ),
        "",
        "| Flag | Count | Meaning |",
        "|---|---|---|",
    ]
    meaning = {
        "who_may_avail_blank": "Who may avail is blank in the sheet; stored as null.",
        "where_to_secure_missing": "Requirement has no 'where to secure'; stored as null.",
        "where_to_secure_shared": "'Where to secure' is a merged cell shared with another row; value copied and flagged.",
        "time_not_stated": "Step has no processing time ('- - -' or blank).",
        "time_unparsed": "Step time is text the duration parser does not understand; kept raw.",
        "fee_text_only": "Step fee is text with no amount (e.g. 'As determined by the CSWMO').",
        "person_missing": "Step has no person responsible.",
        "merged_cell_shared": "Step's fee/time cell is merged with a step above; value counted once.",
        "orphan_where_to_secure": "'Where to secure' text on a row with no requirement.",
        "total_missing": "No TOTAL row found.",
        "total_time_unparsed": "Stated total time is not understood.",
        "total_fee_text_only": "Stated total fee has no amount.",
        "time_ambiguous": "Step time is a decimal such as '1.15 min'; kept raw, not converted.",
        "total_time_ambiguous": "Stated total time is a decimal; kept raw, not converted.",
        "time_typo_normalized": "Step time contains a known unit typo that was read as its unit.",
        "total_time_typo_normalized": "Stated total time contains a known unit typo that was "
        "read as its unit (e.g. 'dsys' as days).",
        "fee_no_currency_sign": "Step fee is a bare number with no peso sign; read as an amount.",
        "total_fee_no_currency_sign": "Stated total fee has no peso sign; read as an amount.",
        "no_requirements_listed": "The checklist says N/A; stored as no requirements.",
        "where_to_secure_na": "'Where to secure' says N/A; stored as null.",
        "requirement_fragment_glued": "A labelled requirement wrapped onto the next row; the "
        "rows were joined.",
        "orphan_row_glued": "A row with no fee or time continues the step above (wrapped text); "
        "appended to it.",
        "possible_split_step": "A step with no fee or time is followed by a row with no label or "
        "person; possibly one step split over two rows. Kept as two.",
    }
    for code, n in sorted(counts.items()):
        out.append(f"| `{code}` | {n} | {meaning.get(code, '')} |")
    for d in drafts:
        out += ["", f"## {d.draft_id}: {d.name}", ""]
        if not d.flags:
            out.append("No flags.")
        out += [f"- `{f['code']}`: {_cell(f['message'])}" for f in d.flags]
    return "\n".join(out).rstrip() + "\n"
