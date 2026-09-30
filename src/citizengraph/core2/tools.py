"""The nine Core 2 tools: typed, documented, read-only, with strict argument validation.

The model chooses which tool to call and with which arguments; everything exact (elapsed time,
working days, verdicts, alert text) happens here in plain code. Tools never touch Neo4j and never
change the workflow store. ``draft_alert`` is the only writer and writes only to the separate
``AlertStore``.

Content problems (unknown application, reversed date range, alert the facts do not support) come
back as ``{"error": ...}`` observations the model can react to. Malformed *arguments* raise
``ToolArgumentError`` and an unknown tool raises ``UnknownToolError``; the agent loop turns both
into observations with a bounded retry budget.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from citizengraph.core2.alerts import (
    AlertContext,
    days_en,
    days_fil,
    minutes_en,
    minutes_fil,
    render_alert,
)
from citizengraph.core2.calendar import (
    PHT,
    Calendar,
    check_work_suspension,
    working_days_elapsed,
)
from citizengraph.core2.config import (
    CHARTER_BASIS,
    Core2Config,
    StatutoryCaps,
)
from citizengraph.core2.models import ALERT_KINDS, AUDIENCE, Application
from citizengraph.core2.sla import (
    StatutoryCheck,
    StepCheck,
    WorkflowState,
    allowance,
    check_statutory,
    check_step,
    resolve_day_type,
    workflow_state,
)
from citizengraph.core2.store import Alert, AlertStore, WorkflowStore
from citizengraph.graph import InMemoryGraph
from citizengraph.graph.ids import clean_name, slug
from citizengraph.graph.models import Step


class ToolArgumentError(ValueError):
    """The arguments do not match the tool's schema. The message is shown to the model."""


class UnknownToolError(KeyError):
    """No tool with that name."""


# ------------------------------------------------------------------------------------- specification

_ID = re.compile(r"^[A-Za-z0-9_.:\-]{1,64}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$")
_ROLE = re.compile(r"^[^\x00-\x1f\x7f]{1,100}$")


@dataclass(frozen=True)
class Param:
    name: str
    type: str  # id | role | date | datetime | enum
    doc: str
    required: bool = True
    enum: tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolSpec:
    name: str
    doc: str
    params: tuple[Param, ...]
    fn: Callable[..., dict[str, Any]] = field(repr=False, compare=False)

    def signature(self) -> str:
        parts = []
        for p in self.params:
            label = "|".join(p.enum) if p.type == "enum" else p.type
            parts.append(f"{p.name}{'' if p.required else '?'}:{label}")
        return f"{self.name}({', '.join(parts)})"


def _parse_date(text: str) -> date:
    if not _DATE.match(text):
        raise ValueError("expected a date written YYYY-MM-DD")
    return date.fromisoformat(text)


def _parse_datetime(text: str) -> datetime:
    if not _DATETIME.match(text):
        raise ValueError("expected a local time written YYYY-MM-DDTHH:MM")
    return datetime.fromisoformat(text).replace(tzinfo=PHT)


def _check_value(p: Param, value: Any) -> Any:
    if p.type == "enum":
        if not isinstance(value, str) or value not in p.enum:
            raise ValueError(f"must be one of {list(p.enum)}")
        return value
    if isinstance(value, bool) or not isinstance(value, str):
        raise TypeError("must be a string")
    if p.type == "id":
        if not _ID.match(value):
            raise ValueError("must be 1-64 characters from letters, digits and _ . : -")
        return value
    if p.type == "role":
        if not _ROLE.match(value):
            raise ValueError("must be a role title of 1-100 printable characters")
        return value
    try:
        return _parse_date(value) if p.type == "date" else _parse_datetime(value)
    except ValueError as exc:
        raise ValueError(str(exc)) from None


