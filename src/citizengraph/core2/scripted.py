"""ScriptedPolicy: an ``LLMClient`` that follows a hand-written reference policy.

READ THIS BEFORE USING IT. This is a TEST DOUBLE. It exists to exercise the agent loop, the
grammar, the prompt format and the evaluation harness. It contains no model. Its scores measure
how well the harness and the gold outcomes agree with the policy's author, NOT how well any language
model can do this task, and they must never be reported as model results. Real model evaluation
happens later, with the same harness and a real ``LLMClient``.

The policy is written as a generator (``reference_plan``): it yields the next tool call and
receives the observation. ``ScriptedPolicy.generate`` is stateless like a real model: it rebuilds
the plan from the prompt (task line plus the ACTION/RESULT history) on every call and replays the
recorded observations to find the next action. The same generator produces gold trajectories for
``traces.py``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Generator
from typing import Any

from citizengraph.core2.models import ALERT_KINDS
from citizengraph.core2.runtime import Task

Action = dict[str, Any]
Plan = Generator[Action, dict[str, Any], dict[str, Any]]

_ORDER = {k: i for i, k in enumerate(ALERT_KINDS)}


def _call(tool: str, **args: Any) -> Action:
    return {"tool": tool, "args": args}


def _plan_app(app_id: str, today: str) -> Generator[Action, dict[str, Any], dict[str, Any]]:
    """Reference rules for one application (see docs/core2_notes.md section 4)."""
    state = yield _call("get_workflow_state", app_id=app_id)
    if "error" in state:
        return {"app_id": app_id, "status": "cannot_determine",
                "reasons": ["no_application_found"], "alerts": []}  # fmt: skip
    issues = state.get("issues", [])
    cur = state.get("current")
    alerts: list[str] = ["missing_data_flag"] if issues else []
    reasons: list[str] = []
    status = "cannot_determine"

    if state.get("complete"):
        status = "completed"
        if issues:
            reasons.append("missing_timestamp_earlier_step")
    elif cur is None or cur.get("entered_at") is None:
        reasons.append("missing_timestamp")
    else:
        if issues:
            reasons.append("missing_timestamp_earlier_step")
        sla = yield _call(
            "get_step_sla", service_id=state["service_id"], step_id=cur["step_id"], app_id=app_id
        )
        check = sla.get("check", {})
        charter, stat = check.get("charter", {}), check.get("statutory", {})
        cv, sv = charter.get("verdict"), stat.get("verdict")
        if stat.get("reason") == "posting_period_treatment_unverified":
            reasons.append("posting_treatment_unverified")
        if cur.get("external"):
            status = "external_waiting"
            reasons.append("external_agency")
            if cv == "over":
                alerts.append("external_wait_notice")
        elif cur.get("posting") and cv != "over":
            status = "waiting_posting"
            reasons.append("posting_period")
            if charter.get("reason") == "day_type_unknown":
                reasons.append("day_type_unknown")
        elif sv == "over" or cv == "over":
            today_check = yield _call("check_work_suspension", date=today)
            if today_check.get("suspended"):
                status = "paused_by_suspension"
                reasons.append("suspension_today")
            elif sv == "over":
                status = "overdue_statutory"
                reasons.append("statutory_cap_exceeded")
                if cv == "over":
                    reasons.append("over_charter_step_time")
                alerts += ["citizen_delay_notice", "department_head_escalation"]
            else:
                status = "delayed"
                reasons.append("over_charter_step_time")
                alerts.append("citizen_delay_notice")
                roles = yield _call("get_step_roles", step_id=cur["step_id"])
                titles = [r["title"] for r in roles.get("roles", [])]
                if titles:
                    who = yield _call("get_role_availability", role=titles[0], date=today)
                    if who.get("available") is False:
                        alerts.append("department_head_escalation")
                        reasons.append("role_unavailable")
        elif charter.get("suspension_effect") or stat.get("suspension_effect"):
            status = "paused_by_suspension"
            reasons.append("suspension_days_excluded")
        elif cv == "minor_over":
            status = "minor_delay"
        elif cv == "within":
            status = "on_track"
        else:
            reasons.append(charter.get("reason") or "charter_time_not_stated")

    drafted: list[str] = []
    for kind in sorted(set(alerts), key=_ORDER.__getitem__):
        made = yield _call("draft_alert", app_id=app_id, kind=kind)
        if "error" not in made:
            drafted.append(kind)
    return {"app_id": app_id, "status": status, "reasons": reasons, "alerts": drafted}


def reference_plan(task: Task) -> Plan:
    """The reference policy for a whole task: yields tool calls, returns the final answer."""
    if task.kind == "working_days":
        obs = yield _call("working_days_elapsed", start=task.start, end=task.end)
        return {"answer": {"working_days": int(obs.get("working_days", 0))}}
    if task.kind == "suspension_check":
        obs = yield _call("check_work_suspension", date=task.date)
        return {"answer": {"suspended": bool(obs.get("suspended"))}}
    today = task.now[:10]
    if task.kind == "status":
        found = yield _call("get_applications", ref=task.ref)
        rows = found.get("applications", [])
        if not rows:
            return {"applications": [], "reasons": ["no_application_found"]}
        ids = [r["app_id"] for r in rows]
    else:
        found = yield _call("list_overdue", office_id=task.office_id, as_of=task.now)
        ids = [r["app_id"] for r in found.get("overdue", [])]
    results = []
    for app_id in ids:
        results.append((yield from _plan_app(app_id, today)))
    return {"applications": results}


# ------------------------------------------------------------------------------- the LLMClient


_TASK = re.compile(r"^TASK: (.*)$", re.MULTILINE)
_ACTION = re.compile(r"^ACTION (\d+): (.*)$", re.MULTILINE)
_RESULT = re.compile(r"^RESULT (\d+): (.*)$", re.MULTILINE)


def parse_prompt(prompt: str) -> tuple[Task, list[tuple[Action, dict[str, Any]]]]:
    """Recover the task and the (action, observation) history from an agent prompt."""
    m = _TASK.search(prompt)
    if not m:
        raise ValueError("no TASK line in the prompt")
    task = Task(**json.loads(m.group(1)))
    actions = {int(i): json.loads(a) for i, a in _ACTION.findall(prompt)}
    results = {int(i): json.loads(r) for i, r in _RESULT.findall(prompt)}
    return task, [(actions[i], results[i]) for i in sorted(actions) if i in results]


class ScriptedPolicy:
    """Follows ``reference_plan``. TEST DOUBLE ONLY: not evidence of model quality."""

    name = "scripted-policy"

    def __init__(self) -> None:
        self.calls = 0

    def generate(self, prompt: str, *, max_tokens: int = 256, grammar: str | None = None) -> str:
        self.calls += 1
        task, history = parse_prompt(prompt)
        plan = reference_plan(task)
        try:
            action = next(plan)
            for _action, observation in history:
                action = plan.send(observation)
        except StopIteration as done:
            return json.dumps({"final": done.value}, ensure_ascii=False)
        return json.dumps(action, ensure_ascii=False)
