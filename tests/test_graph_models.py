"""Strict seed models: unknown keys, bad values and inconsistent records are rejected."""

from __future__ import annotations

import json
from typing import Any

import pytest
from graph_fixtures import minimal_seed_raw
from pydantic import ValidationError

from citizengraph.graph.models import (
    Duration,
    Fee,
    Link,
    Office,
    Requirement,
    Service,
    SourceRef,
    Step,
    Variant,
)


def first(kind: str) -> dict[str, Any]:
    return minimal_seed_raw()[kind][0]


@pytest.mark.parametrize(
    ("kind", "model"),
    [
        ("offices", Office),
        ("services", Service),
        ("requirements", Requirement),
        ("steps", Step),
        ("fees", Fee),
        ("variants", Variant),
        ("links", Link),
    ],
)
def test_valid_records_parse_and_unknown_keys_are_rejected(kind, model):
    rec = first(kind)
    model.model_validate(rec)
    with pytest.raises(ValidationError):
        model.model_validate({**rec, "surprise": 1})


@pytest.mark.parametrize(
    ("kind", "model"),
    [
        ("offices", Office),
        ("services", Service),
        ("requirements", Requirement),
        ("steps", Step),
        ("fees", Fee),
        ("variants", Variant),
        ("links", Link),
    ],
)
def test_review_status_is_required_and_limited(kind, model):
    rec = first(kind)
    del rec["review_status"]
    with pytest.raises(ValidationError):
        model.model_validate(rec)
    with pytest.raises(ValidationError):
        model.model_validate({**first(kind), "review_status": "approved"})


@pytest.mark.parametrize("kind", ["services", "requirements", "steps", "fees"])
def test_block_records_need_a_source_reference(kind):
    model = {"services": Service, "requirements": Requirement, "steps": Step, "fees": Fee}[kind]
    rec = first(kind)
    del rec["source"]
    with pytest.raises(ValidationError):
        model.model_validate(rec)


def test_source_ref_rows_must_be_an_ordered_pair_of_positive_ints():
    SourceRef.model_validate({"file": "a.xlsx", "sheet": "S", "rows": [3, 3]})
    for bad in ([5, 2], [0, 4], [1], [1, 2, 3], ["a", "b"]):
        with pytest.raises(ValidationError):
            SourceRef.model_validate({"file": "a.xlsx", "sheet": "S", "rows": bad})


def test_variant_id_must_be_dimension_colon_value():
    Variant.model_validate(first("variants"))
    with pytest.raises(ValidationError):
        Variant.model_validate({**first("variants"), "id": "something-else"})


class TestDuration:
    def test_stated_needs_values_and_unit(self):
        d = Duration(status="stated", value_min=5, value_max=10, unit="minute", raw="5-10 minutes")
        assert d.day_type == "unknown"
        with pytest.raises(ValidationError):
            Duration(status="stated", value_min=5, value_max=10)
        with pytest.raises(ValidationError):
            Duration(status="stated", unit="minute")

    def test_not_stated_and_unparsed_carry_no_numbers(self):
        Duration(status="not_stated", raw="- - -")
        Duration(status="unparsed", raw="asap")
        with pytest.raises(ValidationError):
            Duration(status="not_stated", value_min=1, value_max=1, unit="minute")
        with pytest.raises(ValidationError):
            Duration(status="unparsed", minutes_min=3)

    def test_range_must_be_ordered_and_non_negative(self):
        with pytest.raises(ValidationError):
            Duration(status="stated", value_min=10, value_max=5, unit="minute")
        with pytest.raises(ValidationError):
            Duration(status="stated", value_min=-1, value_max=5, unit="minute")

    def test_unit_and_day_type_are_closed_sets(self):
        with pytest.raises(ValidationError):
            Duration(status="stated", value_min=1, value_max=1, unit="fortnight")
        with pytest.raises(ValidationError):
            Duration(status="not_stated", day_type="business")
        Duration(status="not_stated", day_type="working")


