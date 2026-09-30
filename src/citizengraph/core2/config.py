"""Core 2 configuration: ``config/core2.yaml`` plus the statutory caps in ``config/sla.yaml``.

A missing core2.yaml gives the documented defaults; a present but invalid one is an error
(a wrong number silently changing alert behaviour is worse than a crash).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from citizengraph.core2.calendar import REPO_ROOT

DEFAULT_CORE2_YAML = REPO_ROOT / "config" / "core2.yaml"
DEFAULT_SLA_YAML = REPO_ROOT / "config" / "sla.yaml"

STATUTORY_BASIS = "statutory_cap_unverified"
CHARTER_BASIS = "charter_step_time"


class Core2Config(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_steps: int = Field(default=8, ge=1, le=64, strict=True)
    invalid_json_retries: int = Field(default=1, ge=0, le=3, strict=True)
    invalid_args_retries: int = Field(default=2, ge=0, le=8, strict=True)
    max_observation_chars: int = Field(default=900, ge=100, strict=True)
    max_prompt_chars: int = Field(default=7000, ge=1000, strict=True)
    max_tokens: int = Field(default=200, ge=16, strict=True)
    trajectory_log: str = "data/simulated/core2_trajectories.jsonl"
    row_limit: int = Field(default=10, ge=1, le=100, strict=True)
    alert_store: str = "data/simulated/core2_alerts.jsonl"
    minor_delay_ratio: float = Field(default=1.5, gt=1.0)
    weekend_days: frozenset[int] = frozenset({5, 6})
    day_type_overrides: dict[str, Literal["working", "calendar"]] = Field(default_factory=dict)
    posting_step_ids: tuple[str, ...] = ("birth_registration_delayed-S04",)

    @field_validator("weekend_days")
    @classmethod
    def _weekday_numbers(cls, v: frozenset[int]) -> frozenset[int]:
        if any(not isinstance(d, int) or d < 0 or d > 6 for d in v):
            raise ValueError("weekend_days must be weekday numbers 0 to 6")
        return v


def load_core2_config(path: str | Path | None = None) -> Core2Config:
    p = Path(path) if path else DEFAULT_CORE2_YAML
    if not p.exists():
        return Core2Config()
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        section = data.get("core2") or {}
        if not isinstance(section, dict):
            raise TypeError("core2 must be a mapping")
        return Core2Config(**section)
    except (ValidationError, yaml.YAMLError, TypeError) as exc:
        raise ValueError(f"invalid Core 2 config {p}: {exc}") from exc


class StatutoryCaps(BaseModel):
    """RA 11032 working-day limits as configured in config/sla.yaml. UNVERIFIED."""

    model_config = ConfigDict(frozen=True)

    working_days: dict[str, int]
    basis: str = STATUTORY_BASIS


def load_statutory_caps(path: str | Path | None = None) -> StatutoryCaps:
    p = Path(path) if path else DEFAULT_SLA_YAML
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    caps = data.get("statutory_working_days") or {}
    if not isinstance(caps, dict) or not all(isinstance(v, int) and v > 0 for v in caps.values()):
        raise ValueError(f"statutory_working_days in {p} must map class names to positive ints")
    return StatutoryCaps(working_days={str(k): v for k, v in caps.items()})
