"""Canonical Cypher templates: one source of truth for Core 1 (and its fallback / baseline)."""

from __future__ import annotations

import dataclasses
import re
from collections import defaultdict
from pathlib import Path

import pytest
import yaml

from citizengraph.core1 import templates as T
from citizengraph.core1.slots import INTENTS, Slots
from citizengraph.graph import InMemoryGraph
from citizengraph.guardrail.lexer import PARAM, STRING, tokenize
from citizengraph.guardrail.schema import OFFICIAL_SCHEMA, Schema
from citizengraph.guardrail.validator import validate_cypher

ROOT = Path(__file__).resolve().parents[1]
ALL = sorted(T.TEMPLATES.values(), key=lambda t: t.key)


def slots(intent="requirements", variants=None, service_id="business_permit"):
    return Slots(
        service_id=service_id,
        intent=intent,
        variants=variants or {},
        phrase="x",
        language="en",
    )


def params_in(cypher: str) -> set[str]:
    return {t.value.lstrip("$") for t in tokenize(cypher) if t.kind == PARAM}


def ids(t: T.Template) -> str:
    return f"{t.intent}-{t.shape}-{'filtered' if t.filtered else 'plain'}"


# ---- every template passes the guardrail (the rule this module lives by) ----------------------


@pytest.mark.parametrize("template", ALL, ids=ids)
def test_every_template_passes_the_guardrail(template):
    result = validate_cypher(template.cypher)
    assert result.ok, result.reasons


@pytest.mark.parametrize("template", ALL, ids=ids)
def test_templates_contain_no_literal_ids(template):
    assert not [t for t in tokenize(template.cypher) if t.kind == STRING]
    seed_words = {s.id for s in InMemoryGraph.from_dir().services()}
    assert not [w for w in seed_words if w in template.cypher]


# ---- parameter contract ------------------------------------------------------------------------


@pytest.mark.parametrize("template", ALL, ids=ids)
def test_parameters_are_exactly_the_documented_ones(template):
    used = params_in(template.cypher)
    assert used <= set(T.PARAMETERS)
    assert template.params == tuple(sorted(used))
    assert used - {"variant_ids"}, "every template needs at least one target parameter"
    assert ("variant_ids" in used) == template.filtered
    assert template.needs == tuple(sorted(used - {"variant_ids"}))


def test_the_contract_is_documented_in_the_module():
    doc = T.__doc__ or ""
    for needle in (
        "$sid",
        "$sid2",
        "$oid",
        "$aid",
        "$doc",
        "$variant_ids",
        "dimension:value",
        "Service.id",
        "Office.id",
        "Agency.id",
    ):
        assert needle in doc


# ---- coverage ----------------------------------------------------------------------------------


def test_every_core1_intent_has_a_plain_list_template():
    assert T.CORE1_INTENTS == tuple(i for i in INTENTS if i != "status")
    for intent in T.CORE1_INTENTS:
        assert (intent, "list", False) in T.TEMPLATES


def test_the_required_multi_hop_shapes_exist():
    text = {(t.intent, t.shape): t.cypher for t in ALL}
    assert "[:CHARGES]" in text[("fees", "per_step")]
    go_first = text[("where_to_secure", "go_first")]
    assert "[:SATISFIED_BY]" in go_first and "[:IS_OFFICE]" in go_first
    assert "count(" in text[("requirements", "count")]
    assert "count(" in text[("steps", "count")]


def test_variant_filters_exist_only_where_the_graph_can_filter():
    filtered = {(t.intent, t.shape) for t in ALL if t.filtered}
    assert filtered == {
        ("requirements", "list"),
        ("requirements", "count"),
        ("requirements", "doc_in_service"),
        ("fees", "list"),
        ("fees", "per_step"),
        ("fees", "fees_total"),
        ("fees", "fee_time"),
        ("where_to_secure", "list"),
        ("where_to_secure", "go_first"),
    }
    for intent, shape in filtered:
        assert T.supports_variants(intent, shape)
        assert (intent, shape, False) in T.TEMPLATES
    assert not T.supports_variants("steps", "list")
    assert not T.supports_variants("office", "list")
    assert not T.supports_variants("fees", "compare_fees")


def test_there_are_at_least_ten_new_shapes_with_different_cypher():
    assert len(T.NEW_SHAPES) >= 10 and len(set(T.NEW_SHAPES)) == len(T.NEW_SHAPES)
    assert not set(T.NEW_SHAPES) & set(T.LEGACY_SHAPES)
    new = {t.shape: t for t in ALL if not t.filtered and t.shape in T.NEW_SHAPES}
    assert set(new) == set(T.NEW_SHAPES)
    legacy = {t.cypher for t in ALL if t.shape in T.LEGACY_SHAPES}
    assert not {t.cypher for t in new.values()} & legacy


