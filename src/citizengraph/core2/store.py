"""The two stores Core 2 owns. Neither is the charter graph and neither touches Neo4j.

* ``WorkflowStore``: simulated applications and a role-absence roster. Tools only read it.
* ``AlertStore``: drafted alerts, kept in memory or in one JSONL file. ``draft_alert`` is the
  only writer.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, field_validator

from citizengraph.core2.calendar import as_date
from citizengraph.core2.models import ALERT_KINDS, AUDIENCE, Application


class WorkflowStore:
    def __init__(self) -> None:
        self._apps: dict[str, Application] = {}
        self._absent: dict[str, dict[date, str]] = {}

    # applications

    def add(self, app: Application) -> None:
        if app.app_id in self._apps:
            raise ValueError(f"duplicate application id {app.app_id}")
        self._apps[app.app_id] = app

    def get(self, app_id: str) -> Application | None:
        return self._apps.get(app_id)

    def find(self, ref: str) -> list[Application]:
        """Applications whose reference code or citizen pseudonym equals ``ref``."""
        return [a for a in self._apps.values() if ref in (a.ref, a.citizen_ref)]

    def all(self) -> list[Application]:
        return sorted(self._apps.values(), key=lambda a: a.app_id)

    # role roster (simulated leave and absences)

    def set_absent(self, role: str, day: date | datetime, reason: str = "absent") -> None:
        self._absent.setdefault(role, {})[as_date(day)] = reason

    def absence(self, role: str, day: date | datetime) -> str | None:
        return self._absent.get(role, {}).get(as_date(day))

    # serialization

    def to_json(self) -> str:
        return json.dumps(
            {
                "applications": [a.model_dump(mode="json") for a in self.all()],
                "absences": {
                    role: {d.isoformat(): why for d, why in sorted(days.items())}
                    for role, days in sorted(self._absent.items())
                },
            },
            indent=1,
            sort_keys=True,
        )

    @classmethod
    def from_json(cls, text: str) -> WorkflowStore:
        data = json.loads(text)
        store = cls()
        for raw in data.get("applications", []):
            store.add(Application.model_validate(raw))
        for role, days in data.get("absences", {}).items():
            for d, why in days.items():
                store.set_absent(role, date.fromisoformat(d), why)
        return store


class Alert(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    alert_id: str
    app_id: str
    kind: str
    audience: str
    text_en: str
    text_fil: str  # NEEDS-NATIVE-REVIEW (draft wording, see docs/core2_notes.md)
    created_at: datetime
    status: str = "draft"

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, v: str) -> str:
        if v not in ALERT_KINDS:
            raise ValueError(f"unknown alert kind {v!r}")
        return v

    @field_validator("audience")
    @classmethod
    def _known_audience(cls, v: str) -> str:
        if v not in set(AUDIENCE.values()):
            raise ValueError(f"unknown audience {v!r}")
        return v


class AlertStore:
    """Append-only alert drafts. One alert per (application, kind)."""

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path) if path else None
        self._alerts: list[Alert] = []
        if self._path and self._path.exists():
            for line in self._path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    self._alerts.append(Alert.model_validate_json(line))

    def all(self) -> list[Alert]:
        return list(self._alerts)

    def find(self, app_id: str, kind: str) -> Alert | None:
        return next((a for a in self._alerts if a.app_id == app_id and a.kind == kind), None)

    def add(self, alert: Alert) -> bool:
        """Store ``alert``; False (and nothing written) when that app and kind already exist."""
        if self.find(alert.app_id, alert.kind) is not None:
            return False
        self._alerts.append(alert)
        if self._path:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(alert.model_dump_json() + "\n")
        return True
