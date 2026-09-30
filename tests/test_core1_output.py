"""The completion format: three header lines (intent, shape, variants) then the Cypher, and the
check that turns a model completion into a query with parameters."""

from __future__ import annotations

import pytest

from citizengraph.core1 import templates as T
from citizengraph.core1.output import (
    HEADER_KEYS,
    check_completion,
    format_completion,
    parse_completion,
)
from citizengraph.core1.targets import Request, Target


def req(*targets, phrase="x"):
    return Request(targets=[Target(kind=k, id=i) for k, i in targets], phrase=phrase, language="en")


SERVICE = req(("service", "business_permit"), ("office", "bplo"))


def test_format_has_three_header_lines_then_the_query():
    t = T.TEMPLATES[("fees", "list", True)]
    text = format_completion(t, ["business_type:corporation", "applicant_type:new"])
    lines = text.splitlines()
    assert lines[0] == "intent: fees"
    assert lines[1] == "shape: list"
    assert lines[2] == "variants: applicant_type:new, business_type:corporation"
    assert "\n".join(lines[3:]) == t.cypher
    assert HEADER_KEYS == ("intent", "shape", "variants")


def test_no_variants_reads_none_and_two_intents_join_with_plus():
    t = T.TEMPLATES[("fees", "fee_time", False)]
    lines = format_completion(t, []).splitlines()
    assert lines[0] == "intent: fees+processing_time" and lines[2] == "variants: none"


def test_variants_are_written_only_for_filtered_templates():
    t = T.TEMPLATES[("steps", "list", False)]
    assert format_completion(t, ["business_type:corporation"]).splitlines()[2] == "variants: none"


@pytest.mark.parametrize(
    "template", list(T.TEMPLATES.values()), ids=lambda t: f"{t.shape}-{t.filtered}"
)
def test_every_template_round_trips(template):
    variants = ["taxpayer:company"] if template.filtered else []
    parsed = parse_completion(format_completion(template, variants))
    assert not parsed.problems
    assert parsed.intents == template.intents and parsed.shape == template.shape
    assert list(parsed.variant_ids) == variants
    assert parsed.cypher == template.cypher


def test_parse_strips_a_code_fence_and_blank_lines():
    t = T.TEMPLATES[("office", "list", False)]
    text = "```cypher\n" + format_completion(t, []) + "\n```\n"
    assert parse_completion(text).cypher == t.cypher and not parse_completion(text).problems


@pytest.mark.parametrize(
    "text",
    [
        "",
        "MATCH (s:Service) RETURN s.id LIMIT 1",
        "intent: fees\nMATCH (s:Service) RETURN s.id LIMIT 1",
        "intent: fees\nshape: list\nMATCH (s:Service) RETURN s.id LIMIT 1",
        "shape: list\nintent: fees\nvariants: none\nMATCH (s:Service) RETURN s.id LIMIT 1",
        "intent: fees\nshape: list\nvariants: none\n",
        "intent: \nshape: list\nvariants: none\nMATCH (s:Service) RETURN s.id LIMIT 1",
    ],
)
def test_malformed_completions_report_problems_and_never_raise(text):
    assert parse_completion(text).problems


def test_the_cypher_is_everything_after_the_header():
    text = "intent: office\nshape: list\nvariants: none\nMATCH (o:Office)\nRETURN o.id\nLIMIT 1"
    assert parse_completion(text).cypher == "MATCH (o:Office)\nRETURN o.id\nLIMIT 1"


# ---- check_completion ----------------------------------------------------------------------


def good(intent, shape, variants=(), filtered=None):
    t = T.TEMPLATES[(intent, shape, bool(variants) if filtered is None else filtered)]
    return format_completion(t, list(variants))


def test_a_canonical_completion_checks_out_with_its_parameters():
    c = check_completion(good("requirements", "list", ["business_type:corporation"]), SERVICE)
    assert c.ok and c.canonical and not c.problems
    assert c.params == {"sid": "business_permit", "variant_ids": ["business_type:corporation"]}
    assert c.template is T.TEMPLATES[("requirements", "list", True)]
    assert c.intents == ("requirements",) and c.shape == "list"


def test_parameters_come_from_what_the_cypher_uses():
    r = req(("office", "bplo"), ("service", "business_permit"))
    c = check_completion(good("office", "office_count"), r)
    assert c.ok and c.params == {"oid": "bplo"}


def test_a_query_the_targets_cannot_supply_is_rejected():
    c = check_completion(
        good("office", "office_services"), SERVICE.model_copy(update={"targets": ()})
    )
    assert not c.ok and any("oid" in p for p in c.problems)
    two = check_completion(good("fees", "compare_fees"), SERVICE)
    assert not two.ok and any("sid2" in p for p in two.problems)


def test_a_rejected_query_never_yields_parameters():
    c = check_completion(
        "intent: fees\nshape: list\nvariants: none\nMATCH (n) DETACH DELETE n", SERVICE
    )
    assert not c.ok and c.params == {}


def test_guardrail_failures_are_reported():
    bad = "intent: fees\nshape: list\nvariants: none\nMATCH (n) RETURN n LIMIT 1"
    c = check_completion(bad, SERVICE)
    assert not c.ok and any("guardrail" in p for p in c.problems)


def test_unknown_and_inconsistent_variants_are_reported():
    text = good("fees", "list", ["business_type:corporation"])
    assert check_completion(text, SERVICE).ok
    fake = text.replace("business_type:corporation", "business_type:llc")
    assert any("llc" in p for p in check_completion(fake, SERVICE).problems)
    # the header says variants but the query has no filter (or the other way round)
    no_filter = good("fees", "list").replace("variants: none", "variants: taxpayer:company")
    assert any("filter" in p for p in check_completion(no_filter, SERVICE).problems)
    filtered_none = good("fees", "list", ["taxpayer:company"]).replace(
        "variants: taxpayer:company", "variants: none"
    )
    assert any("filter" in p for p in check_completion(filtered_none, SERVICE).problems)
    twice = good("fees", "list", ["taxpayer:company"]).replace(
        "variants: taxpayer:company", "variants: taxpayer:company, taxpayer:individual"
    )
    assert any("dimension" in p for p in check_completion(twice, SERVICE).problems)


def test_variants_can_be_checked_against_what_the_service_offers():
    text = good("fees", "list", ["taxpayer:company"])
    offers = {"business_permit": {"business_type": {"corporation"}}}
    c = check_completion(text, SERVICE, service_variants=offers)
    assert not c.ok and any("business_permit" in p for p in c.problems)
    offers = {"business_permit": {"taxpayer": {"company", "individual"}}}
    assert check_completion(text, SERVICE, service_variants=offers).ok


def test_a_valid_but_new_query_runs_but_is_not_canonical():
    text = (
        "intent: office\nshape: list\nvariants: none\n"
        "MATCH (o:Office {id: $oid})-[:OFFERS]->(s:Service)\nRETURN s.id\nLIMIT 3"
    )
    c = check_completion(text, req(("office", "cho")))
    assert c.ok and not c.canonical and c.template is None
    assert c.params == {"oid": "cho"}


def test_header_naming_an_unknown_shape_or_status_is_reported():
    assert check_completion(
        good("fees", "list").replace("shape: list", "shape: bogus"), SERVICE
    ).problems
    status = good("fees", "list").replace("intent: fees", "intent: status")
    assert any("intent" in p for p in check_completion(status, SERVICE).problems)
