"""The templates-only baseline: the gateway's rule-based intent mapped to the list templates."""

from __future__ import annotations

import pytest
from test_training_common import load

from citizengraph.core1.output import check_completion, parse_completion
from citizengraph.core1.targets import Request, Target

B = load("baseline")


@pytest.fixture(scope="module")
def baseline():
    return B.TemplatesOnlyBaseline()


def svc(phrase, sid="business_permit", office="bplo", language="en"):
    return Request(
        targets=[Target(kind="service", id=sid), Target(kind="office", id=office)],
        phrase=phrase,
        language=language,
    )


def test_it_maps_the_gateways_intent_to_the_list_template(baseline):
    request = svc("what are the requirements for business permit")
    out = baseline.complete(request)
    parsed = parse_completion(out)
    assert parsed.intents == ("requirements",) and parsed.shape == "list" and not parsed.variant_ids
    assert check_completion(out, request).canonical


def test_variants_come_from_the_gateways_cues_and_only_those_the_service_has(baseline):
    request = svc("requirements for business permit corporation")
    parsed = parse_completion(baseline.complete(request))
    assert parsed.variant_ids == ("business_type:corporation",)
    other = svc("requirements for corporation", sid="fishing_permit", office="bplo")
    assert parse_completion(baseline.complete(other)).variant_ids == ()


def test_it_answers_in_filipino_too(baseline):
    out = baseline.complete(svc("magkano ang bayad sa business permit", language="fil"))
    assert parse_completion(out).intents == ("fees",)


def test_it_always_uses_the_list_shape_and_one_intent(baseline):
    for phrase in (
        "how many requirements for business permit",
        "how much and how long is business permit",
        "which is cheaper business permit or occupational permit",
    ):
        parsed = parse_completion(baseline.complete(svc(phrase)))
        if parsed.cypher:
            assert parsed.shape == "list" and len(parsed.intents) == 1


def test_it_has_no_answer_without_a_service_or_a_known_intent(baseline):
    office_only = Request(
        targets=[Target(kind="office", id="bplo")],
        phrase="what services does the business permits office offer",
        language="en",
    )
    assert baseline.complete(office_only) == ""
    doc = Request(
        targets=[Target(kind="document", id="cedula")],
        phrase="which services require cedula",
        language="en",
    )
    assert baseline.complete(doc) == ""
    assert baseline.complete(svc("asdf qwer zxcv")) == ""


def test_a_status_question_is_not_a_core1_answer(baseline):
    assert baseline.complete(svc("asa na ang permit ko")) == ""
