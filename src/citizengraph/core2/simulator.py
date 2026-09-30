"""Deterministic generator of SIMULATED applications for the 26 curated services.

Nothing here is real citizen data: reference codes are fake (``CG-SIM-0001``), the workflow store
is separate from the charter graph, and the only inputs are the seed's step times, a seed number
and a calendar. The same seed always produces the same store.

Situations (the base of each application) and injections (modifiers):

* ``on_time``, ``minor_delay``, ``over_charter``: time in the current step against the charter.
* ``overdue_statutory``: current step fine, but an earlier step took days, so the LGU working days
  since receipt exceed the (unverified) cap.
* ``suspension_pause``: as above, but declared suspension days bring the count back to the cap.
* ``external_waiting`` / ``external_over``: waiting at an external agency's step.
* ``completed``: every step finished.
* injections ``missing_current``, ``missing_earlier`` (timestamps dropped), ``role_unavailable``
  (the responsible role is marked absent on the as-of day), ``extra_suspension`` (a declared
  suspension day that does NOT rescue the application).

Each application carries a ``Truth``: the outcome the injection was built to produce. It follows
from how the data were made, not from any agent, so it is an independent check on the tools and on
the policies.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from citizengraph.core2.calendar import PHT, Calendar
from citizengraph.core2.config import Core2Config, StatutoryCaps, load_statutory_caps
from citizengraph.core2.models import Application, StepEntry
from citizengraph.core2.sla import workflow_state
from citizengraph.core2.store import WorkflowStore
from citizengraph.graph import InMemoryGraph
from citizengraph.graph.ids import clean_name
from citizengraph.graph.models import Step

SITUATIONS = (
    "on_time",
    "minor_delay",
    "over_charter",
    "overdue_statutory",
    "suspension_pause",
    "external_waiting",
    "external_over",
    "completed",
)
INJECTIONS = ("missing_current", "missing_earlier", "role_unavailable", "extra_suspension")
SUSPENSION_REASON = "SIMULATED work suspension (fixture)"


class SimulationError(ValueError):
    """The requested situation cannot be built for that service or step."""


@dataclass(frozen=True)
class AppSpec:
    service_id: str
    situation: str = "on_time"
    at_step: int | None = None  # order of the current step; None = the simulator picks one
    inject: tuple[str, ...] = ()
    citizen_ref: str | None = None
    app_id: str | None = None
    ref: str | None = None


@dataclass(frozen=True)
class Truth:
    status: str
    alerts: frozenset[str]
    reasons: frozenset[str] = frozenset()
    situation: str = "on_time"
    inject: tuple[str, ...] = ()


@dataclass
class Simulated:
    store: WorkflowStore
    calendar: Calendar
    as_of: datetime
    day_types: dict[str, str] = field(default_factory=dict)
    truth: dict[str, Truth] = field(default_factory=dict)


def _half(x: float) -> float:
    return max(0.5, round(x * 2) / 2)


def _is_clock(step: Step) -> bool:
    return step.duration.status == "stated" and step.duration.unit in ("minute", "hour")


def _is_plain(step: Step) -> bool:
    """A step that can sit in the past of a same-day timeline: clock time or no stated time."""
    return _is_clock(step) or step.duration.status != "stated"


def _allowed_minutes(step: Step) -> float:
    d = step.duration
    assert d.value_max is not None
    return d.value_max * (60.0 if d.unit == "hour" else 1.0)


class Simulator:
    def __init__(
        self,
        graph: InMemoryGraph,
        seed: int = 0,
        config: Core2Config | None = None,
        caps: StatutoryCaps | None = None,
    ) -> None:
        self.graph = graph
        self.seed = seed
        self.config = config or Core2Config()
        self.caps = caps or load_statutory_caps()

    # -- eligibility ---------------------------------------------------------------------------

    def _eligible(self, spec: AppSpec) -> list[int]:
        """0-based indexes of steps that can be the current step for this spec."""
        steps = self.graph.steps(spec.service_id)
        sit = spec.situation
        out: list[int] = []
        for i, st in enumerate(steps):
            if not all(_is_plain(s) for s in steps[:i]):
                break  # a day-based step in the past would push the timeline over the days
            if sit in ("on_time", "minor_delay", "over_charter"):
                ok = _is_clock(st) and not st.external_agency
            elif sit == "external_waiting":
                ok = bool(st.external_agency)
            elif sit == "external_over":
                ok = bool(st.external_agency) and _is_clock(st)
            elif sit in ("overdue_statutory", "suspension_pause"):
                ok = i >= 1 and _is_clock(st) and not st.external_agency
                ok = ok and not steps[i - 1].external_agency and _is_clock(steps[i - 1])
            elif sit == "completed":
                ok = i == len(steps) - 1 and _is_plain(st)
            else:
                raise SimulationError(f"unknown situation {sit!r}")
            if "missing_earlier" in spec.inject and not any(
                not s.external_agency for s in steps[:i]
            ):
                ok = False  # needs an earlier non-external step to lose a timestamp
            if "role_unavailable" in spec.inject and st.role is None:
                ok = False
            if "missing_current" in spec.inject and sit == "completed":
                ok = False
            out.append(i) if ok else None
        return out

    def can_host(self, spec: AppSpec) -> bool:
        return bool(self._eligible(spec))

    # -- building ------------------------------------------------------------------------------

    def build(
        self,
        specs: Sequence[AppSpec],
        as_of: datetime,
        calendar: Calendar | None = None,
        day_types: dict[str, str] | None = None,
    ) -> Simulated:
        rng = random.Random(self.seed)
        base = calendar or Calendar(weekend=frozenset(self.config.weekend_days))
        for spec in specs:
            for inj in spec.inject:
                if inj not in INJECTIONS:
                    raise SimulationError(f"unknown injection {inj!r}")
            if spec.situation not in SITUATIONS:
                raise SimulationError(f"unknown situation {spec.situation!r}")
        cal = base.with_suspensions(self._suspension_days(specs, as_of, base))
        store = WorkflowStore()
        truth: dict[str, Truth] = {}
        roles: dict[str, str | None] = {}
        for n, spec in enumerate(specs, start=1):
            app, tr = self._build_one(spec, n, as_of, cal, store, rng)
            store.add(app)
            truth[app.app_id] = tr
            roles[app.app_id] = self._current_role(app, tr)
        # The roster is shared: a role marked absent for one application is absent for every
        # application waiting on that role, so settle the escalations once all are built.
        for app_id, tr in list(truth.items()):
            role = roles[app_id]
            if tr.status == "delayed" and role and store.absence(role, as_of):
                truth[app_id] = Truth(
                    tr.status,
                    tr.alerts | {"department_head_escalation"},
                    tr.reasons | {"role_unavailable"},
                    tr.situation,
                    tr.inject,
                )
        return Simulated(store, cal, as_of, dict(day_types or {}), truth)

    def _current_role(self, app: Application, truth: Truth) -> str | None:
        cur = workflow_state(app, self.graph).current
        return clean_name(cur.role) if cur and cur.role else None

    def _suspension_days(
        self, specs: Sequence[AppSpec], as_of: datetime, base: Calendar
    ) -> dict[date, str]:
        need = 0
        for spec in specs:
            if spec.situation == "suspension_pause":
                need = max(need, 2)
            if "extra_suspension" in spec.inject:
                need = max(need, 1)
        days: dict[date, str] = {}
        d = as_of.date()
        while len(days) < need:
            d -= timedelta(days=1)
            if base.is_working_day(d):
                days[d] = SUSPENSION_REASON
        return days

    def _build_one(
        self,
        spec: AppSpec,
        n: int,
        as_of: datetime,
        cal: Calendar,
        store: WorkflowStore,
        rng: random.Random,
    ) -> tuple[Application, Truth]:
        graph = self.graph
        try:
            graph.service(spec.service_id)
        except KeyError:
            raise SimulationError(f"unknown service {spec.service_id!r}") from None
        steps = graph.steps(spec.service_id)
        eligible = self._eligible(spec)
        if spec.at_step is not None:
            if spec.at_step - 1 not in eligible:
                raise SimulationError(
                    f"{spec.service_id} step {spec.at_step} cannot host {spec.situation} "
                    f"with {list(spec.inject)}"
                )
            cur = spec.at_step - 1
        elif eligible:
            cur = rng.choice(eligible)
        else:
            raise SimulationError(f"{spec.service_id} has no step that can host {spec.situation}")
        sit = spec.situation
        ratio = self.config.minor_delay_ratio
        current = steps[cur]

        # minutes spent in each finished step
        def spent(st: Step) -> float:
            d = st.duration
            if d.status == "stated" and d.unit in ("minute", "hour"):
                unit = 60.0 if d.unit == "hour" else 1.0
                assert d.value_min is not None and d.value_max is not None
                return _half(rng.uniform(d.value_min * unit, d.value_max * unit))
            return float(rng.randint(1, 5))

        # minutes in the current step
        elapsed = 0.0
        if sit == "completed":
            elapsed = 0.0
        elif current.external_agency and not _is_clock(current):
            elapsed = float(rng.randint(5, 120))
        else:
            allowed = _allowed_minutes(current)
            if sit in ("on_time", "overdue_statutory", "suspension_pause", "external_waiting"):
                elapsed = _half(allowed * rng.uniform(0.3, 1.0))
            elif sit == "minor_delay":
                elapsed = _half(allowed * rng.uniform(1.15, 1.35))
                if not allowed < elapsed <= allowed * ratio:
                    elapsed = allowed * ((1 + ratio) / 2)
            else:  # over_charter, external_over
                elapsed = _half(allowed * rng.uniform(ratio + 0.3, ratio + 2.5))
            elapsed = min(elapsed, allowed) if sit == "external_waiting" else elapsed

        entries: list[StepEntry] = []
        if sit == "completed":
            end = as_of - timedelta(minutes=rng.randint(5, 60))
            spans = [spent(st) for st in steps]
            t = end - timedelta(minutes=sum(spans))
            submitted = t
            for st, m in zip(steps, spans, strict=True):
                entries.append(
                    StepEntry(step_id=st.id, entered_at=t, completed_at=t + timedelta(minutes=m))
                )
                t += timedelta(minutes=m)
        else:
            cur_entered = as_of - timedelta(minutes=elapsed)
            if sit in ("overdue_statutory", "suspension_pause"):
                cap = self.caps.working_days[self.graph.service(spec.service_id).classification]
                k = cap + 1 + rng.randint(0, 1) if sit == "overdue_statutory" else cap
                submitted = datetime.combine(cal.subtract_working_days(as_of, k), time(8, 30), PHT)
                t = submitted
                for st in steps[: cur - 1]:
                    m = spent(st)
                    entries.append(
                        StepEntry(
                            step_id=st.id, entered_at=t, completed_at=t + timedelta(minutes=m)
                        )
                    )
                    t += timedelta(minutes=m)
                entries.append(
                    StepEntry(step_id=steps[cur - 1].id, entered_at=t, completed_at=cur_entered)
                )
            else:
                t = cur_entered
                back: list[StepEntry] = []
                for st in reversed(steps[:cur]):
                    m = spent(st)
                    back.append(
                        StepEntry(
                            step_id=st.id, entered_at=t - timedelta(minutes=m), completed_at=t
                        )
                    )
                    t -= timedelta(minutes=m)
                entries.extend(reversed(back))
                submitted = t
            entries.append(StepEntry(step_id=current.id, entered_at=cur_entered))

        reasons: set[str] = set()
        alerts: set[str] = set()
        status = {
            "on_time": "on_track",
            "minor_delay": "minor_delay",
            "over_charter": "delayed",
            "overdue_statutory": "overdue_statutory",
            "suspension_pause": "paused_by_suspension",
            "external_waiting": "external_waiting",
            "external_over": "external_waiting",
            "completed": "completed",
        }[sit]
        if sit == "over_charter":
            alerts.add("citizen_delay_notice")
        elif sit == "overdue_statutory":
            alerts |= {"citizen_delay_notice", "department_head_escalation"}
        elif sit == "external_over":
            alerts.add("external_wait_notice")
        elif sit == "suspension_pause":
            reasons.add("suspension_days_excluded")

        if "missing_earlier" in spec.inject:
            # Never an external step: losing its times would make the statutory count
            # undecidable, which is a different situation from the one being built.
            pool = [
                k
                for k in range(cur if sit != "completed" else len(steps) - 1)
                if not steps[k].external_agency
            ]
            j = rng.choice(pool)
            e = entries[j]
            drop_entered = j >= 1 and rng.random() < 0.5
            entries[j] = StepEntry(
                step_id=e.step_id,
                entered_at=None if drop_entered else e.entered_at,
                completed_at=e.completed_at if drop_entered else None,
            )
            alerts.add("missing_data_flag")
            reasons.add("missing_timestamp_earlier_step")
        if "missing_current" in spec.inject:
            entries = [e for e in entries if e.step_id != current.id]
            status, alerts, reasons = (
                "cannot_determine",
                {"missing_data_flag"},
                {"missing_timestamp"},
            )
        if "role_unavailable" in spec.inject:
            store.set_absent(clean_name(current.role or ""), as_of, "absent (simulated)")
            if status == "delayed":
                alerts.add("department_head_escalation")
                reasons.add("role_unavailable")

        app = Application(
            app_id=spec.app_id or f"A{n:04d}",
            ref=spec.ref or f"CG-SIM-{n:04d}",
            citizen_ref=spec.citizen_ref or f"CIT-{n:04d}",
            service_id=spec.service_id,
            submitted_at=submitted,
            entries=[e for e in entries if e.entered_at or e.completed_at],
        )
        return app, Truth(status, frozenset(alerts), frozenset(reasons), sit, spec.inject)

    # -- populations ---------------------------------------------------------------------------

    def population(self, n: int, as_of: datetime, calendar: Calendar | None = None) -> Simulated:
        """``n`` applications across all curated services, a mix of every situation."""
        rng = random.Random(f"pop-{self.seed}")
        situations = [
            ("on_time", 25),
            ("minor_delay", 10),
            ("over_charter", 15),
            ("overdue_statutory", 8),
            ("suspension_pause", 5),
            ("external_waiting", 6),
            ("external_over", 4),
            ("completed", 8),
        ]
        names, weights = zip(*situations, strict=True)
        service_ids = [s.id for s in self.graph.services()]
        specs: list[AppSpec] = []
        citizen = 0
        while len(specs) < n:
            situation = rng.choices(names, weights)[0]
            inject: list[str] = []
            if rng.random() < 0.08:
                inject.append("missing_current")
            elif rng.random() < 0.10:
                inject.append("missing_earlier")
            if situation == "over_charter" and rng.random() < 0.3:
                inject.append("role_unavailable")
            if rng.random() < 0.05:
                inject.append("extra_suspension")
            candidates = list(service_ids)
            rng.shuffle(candidates)
            for service_id in candidates:
                spec = AppSpec(service_id, situation, inject=tuple(inject))
                if self.can_host(spec):
                    if not specs or rng.random() > 0.25:
                        citizen += 1
                    specs.append(
                        AppSpec(
                            service_id,
                            situation,
                            inject=tuple(inject),
                            citizen_ref=f"CIT-{citizen:04d}",
                        )
                    )
                    break
        return self.build(specs, as_of, calendar)
