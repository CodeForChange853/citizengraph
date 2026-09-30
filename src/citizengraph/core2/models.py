"""Simulated workflow records. Nothing here is real citizen data.

An ``Application`` is a fake reference code plus per-step timestamps. It lives in the
``WorkflowStore`` (``store.py``), never in the charter graph. Datetimes are naive local time.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Simulated codes only. This is the guard that keeps a real-looking value out of the store.
SIM_CODE = re.compile(r"^(CG|CIT|APP|A)[-A-Z0-9]{1,30}$")

AlertKind = Literal[
    "citizen_delay_notice",
    "department_head_escalation",
    "external_wait_notice",
    "missing_data_flag",
]
ALERT_KINDS: tuple[str, ...] = (
    "citizen_delay_notice",
    "department_head_escalation",
    "external_wait_notice",
    "missing_data_flag",
)
AUDIENCE: dict[str, str] = {
    "citizen_delay_notice": "citizen",
    "external_wait_notice": "citizen",
    "department_head_escalation": "staff",
    "missing_data_flag": "staff",
}

STATUSES: tuple[str, ...] = (
    "on_track",
    "minor_delay",
    "delayed",
    "overdue_statutory",
    "external_waiting",
    "waiting_posting",
    "paused_by_suspension",
    "cannot_determine",
    "completed",
)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class StepEntry(_Strict):
    """When an application entered and left one charter step. Either may be missing."""

    step_id: str
    entered_at: datetime | None = None
    completed_at: datetime | None = None


class Application(_Strict):
    app_id: str
    ref: str  # fake reference code shown to the citizen, e.g. CG-SIM-0001
    citizen_ref: str  # fake pseudonym so one citizen can have several applications
    service_id: str
    submitted_at: datetime
    entries: list[StepEntry] = Field(default_factory=list)

    @field_validator("app_id", "ref", "citizen_ref")
    @classmethod
    def _simulated_code(cls, v: str) -> str:
        if not SIM_CODE.match(v):
            raise ValueError(f"{v!r} does not look like a simulated code (CG-/CIT-/APP-/A...)")
        return v

    def entry(self, step_id: str) -> StepEntry | None:
        return next((e for e in self.entries if e.step_id == step_id), None)
