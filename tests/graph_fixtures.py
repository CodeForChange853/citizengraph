"""A tiny, valid seed (as parsed YAML) that graph tests copy and then break on purpose.

Everything here is invented test data, not charter data.
"""

from __future__ import annotations

import copy
import re
from typing import Any

SRC = {"file": "TEST.xlsx", "sheet": "T", "rows": [10, 40]}


def _common(**extra: Any) -> dict[str, Any]:
    return {"review_status": "needs_review", "flags": [], **extra}


def _duration(lo: float | None = None, hi: float | None = None, unit: str | None = None) -> dict:
    if lo is None:
        return {"status": "not_stated", "day_type": "unknown", "raw": "- - -"}
    unit_minutes = {"minute": 1, "hour": 60, "day": 1440}[unit or "minute"]
    return {
        "status": "stated",
        "value_min": lo,
        "value_max": hi,
        "unit": unit,
        "minutes_min": lo * unit_minutes,
        "minutes_max": hi * unit_minutes,
        "day_type": "unknown",
        "raw": f"{lo}-{hi} {unit}",
    }


def minimal_seed_raw() -> dict[str, list[dict[str, Any]]]:
    """Return a fresh copy each call so tests can mutate it freely."""
    raw: dict[str, list[dict[str, Any]]] = {
        "offices": [_common(id="o1", name="Test Office", sources=[SRC])],
        "links": [
            _common(
                id="link-01",
                kind="agency_is_office",
                requirement_id=None,
                agency="Some Agency",
                service_id=None,
                office_id="o1",
                sources=[SRC],
            )
        ],
        "variants": [
            _common(id="taxpayer:company", dimension="taxpayer", value="company", sources=[SRC]),
            _common(
                id="taxpayer:individual", dimension="taxpayer", value="individual", sources=[SRC]
            ),
            _common(
                id="birth_status:non_marital",
                dimension="birth_status",
                value="non_marital",
                sources=[SRC],
            ),
        ],
        "services": [
            _common(
                id="svc",
                office_id="o1",
                charter_ref="T-01",
                name="Test Service",
                classification="SIMPLE",
                transaction_type="G2C",
                who_may_avail=None,
                total_fee_text="P100",
                total_time_text="10 minutes",
                description=None,
                source=SRC,
                total_source_row=40,
            )
        ],
        "requirements": [
            _common(
                id="svc-R01",
                service_id="svc",
                key="1",
                text="Plain requirement",
                group=False,
                parent_id=None,
                min_required=None,
                condition_text=None,
                condition_structured=None,
                variant_ids=[],
                secured_at="Some Agency",
                source=SRC,
                source_row=20,
            ),
            _common(
                id="svc-R02",
                service_id="svc",
                key="2",
                text="Company documents:",
                group=True,
                parent_id=None,
                min_required=1,
                condition_text="Company:",
                condition_structured=True,
                variant_ids=["taxpayer:company"],
                secured_at=None,
                source=SRC,
                source_row=21,
            ),
            _common(
                id="svc-R03",
                service_id="svc",
                key=None,
                text="Company registration",
                group=False,
                parent_id="svc-R02",
                min_required=None,
                condition_text="Company:",
                condition_structured=True,
                variant_ids=["taxpayer:company"],
                secured_at="Other Agency",
                source=SRC,
                source_row=22,
            ),
            _common(
                id="svc-R04",
                service_id="svc",
                key="3",
                text="Something only sometimes",
                group=False,
                parent_id=None,
                min_required=None,
                condition_text="if applicable",
                condition_structured=False,
                variant_ids=[],
                secured_at=None,
                source=SRC,
                source_row=23,
            ),
            _common(
                id="svc-R05",
                service_id="svc",
                key="4",
                text="Affidavit",
                group=False,
                parent_id=None,
                min_required=None,
                condition_text="if the parents are not married",
                condition_structured=True,
                variant_ids=["birth_status:non_marital"],
                secured_at="Some Agency",
                source=SRC,
                source_row=24,
            ),
        ],
        "steps": [
            _common(
                id="svc-S01",
                service_id="svc",
                order=1,
                label="1.",
                citizen_step_group=1,
                citizen_action="Submit documents",
                agency_action="Check documents",
                external_agency=None,
                duration=_duration(2, 2, "minute"),
                role="Registration Officer",
                internal_person_raw="Juan Dela Cruz",
                next_id="svc-S02",
                duration_shared_from=None,
                source=SRC,
                source_row=30,
            ),
            _common(
                id="svc-S02",
                service_id="svc",
                order=2,
                label="2.",
                citizen_step_group=2,
                citizen_action="Pay",
                agency_action="Receive payment",
                external_agency="City Treasurer's Office",
                duration=_duration(),
                role=None,
                internal_person_raw="Maria Santos",
                next_id="svc-S03",
                duration_shared_from=None,
                source=SRC,
                source_row=31,
            ),
            _common(
                id="svc-S03",
                service_id="svc",
                order=3,
                label="3.",
                citizen_step_group=3,
                citizen_action=None,
                agency_action="Release",
                external_agency=None,
                duration=_duration(3, 5, "minute"),
                role="Registration Officer",
                internal_person_raw="Registration Officer",
                next_id=None,
                duration_shared_from=None,
                source=SRC,
                source_row=32,
            ),
        ],
        "fees": [
            _common(
                id="svc-F01",
                service_id="svc",
                step_id="svc-S01",
                label="Filing",
                amount_min=100,
                amount_max=100,
                unit=None,
                note=None,
                condition_text=None,
                condition_structured=None,
                variant_ids=[],
                source=SRC,
                source_row=30,
            ),
            _common(
                id="svc-F02",
                service_id="svc",
                step_id="svc-S02",
                label="Tax",
                amount_min=120,
                amount_max=120,
                unit=None,
                note=None,
                condition_text="(company)",
                condition_structured=True,
                variant_ids=["taxpayer:company"],
                source=SRC,
                source_row=31,
            ),
            _common(
                id="svc-F03",
                service_id="svc",
                step_id="svc-S02",
                label="Tax",
                amount_min=215,
                amount_max=215,
                unit=None,
                note=None,
                condition_text="(individual)",
                condition_structured=True,
                variant_ids=["taxpayer:individual"],
                source=SRC,
                source_row=31,
            ),
            _common(
                id="svc-F04",
                service_id="svc",
                step_id="svc-S02",
                label="Special case fee",
                amount_min=500,
                amount_max=500,
                unit=None,
                note=None,
                condition_text="only for special cases",
                condition_structured=False,
                variant_ids=[],
                source=SRC,
                source_row=31,
            ),
        ],
    }
    return copy.deepcopy(raw)


def staff_names(seed: Any) -> set[str]:
    """Person names found in the internal-only field of the real seed (never in any output)."""
    roles = {st.role.lower() for st in seed.steps if st.role}
    names: set[str] = set()
    for st in seed.steps:
        raw = st.internal_person_raw or ""
        if raw.lower() in roles:
            continue  # the whole cell is a role title, not a person
        for part in re.split(r"\s+/\s+|\s+or\s+", raw, flags=re.IGNORECASE):
            part = re.sub(r"^(or\s+)?/?\s*", "", part.strip(" /"), flags=re.IGNORECASE)
            if part and not part.lower().startswith("any") and part.lower() not in roles:
                names.add(part)
    return names
