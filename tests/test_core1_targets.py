"""Targets: what the gateway linked (service, office, agency, document) and the query parameters
they become."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from citizengraph.core1 import templates as T
from citizengraph.core1.targets import (
    Request,
    Target,
    build_request_query,
    params_for,
    parse_targets,
    render_targets,
)
from citizengraph.guardrail.validator import validate_cypher


def req(*targets, phrase="x", language="en"):
    return Request(
        targets=[Target(kind=k, id=i) for k, i in targets], phrase=phrase, language=language
    )


def test_targets_render_in_a_fixed_order_whatever_the_input_order():
    r = req(("document", "cedula"), ("office", "bplo"), ("service", "business_permit"))
    assert render_targets(r.targets) == "service:business_permit, office:bplo, document:cedula"
    assert render_targets(()) == "none"


def test_render_and_parse_round_trip():
    targets = req(
        ("service", "business_permit"),
        ("service", "occupational_permit"),
        ("office", "bplo"),
        ("agency", "city-treasurers-office"),
        ("document", "barangay clearance"),
    ).targets
    assert parse_targets(render_targets(targets)) == targets
    assert parse_targets("none") == ()


@pytest.mark.parametrize(
    "bad",
    [
        ("service", "Business Permit"),
        ("service", ""),
        ("office", "bplo; DROP"),
        ("agency", "x'y"),
        ("document", "a\\nb"),
        ("document", "x" * 80),
        ("planet", "mars"),
    ],
)
def test_bad_targets_are_rejected(bad):
    with pytest.raises(ValidationError):
        Target(kind=bad[0], id=bad[1])


def test_a_request_cannot_have_two_offices_three_services_or_blank_phrase():
    with pytest.raises(ValidationError):
        req(("office", "bplo"), ("office", "cho"))
    with pytest.raises(ValidationError):
        req(("service", "a"), ("service", "b"), ("service", "c"))
    with pytest.raises(ValidationError):
        req(("service", "a"), ("service", "a"))
    with pytest.raises(ValidationError):
        req(("service", "business_permit"), phrase="  ")


def test_parameters_follow_the_contract():
    r = req(
        ("service", "business_permit"),
        ("service", "occupational_permit"),
        ("office", "bplo"),
        ("agency", "civil-registry-office"),
        ("document", "cedula"),
    )
    assert params_for(r, ("sid", "sid2", "oid", "aid", "doc"), []) == {
        "sid": "business_permit",
        "sid2": "occupational_permit",
        "oid": "bplo",
        "aid": "civil-registry-office",
        "doc": "cedula",
    }
    only = params_for(r, ("oid",), ["business_type:corporation"])
    assert only == {"oid": "bplo", "variant_ids": ["business_type:corporation"]}


def test_missing_parameters_raise():
    with pytest.raises(T.MissingTarget):
        params_for(req(("service", "business_permit")), ("sid", "oid"), [])
    with pytest.raises(T.MissingTarget):
        params_for(req(("service", "business_permit")), ("sid", "sid2"), [])


def test_every_template_can_be_built_from_a_request_that_has_its_targets():
    full = req(
        ("service", "business_permit"),
        ("service", "occupational_permit"),
        ("office", "bplo"),
        ("agency", "civil-registry-office"),
        ("document", "cedula"),
    )
    for (intent, shape, filtered), template in T.TEMPLATES.items():
        variants = ["business_type:corporation"] if filtered else []
        q = build_request_query(full, intent, shape, variants)
        assert q.cypher == template.cypher
        assert set(q.params) == set(template.params)
        assert validate_cypher(q.cypher).ok


def test_variant_ids_without_a_filtered_template_are_ignored():
    q = build_request_query(req(("service", "business_permit")), "steps", "list", ["a:b"])
    assert "variant_ids" not in q.params and "$variant_ids" not in q.cypher


def test_filtered_template_is_chosen_only_when_variants_are_given():
    r = req(("service", "business_permit"))
    assert "variant_ids" not in build_request_query(r, "fees", "fees_total", []).params
    q = build_request_query(r, "fees", "fees_total", ["taxpayer:company"])
    assert q.params["variant_ids"] == ["taxpayer:company"]


def test_unknown_shape_or_status_intent_is_an_error():
    r = req(("service", "business_permit"))
    with pytest.raises(ValueError):
        build_request_query(r, "fees", "no_such_shape", [])
    with pytest.raises(T.NotCore1Intent):
        build_request_query(r, "status", "list", [])


class _Sub:  # shaped like the gateway's SubRequest
    service_id = "cho_sanitary_permit"
    office_id = "cho"
    phrase = "how much is the sanitary permit"
    language = "en"


def test_a_gateway_sub_request_becomes_a_request_with_service_and_office():
    r = Request.from_sub_request(_Sub())
    assert render_targets(r.targets) == "service:cho_sanitary_permit, office:cho"
    assert r.language == "en" and r.phrase.startswith("how much")
    _Sub.service_id = None
    _Sub.office_id = None
    try:
        assert Request.from_sub_request(_Sub()).targets == ()
    finally:
        _Sub.service_id = "cho_sanitary_permit"
        _Sub.office_id = "cho"
