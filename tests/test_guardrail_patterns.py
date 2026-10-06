"""Guardrail hardening: explicit labels and relationship types, and a maximum query length.

No Neo4j, no model, no network. Every query below is valid Cypher and passes the older
rules (known labels, LIMIT, ...), so a rejection here is caused by the rule under test.

Rules (docs/specs.md section 4, CLAUDE.md decisions log):
- every node pattern carries a label, except a bare variable already bound with a label
  earlier in scope; an anonymous `()` needs a label;
- every relationship pattern names a type: `[r]`, `[]`, `[*]`, `--`, `-->` and `<--` are out;
- both apply inside WHERE, EXISTS and COUNT subqueries and pattern comprehensions;
- `core1.cypher_max_chars` (config/limits.yaml) caps the query length; it fails closed.
"""

from pathlib import Path

import pytest
import yaml

from citizengraph.guardrail import validator
from citizengraph.guardrail.validator import ValidationResult, validate_cypher

LIMITS_YAML = Path(__file__).resolve().parents[1] / "config" / "limits.yaml"
CORE1 = yaml.safe_load(LIMITS_YAML.read_text())["core1"]
MAX_CHARS = CORE1["cypher_max_chars"]


def rejected(query, *fragments: str) -> ValidationResult:
    result = validate_cypher(query)
    assert result.ok is False, f"expected rejection: {query!r}"
    assert result.reasons, "a rejection must carry reasons"
    joined = " | ".join(result.reasons).lower()
    for fragment in fragments:
        assert fragment.lower() in joined, f"{fragment!r} not in reasons: {result.reasons}"
    return result


def accepted(query: str) -> None:
    result = validate_cypher(query)
    assert result.ok is True, f"expected pass: {query!r} -> {result.reasons}"
    assert result.reasons == []


# ------------------------------------------------------------ realistic Core 1 queries

REALISTIC = {
    "requirements_by_service_id": (
        "MATCH (s:Service {id: $sid})-[:REQUIRES]->(r:Requirement) "
        "RETURN r.text, r.group, r.min_required, r.parent_id LIMIT 50"
    ),
    "fees_with_optional_variant": (
        "MATCH (s:Service {id: $sid})-[:HAS_FEE]->(f:Fee) "
        "OPTIONAL MATCH (f)-[:APPLIES_WHEN]->(v:Variant) "
        "RETURN f.label, f.amount_min, f.amount_max, f.unit, v.dimension, v.value LIMIT 30"
    ),
    "steps_ordered": (
        "MATCH (s:Service {id: $sid})-[:HAS_STEP]->(st:Step) "
        "RETURN st.order, st.citizen_action, st.agency_action ORDER BY st.order LIMIT 30"
    ),
    "alias_by_text_and_lang": (
        "MATCH (s:Service)-[:KNOWN_AS]->(al:Alias) "
        "WHERE al.text = $text AND al.lang = $lang RETURN s.id, s.name LIMIT 5"
    ),
    "count_s": ("MATCH (s:Service)-[:HAS_FEE]->(f:Fee) RETURN s.name, count(s) AS n LIMIT 20"),
    "exists_subquery": (
        "MATCH (s:Service) WHERE EXISTS { (s)-[:HAS_FEE]->(:Fee) } RETURN s.name LIMIT 20"
    ),
    "count_subquery": (
        "MATCH (s:Service) RETURN s.name, COUNT { (s)-[:HAS_FEE]->(:Fee) } AS fees LIMIT 20"
    ),
    "office_services": (
        "MATCH (o:Office)-[:OFFERS]->(s:Service) WHERE o.id = $oid RETURN s.name LIMIT 30"
    ),
    "step_roles": (
        "MATCH (s:Service {id: $sid})-[:HAS_STEP]->(st:Step)-[:PERFORMED_BY]->(ro:Role) "
        "RETURN st.order, ro.title ORDER BY st.order LIMIT 30"
    ),
}


@pytest.mark.parametrize("name", list(REALISTIC))
def test_realistic_core1_queries_are_accepted(name):
    accepted(REALISTIC[name])


# ------------------------------------------------------------------- label-less nodes


