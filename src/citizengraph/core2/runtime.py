"""Shared types for anything that answers a Core 2 task: the ReAct agent and the baseline.

``Task`` is what is asked, ``AgentResult`` is what comes back (final answer, full trace, step
count, why it stopped). Trajectories are written as JSONL, one line per run.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from citizengraph.core2.calendar import PHT
from citizengraph.core2.models import ALERT_KINDS, STATUSES

REASONS: tuple[str, ...] = (
    "no_application_found",
    "missing_timestamp",
    "missing_timestamp_earlier_step",
    "timestamps_out_of_order",
    "day_type_unknown",
    "charter_time_not_stated",
    "external_agency",
    "posting_period",
    "posting_treatment_unverified",
    "statutory_cap_exceeded",
    "over_charter_step_time",
    "role_unavailable",
    "suspension_days_excluded",
    "suspension_today",
    "agent_fallback",
)
StoppedReason = Literal[
    "final", "step_cap", "invalid_json", "invalid_action", "prompt_too_long", "llm_error"
]
_ID = re.compile(r"^[A-Za-z0-9_.:\-]{1,64}$")
_LOCAL_TIME = "%Y-%m-%dT%H:%M"


class Task(BaseModel):
    """One question for the SLA agent. ``now`` is the simulated clock (local time)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["status", "office_sweep", "working_days", "suspension_check"]
    now: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")
    ref: str | None = None  # status: application reference or citizen code
    office_id: str | None = None  # office_sweep
    start: str | None = None  # working_days
    end: str | None = None
    date: str | None = None  # suspension_check
    language: Literal["en", "fil"] = "en"

    @model_validator(mode="after")
    def _fields_for_kind(self) -> Task:
        need = {
            "status": ("ref",),
            "office_sweep": ("office_id",),
            "working_days": ("start", "end"),
            "suspension_check": ("date",),
        }[self.kind]
        missing = [f for f in need if getattr(self, f) is None]
        if missing:
            raise ValueError(f"{self.kind} task needs {missing}")
        return self

    @property
    def clock(self) -> datetime:
        return datetime.strptime(self.now, _LOCAL_TIME).replace(tzinfo=PHT)

    def brief(self) -> str:
        """One JSON line for the prompt, without unset fields."""
        return json.dumps(
            self.model_dump(exclude_none=True, exclude={"language"}), separators=(",", ":")
        )


class TraceStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    n: int
    kind: Literal["tool", "final", "invalid_json", "invalid_args", "unknown_tool", "invalid_final"]
    raw: str | None = None
    action: dict[str, Any] | None = None
    observation: dict[str, Any] | None = None
    error: str | None = None


class AgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task: Task
    final: dict[str, Any]
    trace: list[TraceStep]
    steps: int  # tool calls that ran
    llm_calls: int = 0
    stopped_reason: StoppedReason
    runner: str = ""

    @property
    def tool_calls(self) -> list[tuple[str, dict[str, Any]]]:
        """Every tool call the runner attempted (valid or not), in order."""
        return [
            (s.action["tool"], s.action.get("args", {}))
            for s in self.trace
            if s.action and "tool" in s.action
        ]

    @property
    def is_fallback(self) -> bool:
        return self.stopped_reason != "final"


def safe_fallback() -> dict[str, Any]:
    """What the agent returns when it cannot finish: no claims, and 'ask the office'."""
    return {"applications": [], "fallback": "check_with_office", "reasons": ["agent_fallback"]}


def validate_final(final: Any) -> list[str]:
    """Problems with a model-supplied final answer (empty when it is acceptable)."""
    if not isinstance(final, dict):
        return ["final must be an object"]
    keys = set(final)
    if keys in ({"applications"}, {"applications", "reasons"}):
        extra = final.get("reasons", [])
        if not isinstance(extra, list) or any(r not in REASONS for r in extra):
            return [f"reasons must be a list from {list(REASONS)}"]
        apps = final["applications"]
        if not isinstance(apps, list) or len(apps) > 20:
            return ["applications must be a list of at most 20 items"]
        problems: list[str] = []
        for i, a in enumerate(apps):
            if not isinstance(a, dict) or set(a) != {"app_id", "status", "reasons", "alerts"}:
                problems.append(f"applications[{i}] needs exactly app_id, status, reasons, alerts")
                continue
            if not isinstance(a["app_id"], str) or not _ID.match(a["app_id"]):
                problems.append(f"applications[{i}].app_id is not a valid id")
            if a["status"] not in STATUSES:
                problems.append(f"applications[{i}].status must be one of {list(STATUSES)}")
            if not isinstance(a["reasons"], list) or any(r not in REASONS for r in a["reasons"]):
                problems.append(f"applications[{i}].reasons must be a list from {list(REASONS)}")
            if not isinstance(a["alerts"], list) or any(k not in ALERT_KINDS for k in a["alerts"]):
                problems.append(f"applications[{i}].alerts must be a list from {list(ALERT_KINDS)}")
        return problems
    if keys == {"answer"}:
        ans = final["answer"]
        if isinstance(ans, dict) and set(ans) == {"working_days"}:
            ok = isinstance(ans["working_days"], int) and not isinstance(ans["working_days"], bool)
            return [] if ok and ans["working_days"] >= 0 else ["working_days must be an integer"]
        if isinstance(ans, dict) and set(ans) == {"suspended"}:
            return [] if isinstance(ans["suspended"], bool) else ["suspended must be true or false"]
        return ["answer must be {working_days: int} or {suspended: bool}"]
    return ["final must have exactly 'applications' or 'answer'"]


def append_jsonl(result: AgentResult, path: str | Path) -> None:
    """Append one trajectory line. Local file only."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(result.model_dump_json() + "\n")
