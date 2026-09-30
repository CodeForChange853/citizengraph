"""Exact SLA logic. Plain code: every number and comparison here is deterministic.

Two clocks (docs/specs.md section 3):

* charter step time, from the seed (``basis = "charter_step_time"``);
* the statutory working-day cap, from ``config/sla.yaml`` (``basis = "statutory_cap_unverified"``:
  the limits are NOT verified against RA 11032 and must never be shown as law).

Nothing is guessed. A day-based charter time with day type "unknown" (and no explicit override)
is ``not_comparable``; so is a step with no stated time or a missing timestamp.
Steps marked ``external_agency`` are not LGU time: their days are removed from the statutory
count, and callers report them as external waiting.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime

from citizengraph.core2.calendar import Calendar, working_days_elapsed
from citizengraph.core2.config import CHARTER_BASIS, STATUTORY_BASIS, Core2Config, StatutoryCaps
from citizengraph.core2.models import Application, StepEntry
from citizengraph.graph import InMemoryGraph
from citizengraph.graph.models import Step

RANK = {"within": 0, "minor_over": 1, "over": 2}
_UNIT_MINUTES = {"minute": 1.0, "hour": 60.0}


# ---------------------------------------------------------------------------------------- allowance


@dataclass(frozen=True)
class Allowance:
    comparable: bool
    reason: str | None  # why not comparable
    kind: str | None  # "clock" | "working_days" | "calendar_days"
    unit: str | None
    value_min: float | None
    value_max: float | None
    day_type: str
    allowed_minutes: float | None = None
    allowed_days: float | None = None


def resolve_day_type(step: Step, service_id: str, overrides: dict[str, str]) -> str:
    """Explicit override (step id first, then service id) or the charter's own day type."""
    return overrides.get(step.id) or overrides.get(service_id) or step.duration.day_type


def allowance(step: Step, day_type: str, weekend_len: int = 2) -> Allowance:
    d = step.duration
    if d.status != "stated" or d.unit is None or d.value_max is None:
        return Allowance(False, "charter_time_not_stated", None, None, None, None, day_type)
    common = {"unit": d.unit, "value_min": d.value_min, "value_max": d.value_max}
    if d.unit in _UNIT_MINUTES:
        return Allowance(
            True, None, "clock", day_type=day_type, **common,
            allowed_minutes=d.value_max * _UNIT_MINUTES[d.unit],
        )  # fmt: skip
    if day_type not in ("working", "calendar"):
        return Allowance(False, "day_type_unknown", None, common["unit"], d.value_min,
                         d.value_max, day_type)  # fmt: skip
    days = (
        d.value_max
        if d.unit == "day"
        else d.value_max * (7 if day_type == "calendar" else 7 - weekend_len)
    )
    return Allowance(
        True, None, "working_days" if day_type == "working" else "calendar_days",
        day_type=day_type, **common, allowed_days=float(days),
    )  # fmt: skip


# ------------------------------------------------------------------------------------ workflow state


@dataclass(frozen=True)
class Issue:
    step_id: str
    problem: str  # missing_entered_at | missing_completed_at | completed_before_entered


@dataclass(frozen=True)
class WorkflowState:
    steps: list[Step]
    current: Step | None
    current_entry: StepEntry | None
    complete: bool
    steps_done: int
    issues: list[Issue] = field(default_factory=list)


def workflow_state(app: Application, graph: InMemoryGraph) -> WorkflowState:
    steps = graph.steps(app.service_id)
    entries = [app.entry(st.id) for st in steps]

    def touched(e: StepEntry | None) -> bool:
        return e is not None and (e.entered_at is not None or e.completed_at is not None)

    last = max((i for i, e in enumerate(entries) if touched(e)), default=-1)
    issues: list[Issue] = []
    for i, (st, e) in enumerate(zip(steps, entries, strict=True)):
        if i > last:
            break
        entered = e.entered_at if e else None
        done = e.completed_at if e else None
        if entered is None and (done is not None or i < last):
            issues.append(Issue(st.id, "missing_entered_at"))
        if i < last and done is None:
            issues.append(Issue(st.id, "missing_completed_at"))
        if entered is not None and done is not None and done < entered:
            issues.append(Issue(st.id, "completed_before_entered"))

    frontier = entries[last] if last >= 0 else None
    if last >= 0 and frontier is not None and frontier.completed_at is None:
        cur_idx: int | None = last
    elif last == len(steps) - 1:
        cur_idx = None
    else:
        cur_idx = last + 1
        issues.append(Issue(steps[cur_idx].id, "missing_entered_at"))
    complete = cur_idx is None
    done_count = sum(1 for e in entries if e is not None and e.completed_at is not None)
    return WorkflowState(
        steps=steps,
        current=None if cur_idx is None else steps[cur_idx],
        current_entry=None if cur_idx is None else entries[cur_idx],
        complete=complete,
        steps_done=done_count,
        issues=issues,
    )


# ------------------------------------------------------------------------------------- charter check


@dataclass(frozen=True)
class StepCheck:
    step_id: str
    verdict: str  # within | minor_over | over | not_comparable
    reason: str | None
    kind: str | None
    allowed: float | None  # in minutes (clock) or days
    measured: float | None  # same unit as allowed
    elapsed_min: float | None
    entered_at: datetime | None
    end_at: datetime | None
    suspension_effect: bool = False  # over/minor only because suspension days were not excluded
    suspension_days: int = 0  # declared suspension days inside the interval
    basis: str = CHARTER_BASIS

    def to_dict(self) -> dict:
        return asdict(self)