@pytest.mark.parametrize(
    "query",
    [
        "MATCH (n) RETURN n LIMIT 5",
        "MATCH (n)-[:REQUIRES]->(r:Requirement) RETURN r LIMIT 5",
        "MATCH (s:Service)-[:REQUIRES]->(x) RETURN x LIMIT 5",
        "MATCH (s:Service)-[:REQUIRES|HAS_FEE]->(x) RETURN x LIMIT 10",
        "MATCH (s:Service)<-[:OFFERS]-(o) RETURN o LIMIT 5",
        "MATCH (n {id: 'x'}) RETURN n LIMIT 5",
        "MATCH (n {id: $id}) RETURN n.name LIMIT 5",
        "OPTIONAL MATCH (n) RETURN n LIMIT 5",
        "MATCH (s:Service) MATCH (n) RETURN n LIMIT 5",
        "MATCH (s:Service), (n) RETURN n LIMIT 5",
        "MATCH p = (n)-[:NEXT]->(m:Step) RETURN m LIMIT 5",
        "MATCH (s:Service) OPTIONAL MATCH (s)-[:HAS_STEP]->(t) RETURN t LIMIT 5",
    ],
)
def test_node_without_a_label_is_rejected(query):
    rejected(query, "has no label")


def test_the_reason_names_the_variable():
    rejected("MATCH (s:Service)-[:REQUIRES]->(zork) RETURN zork LIMIT 5", "zork")


@pytest.mark.parametrize(
    "query",
    [
        "MATCH () RETURN 1 AS x LIMIT 5",
        "MATCH ({id: 'x'}) RETURN 1 AS x LIMIT 5",
        "MATCH ({id: $id}) RETURN 1 AS x LIMIT 5",
        "MATCH ()-[:REQUIRES]->(r:Requirement) RETURN r LIMIT 5",
        "MATCH (s:Service)-[:REQUIRES]->() RETURN s LIMIT 5",
        "MATCH (s:Service) WHERE (s)-[:HAS_FEE]->() RETURN s LIMIT 5",
    ],
)
def test_anonymous_node_without_a_label_is_rejected(query):
    rejected(query, "anonymous node pattern")


@pytest.mark.parametrize(
    "query",
    [
        "MATCH (:Service) RETURN 1 AS x LIMIT 5",
        "MATCH (s:Service)-[:REQUIRES]->(:Requirement) RETURN s.name LIMIT 5",
        "MATCH (:Office)-[:OFFERS]->(s:Service) RETURN s.name LIMIT 5",
        "MATCH (:Service {id: $sid})-[:HAS_STEP]->(st:Step) RETURN st.order LIMIT 5",
        "MATCH (s:Service|Office) RETURN s.name LIMIT 5",
    ],
)
def test_anonymous_node_with_a_label_is_accepted(query):
    accepted(query)


def test_the_spec_examples_are_blocked():
    rejected("MATCH (n) RETURN n LIMIT 5")
    rejected("MATCH ()-[r]->() RETURN r LIMIT 5")


@pytest.mark.parametrize(
    "query",
    [
        # a negated label "carries a label" but matches every node that is not a Service
        "MATCH (n:!Service) RETURN n LIMIT 5",
        "MATCH (n:Service|!Office) RETURN n LIMIT 5",
        "MATCH (n:!Service&!Office) RETURN n LIMIT 5",
        "MATCH (s:Service) WHERE s:!Service RETURN s LIMIT 5",
        "MATCH (s:Service)-[:REQUIRES]->(x:!Fee) RETURN x LIMIT 5",
        "MATCH (s:Service)-[:REQUIRES|!HAS_FEE]->(x:Requirement) RETURN x LIMIT 5",
        "MATCH (s:Service)-[r:REQUIRES|!HAS_FEE]->(x:Requirement) RETURN x LIMIT 5",
        (
            "MATCH (s:Service) WHERE EXISTS { (s)-[:REQUIRES|!HAS_FEE]->(:Requirement) } "
            "RETURN s LIMIT 5"
        ),
        "MATCH (s:Service) WHERE (s)-[:HAS_STEP]->(:!Fee) RETURN s LIMIT 5",
    ],
)
def test_negated_label_and_type_expressions_are_rejected(query):
    rejected(query, "negated")


# ---------------------------------------------------------------- untyped relationships


