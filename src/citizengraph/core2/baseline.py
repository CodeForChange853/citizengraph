"""Rule-based (if-else) SLA agent: the baseline for RQ3.

FROZEN. The rules are documented in docs/core2_notes.md section 2 and were written before the
scenarios. Do not change them after seeing results; add a dated entry to the notes instead.

It uses the same tools as the model-driven agent and returns the same ``AgentResult``, so the
harness scores both the same way. It is a fair attempt, not a straw man: exactness comes from the
same tools, and it handles external steps, posting periods, unknown day types, missing timestamps,
absent roles and several applications for one citizen. Its known simplifications are listed in the
notes.
"""

from __future__ import annotations

from typing import Any

from citizengraph.core2.runtime import AgentResult, Task, TraceStep, safe_fallback
from citizengraph.core2.tools import ToolArgumentError, Toolbox


class _StepCap(Exception):
    """The shared step budget ran out before the rules finished."""


class _Recorder:
    def __init__(self, toolbox: Toolbox, max_steps: int) -> None:
        self.toolbox = toolbox
        self.max_steps = max_steps
        self.trace: list[TraceStep] = []
        self.calls = 0

    def __call__(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        if self.calls + 1 >= self.max_steps:  # keep one step for the final answer
            raise _StepCap
        self.calls += 1
        try:
            obs = self.toolbox.call(tool, args)
        except ToolArgumentError as exc:  # a baseline bug, not a model error: keep it visible
            obs = {"error": "invalid_arguments", "detail": str(exc)}
        self.trace.append(
            TraceStep(
                n=self.calls, kind="tool", action={"tool": tool, "args": args}, observation=obs
            )
        )
        return obs


class RuleBasedAgent:
    name = "baseline"

    def run(self, task: Task, toolbox: Toolbox, max_steps: int | None = None) -> AgentResult:
        """Answer ``task``. ``max_steps`` is the same budget the agent gets (tool calls plus the
        final answer); when it runs out the result is the same safe fallback."""
        rec = _Recorder(toolbox, max_steps or toolbox.config.max_steps)
        try:
            final = self._answer(task, rec)
        except _StepCap:
            return AgentResult(
                task=task,
                final=safe_fallback(),
                trace=rec.trace,
                steps=rec.calls,
                stopped_reason="step_cap",
                runner=self.name,
            )
        rec.trace.append(TraceStep(n=rec.calls + 1, kind="final", action={"final": final}))
        return AgentResult(
            task=task,
            final=final,
            trace=rec.trace,
            steps=rec.calls + 1,
            stopped_reason="final",
            runner=self.name,
        )

    def _answer(self, task: Task, rec: _Recorder) -> dict[str, Any]:
        if task.kind == "working_days":
            obs = rec("working_days_elapsed", {"start": task.start, "end": task.end})
            return {"answer": {"working_days": obs.get("working_days", 0)}}
        if task.kind == "suspension_check":
            obs = rec("check_work_suspension", {"date": task.date})
            return {"answer": {"suspended": bool(obs.get("suspended"))}}
        if task.kind == "status":
            return self._status(task, rec)
        return self._sweep(task, rec)

    # -- tasks ---------------------------------------------------------------------------------

    def _status(self, task: Task, rec: _Recorder) -> dict[str, Any]:
        found = rec("get_applications", {"ref": task.ref})
        rows = found.get("applications", [])
        if not rows:
            return {"applications": [], "reasons": ["no_application_found"]}
        return {"applications": [self._app(rec, r["app_id"]) for r in rows]}

    def _sweep(self, task: Task, rec: _Recorder) -> dict[str, Any]:
        found = rec("list_overdue", {"office_id": task.office_id, "as_of": task.now})
        rows = found.get("overdue", [])
        return {"applications": [self._app(rec, r["app_id"]) for r in rows]}

    # -- one application: the frozen rules B1..B10 --------------------------------------------

    def _app(self, rec: _Recorder, app_id: str) -> dict[str, Any]:
        today = rec.toolbox.now.strftime("%Y-%m-%d")
        state = rec("get_workflow_state", {"app_id": app_id})
        alerts: list[str] = []

        def draft(kind: str) -> None:
            if "error" not in rec("draft_alert", {"app_id": app_id, "kind": kind}):
                alerts.append(kind)

        def result(status: str, reasons: list[str]) -> dict[str, Any]:
            return {
                "app_id": app_id,
                "status": status,
                "reasons": reasons,
                "alerts": sorted(set(alerts)),
            }

        if state.get("issues"):  # B1
            draft("missing_data_flag")
            return result("cannot_determine", ["missing_timestamp"])
        if state.get("complete"):  # B2
            return result("completed", [])
        cur = state["current"]
        sla = rec(
            "get_step_sla",
            {"service_id": state["service_id"], "step_id": cur["step_id"], "app_id": app_id},
        )
        check = sla.get("check", {})
        charter, statutory = check.get("charter", {}), check.get("statutory", {})
        if cur.get("external"):  # B3
            if charter.get("verdict") == "over":
                draft("external_wait_notice")
            return result("external_waiting", ["external_agency"])
        if cur.get("posting"):  # B4
            return result("waiting_posting", ["posting_period"])
        if charter.get("suspension_effect") or statutory.get("suspension_effect"):  # B5
            return result("paused_by_suspension", ["suspension_days_excluded"])
        if statutory.get("verdict") == "over":  # B6
            draft("citizen_delay_notice")
            draft("department_head_escalation")
            reasons = ["statutory_cap_exceeded"]
            if charter.get("verdict") == "over":
                reasons.append("over_charter_step_time")
            return result("overdue_statutory", reasons)
        verdict = charter.get("verdict")
        if verdict == "over":  # B7
            draft("citizen_delay_notice")
            reasons = ["over_charter_step_time"]
            roles = rec("get_step_roles", {"step_id": cur["step_id"]}).get("roles", [])
            if roles:
                who = rec("get_role_availability", {"role": roles[0]["title"], "date": today})
                if who.get("available") is False:
                    draft("department_head_escalation")
                    reasons.append("role_unavailable")
            return result("delayed", reasons)
        if verdict == "minor_over":  # B8
            return result("minor_delay", [])
        if verdict == "within":  # B9
            return result("on_track", [])
        reason = charter.get("reason") or "charter_time_not_stated"  # B10
        return result("cannot_determine", [reason])
