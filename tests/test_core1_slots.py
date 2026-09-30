"""Slots: the sub-request vocabulary shared by every session."""

import pytest
from pydantic import ValidationError

from citizengraph.core1.slots import INTENTS, LANGUAGES, Slots, check_variants, known_variants


def make(**over):
    base = {
        "service_id": "business_permit",
        "intent": "requirements",
        "variants": {},
        "phrase": "what do i need for a business permit",
        "language": "en",
    }
    base.update(over)
    return Slots(**base)


def test_shared_vocabulary_is_exact():
    assert INTENTS == (
        "requirements",
        "fees",
        "steps",
        "processing_time",
        "where_to_secure",
        "who_may_avail",
        "office",
        "status",
    )
    assert LANGUAGES == ("en", "fil", "mixed")


def test_field_names_are_the_shared_vocabulary():
    assert list(Slots.model_fields) == ["service_id", "intent", "variants", "phrase", "language"]


def test_variants_default_to_empty():
    s = Slots(service_id="business_permit", intent="fees", phrase="x", language="fil")
    assert s.variants == {}
    assert s.variant_ids == []


def test_variant_ids_are_sorted_dimension_value_pairs():
    s = make(variants={"business_type": "corporation", "applicant_type": "new"})
    assert s.variant_ids == ["applicant_type:new", "business_type:corporation"]


@pytest.mark.parametrize(
    "over",
    [
        {"intent": "delete_everything"},
        {"intent": ""},
        {"language": "waray"},
        {"service_id": ""},
        {"service_id": "Business Permit"},
        {"service_id": "x'; MATCH (n) DETACH DELETE n //"},
        {"phrase": ""},
        {"phrase": "   "},
        {"variants": {"Business Type": "corporation"}},
        {"variants": {"business_type": ""}},
        {"variants": {"business_type": "corp:oration"}},
        {"variants": {"business_type": 3}},
        {"variants": ["business_type"]},
    ],
)
def test_bad_slots_are_rejected(over):
    with pytest.raises(ValidationError):
        make(**over)


def test_extra_fields_are_rejected():
    with pytest.raises(ValidationError):
        make(shape="count")


def test_slots_are_frozen():
    s = make()
    with pytest.raises(ValidationError):
        s.intent = "fees"


def test_status_is_a_valid_intent_even_though_core1_has_no_template_for_it():
    assert make(intent="status").intent == "status"


def test_known_variants_come_from_the_seed_file():
    known = known_variants()
    assert known["business_type"] >= {"single_proprietor", "corporation", "association"}
    assert known["foreign_parent"] == {"yes"}
    assert "2C" in known["cockfight_category"]


def test_check_variants_reports_unknown_dimensions_and_values():
    assert check_variants({"business_type": "corporation"}) == []
    problems = check_variants({"business_type": "llc", "colour": "red"})
    assert len(problems) == 2
    assert any("llc" in p for p in problems)
    assert any("colour" in p for p in problems)


def test_check_variants_takes_an_explicit_vocabulary():
    assert check_variants({"a": "b"}, known={"a": {"b"}}) == []
    assert check_variants({"a": "c"}, known={"a": {"b"}})