@pytest.mark.parametrize(
    "query",
    [
        "MATCH (s:Service)-[r]->(x:Fee) RETURN x LIMIT 5",
        "MATCH (s:Service)-[]->(x:Fee) RETURN x LIMIT 5",
        "MATCH (s:Service)<-[r]-(o:Office) RETURN o LIMIT 5",
        "MATCH (s:Service)-[]-(o:Office) RETURN o LIMIT 5",
        "MATCH (s:Service)-[*]->(x:Fee) RETURN x LIMIT 5",
        "MATCH (s:Service)-[r*1..3]->(x:Step) RETURN x LIMIT 5",
        "MATCH (s:Service)-[*1..3]->(x:Step) RETURN x LIMIT 5",
        "MATCH (s:Service)-[r {note: 'x'}]->(x:Fee) RETURN x LIMIT 5",
        "MATCH (s:Service)-[:!REQUIRES]->(x:Fee) RETURN x LIMIT 5",
        "MATCH (s:Service)-[r:!REQUIRES]->(x:Fee) RETURN x LIMIT 5",
    ],
)
def test_relationship_without_a_type_is_rejected(query):
    rejected(query, "must specify a type")


@pytest.mark.parametrize(
    "query",
    [
        "MATCH ()-[r]->() RETURN r LIMIT 5",
        "MATCH (s:Service)-->(x:Fee) RETURN x LIMIT 5",
        "MATCH (s:Service)<--(x:Office) RETURN x LIMIT 5",
        "MATCH (s:Service)--(x:Office) RETURN x LIMIT 5",
        "MATCH (s:Service)- -(x:Office) RETURN x LIMIT 5",
        "MATCH (s:Service)- - >(x:Office) RETURN x LIMIT 5",
    ],
)
def test_shorthand_and_empty_relationships_are_rejected(query):
    result = validate_cypher(query)
    assert result.ok is False, query
    joined = " | ".join(result.reasons).lower()
    assert "untyped" in joined or "must specify a type" in joined, result.reasons


@pytest.mark.parametrize(
    "query",
    [
        "MATCH (s:Service)-[:REQUIRES]->(r:Requirement) RETURN r.id LIMIT 5",
        "MATCH (s:Service)-[q:REQUIRES]->(r:Requirement) RETURN r.id LIMIT 5",
        "MATCH (s:Service)<-[:OFFERS]-(o:Office) RETURN o.id LIMIT 5",
        "MATCH (s:Service)-[:REQUIRES|HAS_FEE]->(x:Requirement|Fee) RETURN x.id LIMIT 5",
    ],
)
def test_typed_relationships_are_accepted(query):
    accepted(query)


# ------------------------------------------------------- bound-variable reuse is allowed


@pytest.mark.parametrize(
    "query",
    [
        # the case from the spec: OPTIONAL MATCH on a variable labeled earlier
        (
            "MATCH (f:Fee) OPTIONAL MATCH (f)-[:APPLIES_WHEN]->(v:Variant) "
            "RETURN f.label, v.value LIMIT 5"
        ),
        (
            "MATCH (s:Service)-[:REQUIRES]->(r:Requirement) MATCH (r)-[:PART_OF]->(p:Requirement) "
            "RETURN p.text LIMIT 5"
        ),
        "MATCH (s:Service)-[:HAS_STEP]->(a:Step), (a)-[:NEXT]->(b:Step) RETURN b.id LIMIT 5",
        "MATCH (s:Service) WHERE (s)-[:HAS_STEP]->(:Step) RETURN s.name LIMIT 5",
        "MATCH (s:Service) WITH s MATCH (s)-[:HAS_STEP]->(st:Step) RETURN st.order LIMIT 5",
        "MATCH (s:Service) WITH DISTINCT s MATCH (s)-[:HAS_STEP]->(st:Step) RETURN st.id LIMIT 5",
        "MATCH (s:Service) WITH s AS svc MATCH (svc)-[:HAS_STEP]->(st:Step) RETURN st.id LIMIT 5",
        "MATCH (s:Service) WITH s, count(s) AS c MATCH (s)-[:HAS_STEP]->(st:Step) RETURN c LIMIT 5",
        "MATCH (s:Service) WITH * MATCH (s)-[:HAS_STEP]->(st:Step) RETURN st.id LIMIT 5",
        "MATCH (s:Service) WITH s WHERE s.id = 'x' MATCH (s)-[:HAS_FEE]->(f:Fee) RETURN f.id LIMIT 5",
        "MATCH (s:Service {id: $sid}) MATCH (s)-[:HAS_FEE]->(f:Fee) RETURN f.label LIMIT 5",
        "MATCH (s:Service) MATCH (s {id: $sid})-[:HAS_FEE]->(f:Fee) RETURN f.label LIMIT 5",
        (
            "MATCH (s:Service) OPTIONAL MATCH (s)-[:HAS_STEP]->(st:Step) "
            "OPTIONAL MATCH (st)-[:PERFORMED_BY]->(ro:Role) RETURN ro.title LIMIT 5"
        ),
    ],
)
def test_reusing_a_variable_bound_with_a_label_is_accepted(query):
    accepted(query)


