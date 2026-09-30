"""Shared builders for the Core 2 tests. All data is simulated."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from functools import lru_cache

from citizengraph.core2.calendar import PHT, Calendar
from citizengraph.core2.config import Core2Config, load_statutory_caps
from citizengraph.core2.models import Application, StepEntry
from citizengraph.core2.store import AlertStore, WorkflowStore
from citizengraph.graph import InMemoryGraph


@lru_cache(maxsize=1)
def graph() -> InMemoryGraph:
    return InMemoryGraph.from_dir()


def dt(day: int, hh: int = 9, mm: int = 0, month: int = 3) -> datetime:
    """A datetime in March 2026 (2026-03-02 is a Monday)."""
    return datetime(2026, month, day, hh, mm, tzinfo=PHT)


def fixture_calendar(holidays=(), suspensions=()) -> Calendar:
    """A FIXTURE calendar. The dates are invented for tests, not real holidays."""
    return Calendar(
        holidays={d: "TEST-HOLIDAY" for d in holidays},
        suspensions={d: "TEST-SUSPENSION" for d in suspensions},
    )


def make_app(
    service_id: str,
    stamps: list[tuple[datetime | None, datetime | None]],
    *,
    app_id: str = "A1",
    ref: str = "CG-SIM-0001",
    citizen: str = "CIT-0001",
    submitted: datetime | None = None,
) -> Application:
    """Build an application from one (entered_at, completed_at) pair per step, in order."""
    steps = graph().steps(service_id)
    assert len(stamps) <= len(steps)
    entries = [
        StepEntry(step_id=st.id, entered_at=a, completed_at=b)
        for st, (a, b) in zip(steps, stamps, strict=False)
        if a is not None or b is not None
    ]
    first = next((a for a, _ in stamps if a is not None), dt(2))
    return Application(
        app_id=app_id,
        ref=ref,
        citizen_ref=citizen,
        service_id=service_id,
        submitted_at=submitted or first,
        entries=entries,
    )


def chain(start: datetime, minutes: list[float], open_last: bool = True):
    """Contiguous (entered, completed) stamps; the last one open when ``open_last``."""
    out: list[tuple[datetime | None, datetime | None]] = []
    t = start
    for i, m in enumerate(minutes):
        end = t + timedelta(minutes=m)
        last = i == len(minutes) - 1
        out.append((t, None if (last and open_last) else end))
        t = end
    return out


def toolbox(
    apps=(),
    *,
    now: datetime,
    calendar: Calendar | None = None,
    absences=(),
    day_types=None,
    cfg: Core2Config | None = None,
    alerts: AlertStore | None = None,
):
    from citizengraph.core2.tools import Toolbox

    store = WorkflowStore()
    for a in apps:
        store.add(a)
    for role, day in absences:
        store.set_absent(role, day, "absent (simulated)")
    return Toolbox(
        graph=graph(),
        store=store,
        calendar=calendar or fixture_calendar(),
        alerts=alerts or AlertStore(),
        config=cfg or Core2Config(),
        caps=load_statutory_caps(),
        now=now,
        day_types=day_types or {},
    )


__all__ = ["chain", "date", "dt", "fixture_calendar", "graph", "make_app", "toolbox"]