def _verdict(measured: float, allowed: float, ratio: float) -> str:
    if measured <= allowed:
        return "within"
    return "minor_over" if measured <= allowed * ratio else "over"


def _suspension_days_between(a: datetime, b: datetime, cal: Calendar) -> int:
    return sum(
        1 for d in cal.suspensions if a.date() < d <= b.date() and d.weekday() not in cal.weekend
    )


def check_step(
    step: Step,
    entry: StepEntry | None,
    as_of: datetime,
    *,
    service_id: str,
    calendar: Calendar,
    day_types: dict[str, str],
    config: Core2Config,
) -> StepCheck:
    """Compare the time an application spent in ``step`` with the charter time.

    An open step is measured up to ``as_of``; a finished one from entered to completed.
    """
    dtype = resolve_day_type(step, service_id, {**config.day_type_overrides, **day_types})
    allow = allowance(step, dtype, weekend_len=len(calendar.weekend))
    entered = entry.entered_at if entry else None
    end = (entry.completed_at if entry and entry.completed_at else as_of) if entry else as_of

    def blocked(reason: str) -> StepCheck:
        return StepCheck(step.id, "not_comparable", reason, allow.kind, None, None, None,
                         entered, end if entered else None)  # fmt: skip

    if entered is None:
        return blocked("missing_timestamp")
    if end < entered:
        return blocked("timestamps_out_of_order")
    if not allow.comparable:
        return blocked(allow.reason or "not_comparable")
    elapsed_min = round((end - entered).total_seconds() / 60.0, 2)
    ratio = config.minor_delay_ratio
    if allow.kind == "clock":
        assert allow.allowed_minutes is not None
        return StepCheck(step.id, _verdict(elapsed_min, allow.allowed_minutes, ratio), None,
                         "clock", allow.allowed_minutes, elapsed_min, elapsed_min, entered, end)  # fmt: skip
    assert allow.allowed_days is not None
    if allow.kind == "calendar_days":
        measured = round(elapsed_min / 1440.0, 2)
        return StepCheck(step.id, _verdict(measured, allow.allowed_days, ratio), None,
                         "calendar_days", allow.allowed_days, measured, elapsed_min, entered, end)  # fmt: skip
    days = working_days_elapsed(entered, end, calendar)
    days_free = working_days_elapsed(entered, end, calendar.without_suspensions())
    verdict = _verdict(days, allow.allowed_days, ratio)
    verdict_free = _verdict(days_free, allow.allowed_days, ratio)
    return StepCheck(
        step.id, verdict, None, "working_days", allow.allowed_days, float(days), elapsed_min,
        entered, end, suspension_effect=RANK[verdict_free] > RANK[verdict],
        suspension_days=_suspension_days_between(entered, end, calendar),
    )  # fmt: skip


# ----------------------------------------------------------------------------------- statutory check


@dataclass(frozen=True)
class StatutoryCheck:
    verdict: str  # within | over | not_comparable
    reason: str | None
    cap: int | None
    elapsed_working_days: int | None  # LGU working days: total minus external steps
    total_working_days: int | None
    external_days_excluded: int
    suspension_effect: bool
    basis: str = STATUTORY_BASIS

    def to_dict(self) -> dict:
        return asdict(self)


def check_statutory(
    app: Application,
    graph: InMemoryGraph,
    as_of: datetime,
    *,
    calendar: Calendar,
    caps: StatutoryCaps,
    config: Core2Config,
) -> StatutoryCheck:
    """Working days from receipt against the configured cap. UNVERIFIED against RA 11032."""
    service = graph.service(app.service_id)
    state = workflow_state(app, graph)
    cap = caps.working_days.get(service.classification)

    def blocked(reason: str, total: int | None = None) -> StatutoryCheck:
        return StatutoryCheck("not_comparable", reason, cap, None, total, 0, False, caps.basis)

    if cap is None:
        return blocked("cap_not_configured")
    for st in state.steps:
        e = app.entry(st.id)
        if st.id in config.posting_step_ids and e is not None and e.entered_at is not None:
            return blocked("posting_period_treatment_unverified")

    last_done = max((e.completed_at for e in app.entries if e.completed_at), default=None)
    end = last_done if state.complete and last_done else as_of
    if end < app.submitted_at:
        return blocked("timestamps_out_of_order")

    def lgu_days(cal: Calendar) -> tuple[int, int] | None:
        total = working_days_elapsed(app.submitted_at, end, cal)
        external = 0
        for st in state.steps:
            e = app.entry(st.id)
            if not st.external_agency or e is None or e.entered_at is None:
                continue
            exit_at = e.completed_at or (as_of if st is state.current else None)
            if exit_at is None:
                return None
            external += working_days_elapsed(e.entered_at, min(exit_at, end), cal)
        return max(total - external, 0), external

    with_susp = lgu_days(calendar)
    if with_susp is None:
        return blocked("missing_timestamp")
    days, external = with_susp
    total = working_days_elapsed(app.submitted_at, end, calendar)
    free = lgu_days(calendar.without_suspensions())
    verdict = "over" if days > cap else "within"
    effect = free is not None and free[0] > cap and days <= cap
    return StatutoryCheck(verdict, None, cap, days, total, external, effect, caps.basis)