def test_the_new_shapes_use_the_extended_parameters():
    needs = {t.shape: t.needs for t in ALL if not t.filtered}
    assert needs["doc_services"] == ("doc",)
    assert needs["doc_where"] == ("doc",)
    assert needs["doc_in_service"] == ("doc", "sid")
    assert needs["agency_services"] == ("aid",)
    for shape in ("office_services", "office_count", "office_req_counts", "office_who"):
        assert needs[shape] == ("oid",)
    assert needs["office_prereqs"] == ("oid",)
    assert needs["cheapest"] == needs["no_fee_rows"] == ("oid",)
    for shape in ("compare_fees", "compare_requirements", "compare_time"):
        assert needs[shape] == ("sid", "sid2")
    for shape in ("fees_total", "fee_time", "longest_step", "external_steps"):
        assert needs[shape] == ("sid",)


def test_the_new_shapes_cover_the_requested_question_families():
    text = {t.shape: t.cypher for t in ALL if not t.filtered}
    assert "CONTAINS $doc" in text["doc_services"]  # which services require a document
    assert "SECURED_AT" in text["agency_services"]  # which services need an agency
    assert "OFFERS" in text["office_services"] and "count(s)" in text["office_count"]
    assert "SATISFIED_BY" in text["office_prereqs"] and "IS_OFFICE" in text["office_prereqs"]
    assert "min(f.amount_min)" in text["cheapest"]
    assert "NOT EXISTS" in text["no_fee_rows"]
    assert "sum(f.amount_min)" in text["fees_total"]
    assert "CHARGES" in text["fee_time"] and "dur_max" in text["fee_time"]
    assert "ORDER BY st.minutes_max DESC" in text["longest_step"]
    assert "external_agency IS NOT NULL" in text["external_steps"]
    assert "$sid2" in text["compare_fees"] and "$sid2" in text["compare_time"]
    assert "who_may_avail" in text["office_who"]


def test_a_shape_that_serves_two_intents_says_so():
    t = T.TEMPLATES[("fees", "fee_time", False)]
    assert t.intents == ("fees", "processing_time") and t.intent_header == "fees+processing_time"
    assert T.TEMPLATES[("fees", "list", False)].intent_header == "fees"
    assert {t.intent_header for t in ALL if "+" in t.intent_header} == {"fees+processing_time"}


def test_v1_builders_refuse_shapes_that_need_more_than_a_service():
    with pytest.raises(T.MissingTarget):
        T.build_query(slots("office"), "office_services")
    with pytest.raises(T.MissingTarget):
        T.build_query(slots("fees"), "compare_fees")
    assert T.build_query(slots("fees"), "fees_total").params == {"sid": "business_permit"}


def test_templates_are_distinct():
    texts = [t.cypher for t in ALL]
    assert len(set(texts)) == len(texts)


def test_row_limit_fits_the_configured_maximum():
    limits = yaml.safe_load((ROOT / "config" / "limits.yaml").read_text(encoding="utf-8"))
    assert T.ROW_LIMIT <= limits["core1"]["cypher_limit_max"]
    for t in ALL:
        assert re.search(r"LIMIT \d+\Z", t.cypher)


def test_ordered_queries_do_not_break_ties_on_unordered_properties():
    # every list-like query ends in ORDER BY on ids or an explicit key, so results are comparable
    for t in ALL:
        if "LIMIT 1" not in t.cypher and "count(" not in t.cypher:
            assert "ORDER BY" in t.cypher, t.key


def test_the_seed_fits_in_the_row_limit():
    graph = InMemoryGraph.from_dir()
    for s in graph.services():
        assert len(graph.requirements(s.id)) <= T.ROW_LIMIT
        assert len(graph.fees(s.id)) <= T.ROW_LIMIT
        assert len(graph.steps(s.id)) <= T.ROW_LIMIT


# ---- selection ---------------------------------------------------------------------------------


def test_status_is_not_a_core1_intent():
    with pytest.raises(T.NotCore1Intent):
        T.select_template(slots("status"))


def test_unknown_shape_is_an_error():
    with pytest.raises(ValueError):
        T.select_template(slots("office"), shape="count")


def test_select_uses_the_filtered_template_only_when_variants_are_given_and_supported():
    assert not T.select_template(slots("requirements")).filtered
    assert T.select_template(slots("requirements", {"business_type": "corporation"})).filtered
    assert T.select_template(slots("fees", {"taxpayer": "company"}), "per_step").filtered
    # the graph has no variant links on steps: the variants are ignored, not turned into a filter
    assert not T.select_template(slots("steps", {"business_type": "corporation"})).filtered