@pytest.mark.parametrize(
    "query",
    [
        # WITH drops s, so the later (s) is a fresh, unlabeled variable
        "MATCH (s:Service) WITH count(s) AS c MATCH (s)-[:HAS_STEP]->(st:Step) RETURN c LIMIT 5",
        "MATCH (s:Service) WITH s.name AS n MATCH (s)-[:HAS_STEP]->(st:Step) RETURN n LIMIT 5",
        "MATCH (s:Service) WITH s AS svc MATCH (s)-[:HAS_STEP]->(st:Step) RETURN st LIMIT 5",
        # an alias of a non-node value is not a labeled node
        "MATCH (s:Service) WITH s.name AS n MATCH (n)-[:HAS_STEP]->(st:Step) RETURN st LIMIT 5",
        "UNWIND ['a'] AS x MATCH (x)-[:HAS_STEP]->(st:Step) RETURN st LIMIT 5",
        # labeled only later, or only inside a subquery or comprehension
        "MATCH (a)-[:NEXT]->(b:Step), (a:Step) RETURN b LIMIT 5",
        (
            "MATCH (s:Service) WHERE EXISTS { MATCH (t:Step) } MATCH (t)-[:NEXT]->(u:Step) "
            "RETURN u LIMIT 5"
        ),
        (
            "MATCH (s:Service) WITH s, [(s)-[:HAS_STEP]->(st:Step) | st.id] AS ids "
            "MATCH (st)-[:NEXT]->(u:Step) RETURN u LIMIT 5"
        ),
        # a different variable is not the bound one
        "MATCH (s:Service) MATCH (t)-[:HAS_STEP]->(st:Step) RETURN st LIMIT 5",
    ],
)
def test_reusing_a_variable_that_is_not_bound_with_a_label_is_rejected(query):
    rejected(query, "has no label")


# --------------------------------------------------------------- subqueries and predicates


@pytest.mark.parametrize(
    "query",
    [
        "MATCH (s:Service) WHERE EXISTS { (s)-[:HAS_FEE]->(x) } RETURN s LIMIT 5",
        "MATCH (s:Service) WHERE EXISTS { (n) } RETURN s LIMIT 5",
        "MATCH (s:Service) WHERE EXISTS { MATCH (s)-[:HAS_FEE]->(x) } RETURN s LIMIT 5",
        "MATCH (s:Service) WHERE EXISTS { (s)-[:HAS_FEE]->(x:Fee), (y) } RETURN s LIMIT 5",
        "MATCH (s:Service) RETURN s.name, COUNT { (s)-[:HAS_FEE]->(x) } AS n LIMIT 5",
        "MATCH (s:Service) RETURN COUNT { (n) } AS n LIMIT 5",
        "MATCH (s:Service) WHERE (s)-[:HAS_FEE]->(x) RETURN s LIMIT 5",
        "MATCH (s:Service) WHERE (n)-[:HAS_FEE]->(:Fee) RETURN s LIMIT 5",
        "MATCH (s:Service) WHERE NOT (s)-[:HAS_FEE]->(x) RETURN s LIMIT 5",
        "MATCH (s:Service) WHERE s.id = 'x' AND (s)-[:HAS_FEE]->(x) RETURN s LIMIT 5",
        "MATCH (s:Service) RETURN [(s)-[:HAS_STEP]->(x) | x.id] AS ids LIMIT 5",
        "MATCH (s:Service) RETURN size([(n)-[:HAS_STEP]->(:Step) | 1]) AS c LIMIT 5",
    ],
)
def test_unlabeled_nodes_inside_subqueries_and_predicates_are_rejected(query):
    rejected(query, "has no label")


