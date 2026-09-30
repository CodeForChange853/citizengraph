"""docs/specs.md, the guardrail allow-list, the loader and the seed agree on the graph schema.

Decision (session 3b): the guardrail's property allow-list stays the spec's; the loader's
bookkeeping properties (review_status, source_*, condition_structured, ...) are stored but Core 1
cannot read them. Text-only conditions are returned as `condition_text`.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

from citizengraph.graph.loader import DEFAULT_SEED_DIR, load_seed
from citizengraph.guardrail.schema import OFFICIAL_SCHEMA
from citizengraph.guardrail.validator import validate_cypher

ROOT = Path(__file__).resolve().parents[1]

BOOKKEEPING = {
    "review_status",
    "source_sheet",
    "source_row",
    "source_rows",
    "charter_ref",
    "key",
    "condition_structured",
}


def _loadmod():
    spec = importlib.util.spec_from_file_location(
        "citizengraph_admin_load_sa", ROOT / "graph/load.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def plan():
    return _loadmod().build_plan(load_seed(DEFAULT_SEED_DIR))


def spec_section(number: int) -> str:
    text = (ROOT / "docs" / "specs.md").read_text(encoding="utf-8")
    start = text.index(f"## {number}. ")
    nxt = re.search(r"^## \d+\. ", text[start + 5 :], re.MULTILINE)
    return text[start : start + 5 + nxt.start()] if nxt else text[start:]


class TestRelationshipTypes:
    def test_new_types_are_in_the_guardrail_allow_list(self):
        assert {"CHARGES", "SATISFIED_BY", "IS_OFFICE"} <= OFFICIAL_SCHEMA.relationship_types

    def test_loader_writes_only_allowed_types_and_every_type_but_alias_links(self, plan):
        written = set()
        for batch in plan:
            written |= set(re.findall(r"-\[:(\w+)\]->", batch.cypher))
        assert written <= OFFICIAL_SCHEMA.relationship_types
        assert OFFICIAL_SCHEMA.relationship_types - written == {"KNOWN_AS"}

    def test_specs_section_1_lists_exactly_the_guardrail_types(self):
        types = set(re.findall(r"\[:(\w+)\]", spec_section(1)))
        assert types == OFFICIAL_SCHEMA.relationship_types

    @pytest.mark.parametrize(
        "query",
        [
            "MATCH (s:Step {id: $sid})-[:CHARGES]->(f:Fee) RETURN f.amount_min, f.label LIMIT 5",
            "MATCH (r:Requirement)-[:SATISFIED_BY]->(s:Service) RETURN r.text, s.name LIMIT 5",
            "MATCH (a:Agency)-[:IS_OFFICE]->(o:Office) RETURN a.name, o.name LIMIT 5",
            (
                "MATCH (r:Requirement)-[:SECURED_AT]->(a:Agency)-[:IS_OFFICE]->(o:Office)"
                " RETURN r.text, o.name LIMIT 5"
            ),
        ],
    )
    def test_guardrail_accepts_queries_over_the_new_types(self, query):
        result = validate_cypher(query)
        assert result.ok, result.reasons


class TestPropertyAllowList:
    def test_bookkeeping_properties_are_not_readable_by_core_1(self):
        assert not BOOKKEEPING & OFFICIAL_SCHEMA.properties
        for prop in ("condition_structured", "review_status", "flags", "source_row"):
            result = validate_cypher(f"MATCH (r:Requirement) RETURN r.{prop} LIMIT 5")
            assert not result.ok, prop

    def test_text_only_conditions_are_readable_as_text(self):
        for query in (
            "MATCH (r:Requirement) RETURN r.text, r.condition_text LIMIT 5",
            "MATCH (f:Fee) RETURN f.label, f.condition_text LIMIT 5",
            "MATCH (r:Requirement)-[:APPLIES_WHEN]->(v:Variant) RETURN r.text, v.dimension LIMIT 5",
        ):
            assert validate_cypher(query).ok, query

    def test_everything_the_loader_stores_is_either_specified_or_bookkeeping(self, plan):
        stored = set()
        for batch in plan:
            if batch.name.startswith("node:"):
                for row in batch.rows:
                    stored |= set(row["props"])
        assert stored - OFFICIAL_SCHEMA.properties <= BOOKKEEPING

    def test_specs_section_4_records_the_decision(self):
        text = spec_section(4)
        for word in ("review_status", "condition_structured", "condition_text"):
            assert word in text
