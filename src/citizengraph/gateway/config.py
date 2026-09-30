"""Gateway settings: the ``gateway:`` section of ``config/limits.yaml``.

Missing keys fall back to the documented defaults; a key with a wrong type or an impossible value
raises ``GatewayConfigError`` when the gateway is built (a bad threshold must not silently change
what citizens are told).
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml

from citizengraph.gateway.types import INTENTS

DEFAULT_LIMITS_PATH = Path(__file__).resolve().parents[3] / "config" / "limits.yaml"


class GatewayConfigError(ValueError):
    """The gateway section of the limits file is unreadable or has a bad value."""


@dataclass(frozen=True)
class GatewayConfig:
    max_chars: int = 500
    hard_max_chars: int = 2000
    rate_limit_per_minute: int = 10
    repeat_limit: int = 3
    repeat_window_s: float = 300.0
    gibberish_threshold: float = 0.75
    link_min_score: float = 0.80
    ambiguity_margin: float = 0.04
    echo_min_score: float = 0.90
    noisy_unknown_ratio: float = 0.6
    noisy_min_tokens: int = 12
    max_phrase_chars: int = 160
    max_sub_requests: int = 6
    withheld_services: tuple[str, ...] = field(default_factory=tuple)
    default_intent: str | None = None

    def __post_init__(self) -> None:
        if not 0 < self.max_chars <= self.hard_max_chars:
            raise GatewayConfigError("need 0 < max_chars <= hard_max_chars")
        for name in ("rate_limit_per_minute", "repeat_limit", "max_phrase_chars"):
            if getattr(self, name) < 1:
                raise GatewayConfigError(f"{name} must be at least 1")
        if self.max_sub_requests < 1:
            raise GatewayConfigError("max_sub_requests must be at least 1")
        if self.default_intent is not None and self.default_intent not in INTENTS:
            raise GatewayConfigError(f"default_intent must be null or one of {INTENTS}")
        for name in (
            "gibberish_threshold",
            "link_min_score",
            "ambiguity_margin",
            "echo_min_score",
            "noisy_unknown_ratio",
        ):
            if not 0.0 <= getattr(self, name) <= 1.0:
                raise GatewayConfigError(f"{name} must be between 0 and 1")


_NUMERIC = {
    f.name: f.type
    for f in fields(GatewayConfig)
    if f.name not in ("withheld_services", "default_intent")
}


def config_from_mapping(raw: dict[str, Any] | None) -> GatewayConfig:
    values: dict[str, Any] = {}
    for key, value in (raw or {}).items():
        if key == "withheld_services":
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise GatewayConfigError("withheld_services must be a list of service ids")
            values[key] = tuple(value)
        elif key == "default_intent":
            if value is not None and not isinstance(value, str):
                raise GatewayConfigError("default_intent must be null or an intent name")
            values[key] = value
        elif key in _NUMERIC:
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise GatewayConfigError(f"{key} must be a number, got {value!r}")
            values[key] = float(value) if _NUMERIC[key] in (float, "float") else int(value)
        else:
            raise GatewayConfigError(f"unknown gateway setting {key!r}")
    return GatewayConfig(**values)


def load_config(path: Path | str | None = None) -> GatewayConfig:
    """Read the ``gateway:`` section; a missing file or section means all defaults."""
    target = Path(path) if path else DEFAULT_LIMITS_PATH
    if not target.exists():
        return GatewayConfig()
    try:
        doc = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise GatewayConfigError(f"cannot read {target}: {exc}") from exc
    section = doc.get("gateway") if isinstance(doc, dict) else None
    if section is not None and not isinstance(section, dict):
        raise GatewayConfigError("the gateway: section must be a mapping")
    return config_from_mapping(section)