@pytest.mark.parametrize(
    "query",
    [
        "MATCH (s:Service) WHERE EXISTS { (s)-[r]->(:Fee) } RETURN s LIMIT 5",
        "MATCH (s:Service) WHERE EXISTS { (s)-[]->(:Fee) } RETURN s LIMIT 5",
        "MATCH (s:Service) WHERE EXISTS { (s)-->(:Fee) } RETURN s LIMIT 5",
        "MATCH (s:Service) RETURN COUNT { (s)-[r]->(:Fee) } AS n LIMIT 5",
        "MATCH (s:Service) WHERE (s)-[r]->(:Fee) RETURN s LIMIT 5",
        "MATCH (s:Service) WHERE (s)-->(:Fee) RETURN s LIMIT 5",
        "MATCH (s:Service) WHERE NOT (s)--(:Fee) RETURN s LIMIT 5",
        "MATCH (s:Service) RETURN [(s)-[r]->(:Step) | 1] AS c LIMIT 5",
    ],
)
def test_untyped_relationships_inside_subqueries_and_predicates_are_rejected(query):
    result = validate_cypher(query)
    assert result.ok is False, query
    joined = " | ".join(result.reasons).lower()
    assert "untyped" in joined or "must specify a type" in joined, result.reasons


@pytest.mark.parametrize(
    "query",
    [
        "MATCH (s:Service) WHERE EXISTS { (s)-[:HAS_FEE]->(:Fee) } RETURN s.name LIMIT 5",
        (
            "MATCH (s:Service) WHERE EXISTS { MATCH (s)-[:HAS_FEE]->(f:Fee) WHERE f.unit = 'x' } "
            "RETURN s.name LIMIT 5"
        ),
        "MATCH (s:Service) WHERE EXISTS { (s) } RETURN s.name LIMIT 5",
        "MATCH (s:Service) RETURN COUNT { (s)-[:HAS_FEE]->(:Fee) } AS n LIMIT 5",
        "MATCH (s:Service) WHERE (s)-[:HAS_FEE]->(:Fee) RETURN s.name LIMIT 5",
        "MATCH (s:Service) WHERE NOT (s)-[:HAS_FEE]->(:Fee) RETURN s.name LIMIT 5",
        "MATCH (s:Service) RETURN [(s)-[:HAS_STEP]->(st:Step) | st.id] AS ids LIMIT 5",
        "MATCH (s:Service) WHERE EXISTS { MATCH (t:Step) } MATCH (t:Step) RETURN t.id LIMIT 5",
    ],
)
def test_labeled_subqueries_and_predicates_are_accepted(query):
    accepted(query)


def test_variables_do_not_leak_out_of_a_comprehension_or_subquery():
    rejected(
        "MATCH (s:Service) WITH s, [(s)-[:HAS_STEP]->(st:Step) | st.id] AS ids "
        "MATCH (st)-[:NEXT]->(u:Step) RETURN u LIMIT 5",
        "has no label",
    )


# ------------------------------------------------------------------- expression parentheses


@pytest.mark.parametrize(
    "query",
    [
        "MATCH (s:Service) WHERE (s.id = 'x') RETURN s.name LIMIT 5",
        "MATCH (s:Service) WHERE (s.id = 'x' OR s.id = 'y') AND s.name IS NOT NULL RETURN s.name LIMIT 5",
        "MATCH (s:Service) RETURN s.name, (size(s.name) + 1) AS n LIMIT 5",
        "MATCH (s:Service) RETURN s.name, size(s.name) - (size(s.id)) AS n LIMIT 5",
        "MATCH (s:Service) WITH s, count(*) AS c WHERE c > (1 + 1) RETURN s.name LIMIT 5",
        "MATCH (s:Service) WHERE toLower(s.name) = toLower($name) RETURN s.name LIMIT 5",
        "MATCH (s:Service) RETURN count(DISTINCT s.name) AS n LIMIT 5",
    ],
)
def test_ordinary_expression_parentheses_are_not_node_patterns(query):
    accepted(query)


# ---------------------------------------------------------------------- maximum length


def padded(length: int) -> str:
    """A valid query of exactly `length` characters (a block comment takes up the slack)."""
    base = "MATCH (s:Service) RETURN s.name LIMIT 5 "
    filler = length - len(base) - len("/**/")
    assert filler >= 0
    return base + "/*" + "x" * filler + "*/"


def test_the_real_config_caps_queries_at_2000_characters():
    assert MAX_CHARS == 2000


def test_query_at_the_maximum_length_is_accepted():
    query = padded(MAX_CHARS)
    assert len(query) == MAX_CHARS
    accepted(query)


def test_query_over_the_maximum_length_is_rejected():
    query = padded(MAX_CHARS + 1)
    assert len(query) == MAX_CHARS + 1
    rejected(query, "too long", str(MAX_CHARS))