def test_build_query_returns_the_documented_parameters():
    q = T.build_query(
        slots("requirements", {"business_type": "corporation", "applicant_type": "new"})
    )
    assert q.params == {
        "sid": "business_permit",
        "variant_ids": ["applicant_type:new", "business_type:corporation"],
    }
    assert validate_cypher(q.cypher).ok
    plain = T.build_query(slots("steps", {"business_type": "corporation"}))
    assert plain.params == {"sid": "business_permit"}


def test_query_text_never_depends_on_the_service_or_variant_values():
    a = T.build_query(slots("fees", {"taxpayer": "company"}, "occupational_permit"))
    b = T.build_query(slots("fees", {"business_type": "association"}, "business_permit"))
    assert a.cypher == b.cypher


# ---- the schema is read at runtime -------------------------------------------------------------


def test_a_property_removed_from_the_schema_disappears_from_the_templates():
    smaller = Schema(
        labels=OFFICIAL_SCHEMA.labels,
        relationship_types=OFFICIAL_SCHEMA.relationship_types,
        properties=OFFICIAL_SCHEMA.properties - {"min_required", "note"},
    )
    built = T.build_templates(smaller)
    assert built.keys() == T.TEMPLATES.keys()
    joined = "\n".join(t.cypher for t in built.values())
    assert "min_required" not in joined and "note" not in joined
    assert "min_required" in "\n".join(t.cypher for t in T.TEMPLATES.values())
    for t in built.values():
        assert validate_cypher(t.cypher, schema=smaller).ok


def test_the_property_catalog_covers_the_whole_allow_list():
    """If this fails, a property was added to guardrail/schema.py: say which label owns it in
    NODE_PROPERTIES (core1/templates.py); the templates and prompts then follow by themselves."""
    catalogued = {p for props in T.NODE_PROPERTIES.values() for p in props}
    assert catalogued == set(OFFICIAL_SCHEMA.properties)
    assert set(T.NODE_PROPERTIES) == set(OFFICIAL_SCHEMA.labels)
    assert {rel for _, rel, _ in T.RELATIONSHIPS} == set(OFFICIAL_SCHEMA.relationship_types)


def test_usage_reports_what_each_intent_needs():
    labels, rels, props = T.usage("fees")
    assert {"Service", "Fee", "Step", "Variant"} <= labels
    assert {"HAS_FEE", "CHARGES", "APPLIES_WHEN", "HAS_STEP"} <= rels
    assert {"amount_min", "amount_max", "dimension"} <= props
    labels, rels, props = T.usage("office")
    assert labels == {"Office", "Service"} and rels == {"OFFERS"}
    assert props == {"id", "name"}


# ---- the variant filter means what InMemoryGraph means -----------------------------------------
# No Neo4j here, so the filter's logic is restated in Python, literally as the Cypher reads
# (drop a record when it links a variant whose dimension the caller gave and none of the
# record's links in that dimension was asked for). The real-Neo4j comparison is in
# test_core1_templates_integration.py.


def cypher_filter_keeps(record_variant_ids: list[str], asked: list[str], catalogue) -> bool:
    by_id = {v.id: v for v in catalogue}
    for vid in record_variant_ids:  # MATCH (r)-[:APPLIES_WHEN]->(v:Variant)
        v = by_id[vid]
        dimension_given = any(by_id[x].dimension == v.dimension for x in asked)  # EXISTS x
        asked_link_same_dimension = any(  # EXISTS w
            w in asked and by_id[w].dimension == v.dimension for w in record_variant_ids
        )
        if dimension_given and not asked_link_same_dimension:
            return False  # NOT EXISTS { ... } fails
    return True


def test_the_filter_logic_agrees_with_the_in_memory_graph_on_every_combination():
    graph = InMemoryGraph.from_dir()
    catalogue = graph.seed.variants
    by_dimension: dict[str, list[str]] = defaultdict(list)
    for v in catalogue:
        by_dimension[v.dimension].append(v.value)
    # every selection of at most one value per dimension, including dimensions a service
    # does not link at all (they must not filter anything)
    combos: list[dict[str, str]] = [{}]
    for dimension, values in by_dimension.items():
        combos += [{**c, dimension: value} for c in combos for value in values]
    checked = 0
    for svc in graph.seed.services:
        requirements = [r for r in graph.seed.requirements if r.service_id == svc.id]
        fees = [f for f in graph.seed.fees if f.service_id == svc.id]
        for combo in combos:
            asked = sorted(f"{d}:{value}" for d, value in combo.items())
            for records, want in (
                (requirements, graph.requirements(svc.id, combo)),
                (fees, graph.fees(svc.id, combo)),
            ):
                got = {
                    x.id for x in records if cypher_filter_keeps(x.variant_ids, asked, catalogue)
                }
                assert got == {x.id for x in want}, (svc.id, combo)
            checked += 1
    assert checked > 1000


def test_templates_are_frozen():
    t = ALL[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        t.cypher = "MATCH (n) RETURN n LIMIT 1"