def fmt_dt(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M")


def _strip(obj: Any) -> Any:
    """Drop None values recursively so observations stay compact."""
    if isinstance(obj, dict):
        return {k: _strip(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [_strip(v) for v in obj]
    return obj


def _round(x: float | None) -> float | int | None:
    if x is None:
        return None
    return int(x) if float(x).is_integer() else round(x, 2)


# ---------------------------------------------------------------------------------------------- toolbox


class Toolbox:
    """Bundles the read-only data sources and the alert store behind the nine tools."""

    def __init__(
        self,
        *,
        graph: InMemoryGraph,
        store: WorkflowStore,
        calendar: Calendar,
        alerts: AlertStore,
        config: Core2Config,
        caps: StatutoryCaps,
        now: datetime,
        day_types: dict[str, str] | None = None,
    ) -> None:
        self.graph = graph
        self.store = store
        self.calendar = calendar
        self.alerts = alerts
        self.config = config
        self.caps = caps
        self.now = now
        self.day_types = dict(day_types or {})
        self._steps = {st.id: st for st in graph.seed.steps}
        self._roles = {
            clean_name(st.role): st.role for st in graph.seed.steps if st.role is not None
        }
        self.specs: dict[str, ToolSpec] = {s.name: s for s in self._build_specs()}

    # -- registry ------------------------------------------------------------------------------

    def _build_specs(self) -> list[ToolSpec]:
        app = Param("app_id", "id", "application id from get_applications")
        return [
            ToolSpec(
                "get_applications",
                "Applications for a reference (CG-...) or citizen (CIT-...) code.",
                (Param("ref", "id", "application reference (CG-...) or citizen code (CIT-...)"),),
                self.get_applications,
            ),
            ToolSpec(
                "get_workflow_state",
                "Current step of one application, minutes in it, timestamp issues.",
                (app,),
                self.get_workflow_state,
            ),
            ToolSpec(
                "get_step_sla",
                "Charter time and statutory cap of a step. With app_id: the exact comparison "
                "for that application.",
                (
                    Param("service_id", "id", "service id"),
                    Param("step_id", "id", "step id"),
                    Param("app_id", "id", "application to compare", required=False),
                ),
                self.get_step_sla,
            ),
            ToolSpec(
                "working_days_elapsed",
                "Working days after start up to and including end.",
                (
                    Param("start", "date", "start date YYYY-MM-DD"),
                    Param("end", "date", "end date YYYY-MM-DD"),
                ),
                self.working_days_elapsed,
            ),
            ToolSpec(
                "check_work_suspension",
                "Is the date a declared work suspension? Is it a working day?",
                (Param("date", "date", "date YYYY-MM-DD"),),
                self.check_work_suspension,
            ),
            ToolSpec(
                "get_step_roles",
                "Role title responsible for a step (never a person's name).",
                (Param("step_id", "id", "step id"),),
                self.get_step_roles,
            ),
            ToolSpec(
                "get_role_availability",
                "Is the role marked absent on the date?",
                (
                    Param("role", "role", "role title or role id from get_step_roles"),
                    Param("date", "date", "date YYYY-MM-DD"),
                ),
                self.get_role_availability,
            ),
            ToolSpec(
                "list_overdue",
                "Office applications over the charter or statutory limit at as_of "
                "(external waits are never listed).",
                (
                    Param("office_id", "id", "office id, e.g. bplo, lcro, cho, cswdo"),
                    Param("as_of", "datetime", "local time YYYY-MM-DDTHH:MM"),
                ),
                self.list_overdue,
            ),
            ToolSpec(
                "draft_alert",
                "Draft an alert into the alert store. Refused when the facts do not support it.",
                (
                    app,
                    Param("kind", "enum", "alert kind", enum=ALERT_KINDS),
                ),
                self.draft_alert,
            ),
        ]

    def describe(self) -> str:
        """One line per tool for the model prompt."""
        return "\n".join(f"- {s.signature()}: {s.doc}" for s in self.specs.values())

    def validate(self, name: str, args: Any) -> dict[str, Any]:
        spec = self.specs.get(name) if isinstance(name, str) else None
        if spec is None:
            raise UnknownToolError(name)
        if not isinstance(args, dict):
            raise ToolArgumentError("args must be a JSON object")
        problems: list[str] = []
        known = {p.name for p in spec.params}
        problems += [f"unknown argument '{k}'" for k in args if k not in known]
        clean: dict[str, Any] = {}
        for p in spec.params:
            if p.name not in args or args[p.name] is None:
                if p.required:
                    problems.append(f"missing argument '{p.name}'")
                continue
            try:
                clean[p.name] = _check_value(p, args[p.name])
            except (TypeError, ValueError) as exc:
                problems.append(f"argument '{p.name}': {exc}")
        if problems:
            raise ToolArgumentError(f"{name}: " + "; ".join(problems))
        return clean

    def call(self, name: str, args: Any) -> dict[str, Any]:
        clean = self.validate(name, args)
        return _strip(self.specs[name].fn(**clean))

    # -- helpers -------------------------------------------------------------------------------

    def _overrides(self) -> dict[str, str]:
        return {**self.config.day_type_overrides, **self.day_types}

    def _charter_check(self, app: Application, step: Step, as_of: datetime) -> StepCheck:
        return check_step(
            step,
            app.entry(step.id),
            as_of,
            service_id=app.service_id,
            calendar=self.calendar,
            day_types=self._overrides(),
            config=self.config,
        )

    def _statutory_check(self, app: Application, as_of: datetime) -> StatutoryCheck:
        return check_statutory(
            app,
            self.graph,
            as_of,
            calendar=self.calendar,
            caps=self.caps,
            config=self.config,
        )

    def _office_name(self, service_id: str) -> str:
        return self.graph.office_of(service_id).name

    @staticmethod
    def _not_found(what: str, value: str) -> dict[str, Any]:
        return {"error": "not_found", "what": what, "value": value}

    # -- tools ---------------------------------------------------------------------------------

    def get_applications(self, ref: str) -> dict[str, Any]:
        """List the applications for a reference code or a citizen code."""
        found = self.store.find(ref)
        limit = self.config.row_limit
        return {
            "ref": ref,
            "count": len(found),
            "truncated": len(found) > limit,
            "applications": [
                {
                    "app_id": a.app_id,
                    "ref": a.ref,
                    "service_id": a.service_id,
                    "submitted_at": fmt_dt(a.submitted_at),
                }
                for a in found[:limit]
            ],
        }

    def get_workflow_state(self, app_id: str) -> dict[str, Any]:
        """Progress of one application at the toolbox clock."""
        app = self.store.get(app_id)
        if app is None:
            return self._not_found("application", app_id)
        state = workflow_state(app, self.graph)
        current = None
        if state.current is not None:
            entry = state.current_entry
            entered = entry.entered_at if entry else None
            current = {
                "step_id": state.current.id,
                "order": state.current.order,
                "entered_at": fmt_dt(entered) if entered else None,
                "elapsed_min": (
                    round((self.now - entered).total_seconds() / 60.0, 2) if entered else None
                ),
                "external": state.current.external_agency,
                "posting": True if state.current.id in self.config.posting_step_ids else None,
            }
        return {
            "app_id": app.app_id,
            "service_id": app.service_id,
            "complete": state.complete,
            "steps_done": state.steps_done,
            "steps_total": len(state.steps),
            "current": current,
            "issues": [{"step_id": i.step_id, "problem": i.problem} for i in state.issues],
        }

    def get_step_sla(
        self, service_id: str, step_id: str, app_id: str | None = None
    ) -> dict[str, Any]:
        """Limits for a step and, with an application, the exact comparison."""
        try:
            service = self.graph.service(service_id)
        except KeyError:
            return self._not_found("service", service_id)
        step = self._steps.get(step_id)
        if step is None or step.service_id != service_id:
            return self._not_found("step", step_id)
        out: dict[str, Any] = {
            "step_id": step_id,
            "order": step.order,
            "class": service.classification,
            "external_agency": step.external_agency,
            "posting": True if step.id in self.config.posting_step_ids else None,
        }
        if app_id is None:
            dtype = resolve_day_type(step, service_id, self._overrides())
            allow = allowance(step, dtype, weekend_len=len(self.calendar.weekend))
            out["charter"] = {
                "basis": CHARTER_BASIS,
                "comparable": allow.comparable,
                "reason": allow.reason,
                "kind": allow.kind,
                "min": _round(allow.value_min),
                "max": _round(allow.value_max),
                "unit": allow.unit,
                "day_type": allow.day_type,
                "allowed": _round(allow.allowed_minutes or allow.allowed_days),
            }
            out["statutory"] = {
                "basis": self.caps.basis,
                "cap_working_days": self.caps.working_days.get(service.classification),
            }
            return out
        app = self.store.get(app_id)
        if app is None:
            return self._not_found("application", app_id)
        if app.service_id != service_id:
            return {"error": "app_service_mismatch", "app_service": app.service_id}
        out["check"] = self._check_block(app, step)
        return out

    def _check_block(self, app: Application, step: Step) -> dict[str, Any]:
        c = self._charter_check(app, step, self.now)
        s = self._statutory_check(app, self.now)
        return {
            "charter": {
                "basis": CHARTER_BASIS,
                "verdict": c.verdict,
                "reason": c.reason,
                "measured": _round(c.measured),
                "allowed": _round(c.allowed),
                "unit": {"clock": "min", "working_days": "wd", "calendar_days": "cd"}.get(
                    c.kind or ""
                ),
                "suspension_effect": True if c.suspension_effect else None,
                "suspension_days": c.suspension_days or None,
            },
            "statutory": {
                "verdict": s.verdict,
                "reason": s.reason,
                "cap": s.cap,
                "lgu_working_days": s.elapsed_working_days,
                "external_days_excluded": s.external_days_excluded or None,
                "suspension_effect": True if s.suspension_effect else None,
                "basis": s.basis,
            },
        }

    def working_days_elapsed(self, start: date, end: date) -> dict[str, Any]:
        """Working days after ``start`` up to and including ``end``."""
        if end < start:
            return {"error": "end_before_start", "start": start.isoformat(), "end": end.isoformat()}
        return {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "working_days": working_days_elapsed(start, end, self.calendar),
        }

    def check_work_suspension(self, date: date) -> dict[str, Any]:
        """Is ``date`` a declared work suspension?"""
        r = check_work_suspension(date, self.calendar)
        return {
            "date": r.date.isoformat(),
            "suspended": r.suspended,
            "working_day": r.working_day,
            "reason": r.reason,
            "non_working_reason": r.non_working_reason,
        }

    def get_step_roles(self, step_id: str) -> dict[str, Any]:
        """Role title responsible for a step."""
        step = self._steps.get(step_id)
        if step is None:
            return self._not_found("step", step_id)
        if step.role is None:
            return {"step_id": step_id, "roles": [], "note": "the charter gives no role title"}
        title = clean_name(step.role)
        return {"step_id": step_id, "roles": [{"role_id": slug(title), "title": title}]}

    def get_role_availability(self, role: str, date: date) -> dict[str, Any]:
        """Whether a role is marked absent on ``date`` in the simulated roster."""
        wanted = clean_name(role)
        title = self._roles.get(wanted) or next(
            (t for t in self._roles.values() if slug(t) == wanted), None
        )
        if title is None:
            return {"error": "unknown_role", "role": role}
        why = self.store.absence(clean_name(title), date)
        return {
            "role": clean_name(title),
            "date": date.isoformat(),
            "available": why is None,
            "reason": f"absent: {why}" if why else None,
        }

    def list_overdue(self, office_id: str, as_of: datetime) -> dict[str, Any]:
        """Applications of an office over their charter step time or the statutory cap."""
        if office_id not in {o.id for o in self.graph.seed.offices}:
            return self._not_found("office", office_id)
        services = {s.id for s in self.graph.services(office_id)}
        rows: list[dict[str, Any]] = []
        for app in self.store.all():
            if app.service_id not in services or app.submitted_at > as_of:
                continue
            state = workflow_state(app, self.graph)
            if state.complete or state.current is None or state.current.external_agency:
                continue
            charter = self._charter_check(app, state.current, as_of)
            statutory = self._statutory_check(app, as_of)
            if charter.verdict == "over" or statutory.verdict == "over":
                rows.append(
                    {
                        "app_id": app.app_id,
                        "step_id": state.current.id,
                        "charter": charter.verdict,
                        "statutory": statutory.verdict,
                    }
                )
        limit = self.config.row_limit
        return {
            "office_id": office_id,
            "as_of": fmt_dt(as_of),
            "count": len(rows),
            "truncated": len(rows) > limit,
            "overdue": rows[:limit],
        }

    # -- alerts --------------------------------------------------------------------------------

    def _facts(self, app: Application) -> tuple[WorkflowState, StepCheck | None, StatutoryCheck]:
        state = workflow_state(app, self.graph)
        charter = self._charter_check(app, state.current, self.now) if state.current else None
        return state, charter, self._statutory_check(app, self.now)

    def _applicable(self, kind: str, state: WorkflowState, charter, statutory) -> str | None:
        """None when the alert is supported by the facts, else the reason it is not."""
        if kind == "missing_data_flag":
            return None if state.issues else "the record has no timestamp problems"
        if state.complete or state.current is None:
            return "the application is complete"
        external = state.current.external_agency
        if kind == "external_wait_notice":
            if not external:
                return "the current step is not an external agency's step"
            if charter is None or charter.verdict != "over":
                return "the external wait is not over the stated time"
            return None
        if external:
            return "the current step belongs to an external agency; it is not an LGU delay"
        lgu_over = charter is not None and charter.verdict == "over"
        if not (lgu_over or statutory.verdict == "over"):
            return "no charter or statutory limit is exceeded"
        return None

    def draft_alert(self, app_id: str, kind: str) -> dict[str, Any]:
        """Draft one alert into the alert store."""
        app = self.store.get(app_id)
        if app is None:
            return self._not_found("application", app_id)
        state, charter, statutory = self._facts(app)
        why_not = self._applicable(kind, state, charter, statutory)
        if why_not:
            return {"error": "not_applicable", "kind": kind, "reason": why_not}
        en, fil = render_alert(kind, self._context(app, state, charter, statutory))
        alert = Alert(
            alert_id=f"AL-{app.app_id}-{kind}",
            app_id=app.app_id,
            kind=kind,
            audience=AUDIENCE[kind],
            text_en=en,
            text_fil=fil,
            created_at=self.now,
        )
        created = self.alerts.add(alert)
        return {
            "alert_id": alert.alert_id,
            "app_id": app_id,
            "kind": kind,
            "audience": alert.audience,
            "created": created,
        }

    def _context(self, app, state, charter, statutory) -> AlertContext:
        service = self.graph.service(app.service_id)
        step = state.current
        allowed_en = allowed_fil = elapsed_en = elapsed_fil = None
        if charter is not None and charter.allowed is not None and charter.measured is not None:
            if charter.kind == "clock":
                allowed_en, allowed_fil = minutes_en(charter.allowed), minutes_fil(charter.allowed)
                elapsed_en, elapsed_fil = (
                    minutes_en(charter.measured),
                    minutes_fil(charter.measured),
                )
            else:
                allowed_en, allowed_fil = (
                    days_en(charter.allowed, charter.kind),
                    days_fil(charter.allowed, charter.kind),
                )
                elapsed_en, elapsed_fil = (
                    days_en(charter.measured, charter.kind),
                    days_fil(charter.measured, charter.kind),
                )
        role = clean_name(step.role) if step and step.role else None
        role_absent = bool(role and self.store.absence(role, self.now))
        orders = {st.id: st.order for st in state.steps}
        charter_over = charter is not None and charter.verdict == "over"
        return AlertContext(
            ref=app.ref,
            service_name=service.name,
            office_name=self._office_name(app.service_id),
            step_order=step.order if step else None,
            steps_total=len(state.steps),
            external_agency=step.external_agency if step else None,
            allowed_en=allowed_en if charter_over else None,
            allowed_fil=allowed_fil if charter_over else None,
            elapsed_en=elapsed_en if charter_over else None,
            elapsed_fil=elapsed_fil if charter_over else None,
            role_title=role,
            role_absent=role_absent,
            statutory_days=statutory.elapsed_working_days,
            statutory_cap=statutory.cap if statutory.verdict == "over" else None,
            issues=[(orders.get(i.step_id), i.problem) for i in state.issues],
        )