def test_a_huge_query_is_rejected_for_length_without_being_analysed():
    result = rejected("MATCH (s:Service) RETURN s LIMIT 5 " + "x" * 200_000, "too long")
    assert len(result.reasons) == 1


def test_length_is_counted_in_characters_not_bytes():
    # one emoji is one character, so MAX_CHARS characters pass even though they exceed MAX_CHARS bytes
    base = "MATCH (s:Service) WHERE s.name = '"
    tail = "' RETURN s.name LIMIT 5"
    query = base + "\U0001f600" * (MAX_CHARS - len(base) - len(tail)) + tail
    assert len(query) == MAX_CHARS and len(query.encode()) > MAX_CHARS
    accepted(query)


def test_explicit_max_chars_argument_overrides_config():
    query = "MATCH (s:Service) RETURN s.name LIMIT 5"
    assert validate_cypher(query, max_chars=len(query)).ok is True
    result = validate_cypher(query, max_chars=len(query) - 1)
    assert result.ok is False and "too long" in " ".join(result.reasons).lower()


@pytest.mark.parametrize("bad", [0, -1, True, 1.5, "2000", []])
def test_invalid_max_chars_argument_fails_closed(bad):
    result = validate_cypher("MATCH (s:Service) RETURN s LIMIT 5", max_chars=bad)
    assert result.ok is False
    assert any("max_chars" in r for r in result.reasons)


# ------------------------------------------------------------------------------ config


@pytest.fixture
def limits_file(tmp_path, monkeypatch):
    path = tmp_path / "limits.yaml"
    monkeypatch.setattr(validator, "LIMITS_PATH", path)
    validator._load_max_limit.cache_clear()
    validator._load_max_chars.cache_clear()
    yield path
    validator._load_max_limit.cache_clear()
    validator._load_max_chars.cache_clear()


QUERY = "MATCH (s:Service) RETURN s.name LIMIT 5"  # 39 characters


def test_max_chars_is_read_from_yaml(limits_file):
    limits_file.write_text(f"core1:\n  cypher_limit_max: 50\n  cypher_max_chars: {len(QUERY)}\n")
    assert validate_cypher(QUERY).ok is True
    limits_file.write_text(
        f"core1:\n  cypher_limit_max: 50\n  cypher_max_chars: {len(QUERY) - 1}\n"
    )
    validator._load_max_chars.cache_clear()
    result = validate_cypher(QUERY)
    assert result.ok is False and "too long" in " ".join(result.reasons).lower()


@pytest.mark.parametrize(
    "core1",
    [
        "cypher_limit_max: 50",  # cypher_max_chars missing
        "cypher_limit_max: 50\n  cypher_max_chars:",  # null
        "cypher_limit_max: 50\n  cypher_max_chars: lots",
        "cypher_limit_max: 50\n  cypher_max_chars: '2000'",
        "cypher_limit_max: 50\n  cypher_max_chars: 0",
        "cypher_limit_max: 50\n  cypher_max_chars: -5",
        "cypher_limit_max: 50\n  cypher_max_chars: 2000.5",
        "cypher_limit_max: 50\n  cypher_max_chars: true",
        "cypher_limit_max: 50\n  cypher_max_chars: [2000]",
        "cypher_limit_max: 50\n  cypher_max_chars: {n: 2000}",
    ],
)
def test_missing_or_invalid_max_chars_config_fails_closed(limits_file, core1):
    limits_file.write_text(f"core1:\n  {core1}\n")
    result = validate_cypher(QUERY)
    assert result.ok is False
    assert any("config" in r.lower() for r in result.reasons)


@pytest.mark.parametrize("content", [None, "", "core1: {}", "just a string", "core1: [unclosed"])
def test_missing_or_broken_config_file_fails_closed(limits_file, content):
    if content is not None:
        limits_file.write_text(content)
    result = validate_cypher(QUERY)
    assert result.ok is False
    assert any("config" in r.lower() for r in result.reasons)


def test_explicit_limits_do_not_need_config(limits_file):
    # the config file is absent, but with both limits given it is never consulted
    assert validate_cypher(QUERY, max_limit=10, max_chars=100).ok is True


def test_one_explicit_limit_still_needs_the_other_from_config(limits_file):
    assert validate_cypher(QUERY, max_limit=10).ok is False
    assert validate_cypher(QUERY, max_chars=100).ok is False