class TestRequirement:
    def test_variants_need_the_original_condition_wording(self):
        rec = {**first("requirements"), "variant_ids": ["taxpayer:company"]}
        with pytest.raises(ValidationError):
            Requirement.model_validate(rec)

    def test_structured_flag_must_match_the_condition(self):
        base = first("requirements")
        # no condition at all: the flag must be null
        with pytest.raises(ValidationError):
            Requirement.model_validate({**base, "condition_structured": True})
        # condition without variant links cannot claim to be structured
        with pytest.raises(ValidationError):
            Requirement.model_validate(
                {**base, "condition_text": "if x", "condition_structured": True}
            )
        # condition without a flag is undecided and therefore rejected
        with pytest.raises(ValidationError):
            Requirement.model_validate({**base, "condition_text": "if x"})
        Requirement.model_validate(
            {**base, "condition_text": "if x", "condition_structured": False}
        )

    def test_min_required_is_only_for_groups_and_positive(self):
        base = first("requirements")
        with pytest.raises(ValidationError):
            Requirement.model_validate({**base, "min_required": 1})
        group = {**base, "group": True}
        Requirement.model_validate({**group, "min_required": 2})
        with pytest.raises(ValidationError):
            Requirement.model_validate({**group, "min_required": 0})


class TestFee:
    def test_amount_range_ordered_and_non_negative(self):
        base = first("fees")
        Fee.model_validate({**base, "amount_min": 1000, "amount_max": 3000})
        with pytest.raises(ValidationError):
            Fee.model_validate({**base, "amount_min": 3000, "amount_max": 1000})
        with pytest.raises(ValidationError):
            Fee.model_validate({**base, "amount_min": -1, "amount_max": 5})

    def test_amounts_are_required_numbers_never_text(self):
        base = first("fees")
        for bad in ("As determined by the CSWMO", None):
            with pytest.raises(ValidationError):
                Fee.model_validate({**base, "amount_min": bad})
            with pytest.raises(ValidationError):
                Fee.model_validate({**base, "amount_max": bad})


class TestStaffNamesStayInternal:
    def test_internal_person_is_kept_on_the_model_but_never_serialized(self):
        step = Step.model_validate(first("steps"))
        assert step.internal_person_raw == "Juan Dela Cruz"
        assert "internal_person_raw" not in step.model_dump()
        assert "Juan" not in step.model_dump_json()
        assert "Juan" not in json.dumps(step.model_dump(mode="json"))

    def test_steps_need_a_positive_order(self):
        with pytest.raises(ValidationError):
            Step.model_validate({**first("steps"), "order": 0})


class TestLink:
    def satisfied_by(self, **over):
        rec = {
            "id": "link-02",
            "kind": "requirement_satisfied_by",
            "requirement_id": "svc-R01",
            "agency": None,
            "service_id": "other",
            "office_id": None,
            "review_status": "needs_review",
            "flags": [{"code": "link_suggested", "message": "a person must confirm"}],
            "sources": [{"file": "T.xlsx", "sheet": "T", "rows": [1, 9]}],
        }
        return {**rec, **over}

    def test_requirement_satisfied_by_a_service(self):
        link = Link.model_validate(self.satisfied_by())
        assert link.service_id == "other"

    def test_satisfied_by_needs_a_requirement_and_a_service_and_nothing_else(self):
        for bad in (
            {"requirement_id": None},
            {"service_id": None},
            {"agency": "X"},
            {"office_id": "o1"},
        ):
            with pytest.raises(ValidationError):
                Link.model_validate(self.satisfied_by(**bad))

    def test_agency_is_office_needs_an_agency_and_an_office_and_no_service(self):
        base = first("links")
        Link.model_validate(base)
        for bad in ({"agency": None}, {"office_id": None}, {"service_id": "svc"}):
            with pytest.raises(ValidationError):
                Link.model_validate({**base, **bad})

    def test_agency_link_may_name_the_requirement_it_came_from(self):
        Link.model_validate({**first("links"), "requirement_id": "svc-R01"})

    def test_unknown_kind_is_rejected(self):
        with pytest.raises(ValidationError):
            Link.model_validate(self.satisfied_by(kind="related_to"))


def test_weeks_are_a_duration_unit_of_their_own():
    d = Duration(status="stated", value_min=1, value_max=1, unit="week", raw="1 week")
    assert d.unit == "week"
