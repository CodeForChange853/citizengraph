"""Guardrail hardening 2: unicode escapes, whole entities, reserved names, one-hop patterns.

No Neo4j, no model, no network. Rules (docs/specs.md section 4):

- no backslash-u escape anywhere in the query text (strings and comments included);
- a node, relationship or path never leaves the query whole: no `RETURN s`, `RETURN *`,
  `collect(s)`, `RETURN p`, and no entity as a function argument, list or map value;
- no variable or alias named like a keyword or like a schema label, type or property;
- `IS` only with `NULL` / `NOT NULL`; relationships are one hop; MATCH holds only patterns;
- the `{` of EXISTS, COUNT and COLLECT is a subquery, not a map, so a label test in it is
  checked as a label.

Every rejected query here was accepted before these rules unless a comment says otherwise;
what each one could reveal is in the section comments.
"""

import json
from pathlib import Path

import pytest

from citizengraph.guardrail.keywords import KEYWORDS
from citizengraph.guardrail.schema import OFFICIAL_SCHEMA
from citizengraph.guardrail.validator import ValidationResult, validate_cypher

GOLDEN = Path(__file__).resolve().parent / "golden" / "core1_cypher.json"
BOOKKEEPING = [
    "review_status",
    "condition_structured",
    "flags",
    "source_sheet",
    "source_row",
    "source_rows",
    "charter_ref",
    "key",
]


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


# ------------------------------------------------------------------ Core 1 is unaffected


def test_every_golden_core1_query_still_passes():
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert len(golden) >= 38
    for name, entry in golden.items():
        result = validate_cypher("\n".join(entry["cypher"]))
        assert result.ok, (name, result.reasons)


# ---------------------------------------------------------------------- unicode escapes
# If the database expands \uXXXX before it parses (unverified here), \u0027 is a quote that
# ends a string early and \u000a is a newline that ends a comment: the text after it would be
# live Cypher that the tokenizer saw as data.


@pytest.mark.parametrize(
    "query",
    [
        "MATCH (s:Service) WHERE s.name = '\\u0027 SET s.name = \\u0027x' RETURN s.name LIMIT 5",
        (
            "MATCH (s:Service) WHERE s.name = 'x\\u0027 OR s.review_status = \\u0027y' "
            "RETURN s.name LIMIT 5"
        ),
        "MATCH (s:Service) // note \\u000a DETACH DELETE s\nRETURN s.name LIMIT 5",
        "MATCH (s:Service) /* \\u002a\\u002f SET s.name = 'x' /* */ RETURN s.name LIMIT 5",
        "MATCH (s:Service) WHERE s.name = 'caf\\u00e9' RETURN s.name LIMIT 5",
        'MATCH (s:Service) WHERE s.name = "\\u0022" RETURN s.name LIMIT 5',
        "MATCH (s:Service) WHERE s.name = '\\U0001F600' RETURN s.name LIMIT 5",
        "MATCH (s:Service) WHERE s.name = 'a\\\\u0027' RETURN s.name LIMIT 5",
        "MATCH (s:Service) RETURN s.\\u006eame LIMIT 5",
        "MATCH (s:Service) RETURN s.name LIMIT 5 // \\u",
    ],
)
def test_a_unicode_escape_anywhere_is_rejected(query):
    rejected(query, "unicode escapes")


def test_other_backslash_escapes_and_real_non_ascii_text_still_pass():
    accepted("MATCH (s:Service) WHERE s.name = 'it\\'s' RETURN s.name LIMIT 5")
    accepted("MATCH (s:Service) WHERE s.name = 'a\\\\b\\n' RETURN s.name LIMIT 5")
    accepted("MATCH (s:Service) WHERE s.name = 'café ñ' RETURN s.name LIMIT 5")
    accepted("MATCH (s:Service) WHERE s.name = 'utang' RETURN s.name LIMIT 5")


# ---------------------------------------------------------------------- whole entities
# A node, relationship or path value carries every stored property, so each of these would
# hand out the bookkeeping properties the allow-list keeps unreadable.

WHOLE_ENTITY = [
    "MATCH (s:Service) RETURN s LIMIT 5",
    "match (s:Service) return s limit 5",
    "MATCH (s:Service) RETURN (s) LIMIT 5",
    "MATCH (s:Service) RETURN DISTINCT s LIMIT 5",
    "MATCH (s:Service) RETURN s, s.name LIMIT 5",
    "MATCH (s:Service) RETURN s.name, s LIMIT 5",
    "MATCH (s:Service) RETURN s AS t LIMIT 5",
    "MATCH (s:Service) RETURN s.name ORDER BY s LIMIT 5",
    "MATCH (s:Service) RETURN collect(s) AS c LIMIT 5",
    "MATCH (s:Service) RETURN head(collect(s)) AS c LIMIT 5",
    "MATCH (s:Service) RETURN [s] AS c LIMIT 5",
    "MATCH (s:Service) RETURN [s.name, s] AS c LIMIT 5",
    "MATCH (s:Service) RETURN {name: s} AS c LIMIT 5",
    "MATCH (s:Service) RETURN CASE WHEN true THEN s END AS c LIMIT 5",
    "MATCH (s:Service) RETURN CASE s WHEN s THEN 1 END AS c LIMIT 5",
    "MATCH (s:Service) RETURN coalesce(s, null) AS c LIMIT 5",
    "MATCH (s:Service) RETURN toString(s) AS c LIMIT 5",
    "MATCH (s:Service) RETURN labels(s) AS c LIMIT 5",
    "MATCH (s:Service) RETURN elementId(s) AS c LIMIT 5",
    "MATCH (s:Service) RETURN s = s AS c LIMIT 5",
    "MATCH (s:Service) RETURN s IS NULL OR s AS c LIMIT 5",
    "MATCH (s:Service) RETURN count(s), s LIMIT 5",
    "MATCH (s:Service) RETURN count(s + 1) AS c LIMIT 5",
    "MATCH (s:Service) RETURN s {.name, s} AS c LIMIT 5",
    "MATCH (s:Service) RETURN s {.name, id: s} AS c LIMIT 5",
    "MATCH (s:Service) RETURN [x IN [s] | x] AS c LIMIT 5",
    "MATCH (s:Service) RETURN [s IN [1] | s] AS c LIMIT 5",
    "MATCH (s:Service) RETURN reduce(a = s, x IN [1] | a) AS c LIMIT 5",
    "MATCH (s:Service) RETURN reduce(s = 0, x IN [1] | s) AS c LIMIT 5",
    "MATCH (s:Service) RETURN any(x IN [1] WHERE s = s) AS c LIMIT 5",
    # through WITH and UNWIND
    "MATCH (s:Service) WITH s AS t RETURN t LIMIT 5",
    "MATCH (s:Service) WITH s AS t WITH t AS u RETURN u LIMIT 5",
    "MATCH (s:Service) WITH s AS t RETURN t.name, t LIMIT 5",
    "MATCH (s:Service) WITH (s) AS t RETURN t LIMIT 5",
    "MATCH (s:Service) WITH [s] AS t RETURN t LIMIT 5",
    "MATCH (s:Service) WITH collect(s) AS t RETURN t LIMIT 5",
    "MATCH (s:Service) UNWIND [s] AS t RETURN t LIMIT 5",
    "MATCH (s:Service) WITH * RETURN s LIMIT 5",
    # relationships and paths
    "MATCH (s:Service)-[r:REQUIRES]->(q:Requirement) RETURN r LIMIT 5",
    "MATCH (s:Service)-[r:REQUIRES]->(q:Requirement) RETURN type(r) AS c LIMIT 5",
    "MATCH (s:Service)-[r:REQUIRES]->(q:Requirement) RETURN startNode(r) AS c LIMIT 5",
    "MATCH p = (s:Service)-[:REQUIRES]->(r:Requirement) RETURN p LIMIT 5",
    "MATCH p = (s:Service)-[:REQUIRES]->(r:Requirement) RETURN nodes(p) AS c LIMIT 5",
    "MATCH p = (s:Service)-[:REQUIRES]->(r:Requirement) RETURN relationships(p) AS c LIMIT 5",
    "MATCH p = (s:Service)-[:REQUIRES]->(r:Requirement) RETURN length(p) AS c LIMIT 5",
    "MATCH p = (s:Service)-[:REQUIRES]->(r:Requirement) WITH p AS q RETURN q LIMIT 5",
    "MATCH (a:Step), p = (s:Service)-[:REQUIRES]->(r:Requirement) RETURN p LIMIT 5",
    # comprehensions and subqueries
    "MATCH (s:Service) RETURN [(s)-[:REQUIRES]->(r:Requirement) | r] AS c LIMIT 5",
    "MATCH (s:Service) RETURN [(s)-[rel:REQUIRES]->(r:Requirement) | rel] AS c LIMIT 5",
    "MATCH (s:Service) RETURN [p = (s)-[:REQUIRES]->(r:Requirement) | p] AS c LIMIT 5",
    (
        "MATCH (s:Service) RETURN COLLECT { MATCH (s)-[:REQUIRES]->(r:Requirement) RETURN r } "
        "AS c LIMIT 5"
    ),
    # a name that is a node anywhere is a node everywhere
    "MATCH (s:Service) WITH s.name AS x WITH 1 AS y MATCH (x:Service) RETURN x LIMIT 5",
    "MATCH (s:Service) RETURN s.name AS s ORDER BY s LIMIT 5",
]


@pytest.mark.parametrize("query", WHOLE_ENTITY)
def test_a_whole_node_relationship_or_path_is_never_a_value(query):
    rejected(query, "is a node, relationship or path")


@pytest.mark.parametrize(
    "query",
    [
        "MATCH (s:Service) RETURN * LIMIT 5",
        "MATCH (s:Service) RETURN DISTINCT * LIMIT 5",
        "MATCH (s:Service) RETURN *, s.name LIMIT 5",
        "MATCH (s:Service) RETURN s.name, * LIMIT 5",
        "MATCH (s:Service) WITH * RETURN * LIMIT 5",
        ("MATCH (s:Service) RETURN COLLECT { MATCH (r:Requirement) RETURN * } AS c LIMIT 5"),
    ],
)
def test_return_star_is_rejected(query):
    rejected(query, "RETURN *")


@pytest.mark.parametrize("prop", BOOKKEEPING)
def test_bookkeeping_properties_stay_unreadable_by_every_route(prop):
    assert prop not in OFFICIAL_SCHEMA.properties
    for query in (
        f"MATCH (s:Service) RETURN s.{prop} LIMIT 5",
        f"MATCH (s:Service) RETURN s['{prop}'] LIMIT 5",
        f"MATCH (s:Service) RETURN s {{.{prop}}} AS m LIMIT 5",
        f"MATCH (s:Service) RETURN s {{.name, {prop}: 1}} AS m LIMIT 5",
        f"MATCH (s:Service {{{prop}: 1}}) RETURN s.name LIMIT 5",
        f"MATCH (by:Service) RETURN by['{prop}'] LIMIT 5",
        f"MATCH (limit:Service) RETURN limit['{prop}'] LIMIT 5",
        f"MATCH (s:Service) WITH s AS in RETURN in['{prop}'] LIMIT 5",
    ):
        rejected(query)


@pytest.mark.parametrize(
    "query",
    [
        "MATCH (s:Service) RETURN s.name LIMIT 5",
        "MATCH (s:Service) RETURN count(s) AS c LIMIT 5",
        "MATCH (s:Service) RETURN count(DISTINCT s) AS c LIMIT 5",
        "MATCH (s:Service) RETURN count(*) AS c LIMIT 5",
        "MATCH (s:Service) RETURN s {.name, .id} AS m LIMIT 5",
        "MATCH (s:Service) WHERE s:Service RETURN s.id LIMIT 5",
        "MATCH (s:Service) WITH s AS t RETURN t.name LIMIT 5",
        "MATCH (s:Service) WITH DISTINCT s RETURN s.name LIMIT 5",
        "MATCH (s:Service) WITH * RETURN s.name LIMIT 5",
        (
            "MATCH (s:Service) OPTIONAL MATCH (s)-[:HAS_FEE]->(f:Fee) WITH s, f "
            "WHERE f IS NULL RETURN s.name LIMIT 5"
        ),
        (
            "MATCH (s:Service) OPTIONAL MATCH (s)-[:HAS_FEE]->(f:Fee) WITH s, f "
            "WHERE f IS NOT NULL RETURN s.name, f.label LIMIT 5"
        ),
        "MATCH p = (s:Service)-[:REQUIRES]->(r:Requirement) RETURN r.text LIMIT 5",
        "MATCH (s:Service)-[q:REQUIRES]->(r:Requirement) RETURN r.text LIMIT 5",
        "MATCH (s:Service) RETURN [(s)-[:HAS_STEP]->(st:Step) | st.id] AS ids LIMIT 5",
        "MATCH (s:Service) RETURN [x IN [1, 2] WHERE x > 1 | x * 2] AS c LIMIT 5",
        "MATCH (st:Step) RETURN st.dur_min * 2 AS c LIMIT 5",
        "MATCH (s:Service) RETURN s.name AS n ORDER BY n DESC SKIP 1 LIMIT 5",
        "MATCH (s:Service) RETURN s.name ORDER BY [s.name, s.id] LIMIT 5",
        "MATCH (s:Service) WHERE s.id IN ['x'] RETURN true AS t, null AS z LIMIT 5",
        "MATCH (a:Step), (b:Step) WHERE a.order < b.order RETURN a.id, b.id LIMIT 5",
    ],
)
def test_entities_are_fine_where_no_whole_value_escapes(query):
    accepted(query)


@pytest.mark.parametrize(
    "query",
    [
        "MATCH (s:Service) RETURN x LIMIT 5",
        "MATCH (s:Service) RETURN x.name LIMIT 5",
        "MATCH (s:Service) RETURN s.name ORDER BY missing LIMIT 5",
        "MATCH (s:Service) WHERE nothing = 1 RETURN s.name LIMIT 5",
    ],
)
def test_an_unknown_name_is_rejected(query):
    rejected(query, "unknown variable")


# ------------------------------------------------------------------------ reserved names
# The guardrail reads `by`, `limit`, `in`, `as` and the rest as syntax. A variable of that
# name is read by the database as a variable: `by['review_status']` was a list after BY to
# us and a dynamic property read to the database.

_ODD = sorted(KEYWORDS - {"WHERE"})


@pytest.mark.parametrize("word", _ODD)
def test_no_node_variable_is_named_like_a_keyword(word):
    for name in (word.lower(), word.title()):
        rejected(f"MATCH ({name}:Service) RETURN {name}.name LIMIT 5")
        rejected(f"MATCH (s:Service)-[:REQUIRES]->({name}:Requirement) RETURN s.name LIMIT 5")


@pytest.mark.parametrize("word", sorted(KEYWORDS))
def test_no_relationship_path_or_alias_is_named_like_a_keyword(word):
    name = word.lower()
    rejected(f"MATCH (s:Service)-[{name}:REQUIRES]->(r:Requirement) RETURN r.text LIMIT 5")
    rejected(f"MATCH {name} = (s:Service)-[:REQUIRES]->(r:Requirement) RETURN r.text LIMIT 5")
    rejected(f"MATCH (s:Service) WITH s AS {name} RETURN 1 AS x LIMIT 5")
    rejected(f"MATCH (s:Service) RETURN s.name AS {name} LIMIT 5")
    rejected(f"UNWIND [1] AS {name} RETURN 1 AS x LIMIT 5")
    rejected(
        f"MATCH (s:Service) RETURN [{name} = (s)-[:REQUIRES]->(r:Requirement) | r.text] AS c "
        "LIMIT 5"
    )


@pytest.mark.parametrize(
    "query",
    [
        "MATCH (by:Service) RETURN by['review_status'] LIMIT 5",
        "MATCH (limit:Service) RETURN limit['key'] LIMIT 5",
        "MATCH (in:Service) RETURN in['charter_ref'] LIMIT 5",
        "MATCH (as:Service) RETURN as['source_sheet'] LIMIT 5",
        "MATCH (where:Service) RETURN where['flags'] LIMIT 5",
        "MATCH (where:Service) RETURN where.name LIMIT 5",
        "MATCH (a:Step)-[:NEXT]->(where:Step) RETURN a.id LIMIT 5",
        "MATCH (a:Step)-[:NEXT]->(where) RETURN a.id LIMIT 5",
        "MATCH unwind = (n) RETURN unwind LIMIT 5",
        "MATCH with = (n) RETURN 1 AS x LIMIT 5",
        "MATCH return = (n) RETURN 1 AS x LIMIT 5",
        "MATCH (by:Service) RETURN by LIMIT 5",
        "MATCH (distinct:Service) RETURN distinct LIMIT 5",
        "MATCH (null:Service) RETURN null LIMIT 5",
        "MATCH (true:Service) RETURN true LIMIT 5",
        "MATCH (end:Service) RETURN end LIMIT 5",
        "MATCH (exists:Service) RETURN exists LIMIT 5",
        "MATCH (s:Service) WITH s AS by RETURN by['key'] LIMIT 5",
        "MATCH (s:Service) WHERE s.id IN by['x'] RETURN s.name LIMIT 5",
        "MATCH (s:Service) RETURN s.name ORDER BY by['x'] LIMIT 5",
        "MATCH (s:Service) RETURN [in IN [1] | in] AS c LIMIT 5",
        ("MATCH (s:Service) RETURN [with = (s)-[:REQUIRES]->(r:Requirement) | with] AS c LIMIT 5"),
        (
            "MATCH (s:Service) WHERE EXISTS { is = (s)-[:REQUIRES]->(r:Requirement) } "
            "RETURN s.name LIMIT 5"
        ),
    ],
)
def test_keyword_named_variables_cannot_reach_a_property_or_a_whole_node(query):
    rejected(query)


def test_by_opens_a_list_only_after_order():
    rejected("MATCH (by:Service) RETURN by['review_status'] LIMIT 5", "subscript")
    rejected("MATCH (s:Service) RETURN s.name ORDER BY s.name, by['x'] LIMIT 5", "subscript")
    accepted("MATCH (s:Service) RETURN s.name ORDER BY [s.name, s.id] LIMIT 5")
    for word in ("as", "is", "limit", "skip"):
        rejected(f"MATCH ({word}:Service) RETURN {word}['key'] LIMIT 5", "subscript")


@pytest.mark.parametrize(
    "name", sorted(OFFICIAL_SCHEMA.properties | OFFICIAL_SCHEMA.labels | {"REQUIRES", "NEXT"})
)
def test_no_variable_or_alias_is_named_like_a_schema_name(name):
    rejected(f"MATCH ({name}:Service) RETURN {name}.id LIMIT 5")
    rejected(f"MATCH (s:Service)-[{name}:REQUIRES]->(r:Requirement) RETURN r.text LIMIT 5")
    rejected(f"MATCH (s:Service) WITH s AS {name} RETURN 1 AS x LIMIT 5")
    rejected(f"MATCH (s:Service) RETURN s.id AS {name} LIMIT 5")


def test_names_that_only_look_like_reserved_ones_are_fine():
    accepted("MATCH (svc:Service) RETURN svc.name AS service_name LIMIT 5")
    accepted("MATCH (s:Service) RETURN s.id AS sid, s.name AS n_name LIMIT 5")
    accepted("MATCH (s:Service) WITH s AS settings RETURN settings.name LIMIT 5")
    accepted("MATCH (service:Service) RETURN service.name LIMIT 5")  # labels are exact case


# ------------------------------------------------------- label tests inside subqueries
# `{` after EXISTS / COUNT / COLLECT was read as a map, so `name:Application` in it looked
# like a map key when the variable was named like an allowed property, and the label after
# it was never checked.


@pytest.mark.parametrize(
    "query",
    [
        (
            "MATCH (s:Service) WHERE EXISTS { MATCH (info_status) "
            "WHERE info_status:Application } RETURN s.id LIMIT 5"
        ),
        (
            "MATCH (name:Service) WHERE EXISTS { (name)-[:HAS_FEE]->(:Fee) "
            "WHERE name:Application } RETURN name.id LIMIT 5"
        ),
        (
            "MATCH (id:Service) RETURN COUNT { MATCH (id)-[:HAS_FEE]->(f:Fee) "
            "WHERE id:Application } AS c LIMIT 5"
        ),
        (
            "MATCH (text:Requirement) WHERE EXISTS { MATCH (text)-[:PART_OF]->(p:Requirement) "
            "WHERE text:Application } RETURN p.id LIMIT 5"
        ),
        (
            "MATCH (s:Service) WHERE EXISTS { MATCH (x:Service) WHERE x:Application } "
            "RETURN s.id LIMIT 5"
        ),
        (
            "MATCH (s:Service) RETURN COLLECT { MATCH (x:Service) WHERE x:Application "
            "RETURN x.id } AS c LIMIT 5"
        ),
    ],
)
def test_a_label_test_inside_a_subquery_is_checked_as_a_label(query):
    rejected(query, "unknown label 'Application'")


def test_a_schema_label_test_inside_a_subquery_is_now_accepted():
    # Was over-rejected ("unknown property 'f'") while the braces were read as a map.
    accepted(
        "MATCH (s:Service) WHERE EXISTS { MATCH (s)-[:HAS_FEE]->(f:Fee) WHERE f:Fee } "
        "RETURN s.id LIMIT 5"
    )


@pytest.mark.parametrize(
    "query",
    [
        "MATCH (s:Service) RETURN {id: s:Application} AS c LIMIT 5",
        "MATCH (s:Service) RETURN {id: 1, s.review_status: 2} AS c LIMIT 5",
        "MATCH (s:Service) RETURN {id: 1 name: 2} AS c LIMIT 5",
        "MATCH (s:Service) RETURN {id: (1):Application} AS c LIMIT 5",
    ],
)
def test_a_colon_in_a_map_only_follows_a_key(query):
    rejected(query)


# ----------------------------------------------------------------------------- IS forms
# `(x IS Application)` next to a relationship was skipped by the label checks (not shaped
# like `(var:Label)`), so it reached labels outside the charter graph.


@pytest.mark.parametrize(
    "query",
    [
        "MATCH (x IS Application) RETURN x.id LIMIT 5",  # was already rejected
        "MATCH (x IS %) RETURN x.id LIMIT 5",  # was already rejected
        "MATCH (s:Service)-[:REQUIRES]->(x IS Application) RETURN x.id LIMIT 5",
        "MATCH (s:Service)-[:REQUIRES]->(x IS %) RETURN x.id LIMIT 5",
        "MATCH (s:Service)-[:REQUIRES]->(IS Application) RETURN s.id LIMIT 5",
        "MATCH (s:Service)-[:REQUIRES]->(x IS Requirement) RETURN x.id LIMIT 5",
        "MATCH (s:Service)-[r IS AT_STEP]->(t:Step) RETURN t.id LIMIT 5",
        "MATCH (s:Service)-[IS AT_STEP]->(t:Step) RETURN t.id LIMIT 5",
        "MATCH (s:Service) WHERE s IS Application RETURN s.id LIMIT 5",
        "MATCH (s:Service) WHERE s IS NOT Application RETURN s.id LIMIT 5",
        "MATCH (s:Service) WHERE s.id IS :: INTEGER RETURN s.id LIMIT 5",
        "MATCH (s:Service) WHERE s.id IS TYPED INTEGER RETURN s.id LIMIT 5",
        "MATCH (s:Service) WHERE s.name IS NORMALIZED RETURN s.id LIMIT 5",
        "MATCH (s:Service) WHERE s.name IS NOT NORMALIZED RETURN s.id LIMIT 5",
    ],
)
def test_is_takes_only_null_tests(query):
    rejected(query, "IS may only be followed by NULL")


def test_is_null_and_is_not_null_still_pass():
    accepted("MATCH (s:Service) WHERE s.description IS NULL RETURN s.id LIMIT 5")
    accepted("MATCH (s:Service) WHERE s.description is not null RETURN s.id LIMIT 5")


# ------------------------------------------------- variable length, quantifiers, selectors
# Inside the charter graph these read no forbidden data, but `->+(n)` let an unlabeled node
# through, and unbounded traversals are the expensive queries the spec warns about.


@pytest.mark.parametrize(
    "query",
    [
        "MATCH (a:Step)-[:NEXT*]->(b:Step) RETURN b.id LIMIT 5",
        "MATCH (a:Step)-[:NEXT*1..3]->(b:Step) RETURN b.id LIMIT 5",
        "MATCH (a:Step)-[r:NEXT*1..2]->(b:Step) RETURN b.id LIMIT 5",
        "MATCH (a:Step)-[:NEXT*2]->(b:Step) RETURN b.id LIMIT 5",
        "MATCH (a:Step)-[:NEXT*..3]->(b:Step) RETURN b.id LIMIT 5",
        "MATCH (a:Step)-[r:NEXT WHERE r.id = 1]->(b:Step) RETURN b.id LIMIT 5",
        "MATCH (s:Service)-[:NEXT]->+(n) RETURN n.id LIMIT 5",
        "MATCH (s:Service)-[:NEXT]->*(n) RETURN n.id LIMIT 5",
        "MATCH (s:Service)-[:NEXT]->{1,3}(n) RETURN n.id LIMIT 5",
        "MATCH (a:Step)-[:NEXT]->+(b:Step) RETURN b.id LIMIT 5",
        "MATCH (a:Step)-[:NEXT]-+(b:Step) RETURN b.id LIMIT 5",
        "MATCH (a:Step)<-[:NEXT]-*(b:Step) RETURN b.id LIMIT 5",
        "MATCH (s:Service) WHERE (s)-[:HAS_STEP]->+(:Step) RETURN s.id LIMIT 5",
        "MATCH (s:Service) WHERE (s)-[:HAS_STEP]->{2}(:Step) RETURN s.id LIMIT 5",
        "MATCH (s:Service) RETURN [(s)-[:HAS_STEP*]->(t:Step) | t.id] AS c LIMIT 5",
        "MATCH (s:Service) WHERE EXISTS { (s)-[:HAS_STEP*2]->(:Step) } RETURN s.id LIMIT 5",
    ],
)
def test_relationships_are_one_hop(query):
    rejected(query, "variable-length, quantified or filtered")


@pytest.mark.parametrize(
    "query",
    [
        "MATCH ((a:Step)-[:NEXT]->(b:Step))+ RETURN 1 AS x LIMIT 5",
        "MATCH ((x:Step)-[:NEXT]->(y:Step))* RETURN 1 AS c LIMIT 5",
        "MATCH (a:Step) ((x:Step)-[:NEXT]->(y:Step))+ (b:Step) RETURN b.id LIMIT 5",
        "MATCH (a:Step) ((x:Step)-[:NEXT]->(y:Step)){1,3} (b:Step) RETURN b.id LIMIT 5",
        "MATCH (s:Service) RETURN [((x:Step)-[:NEXT]->(y:Step))+ | 1] AS c LIMIT 5",
        "MATCH (a:Step) (b) RETURN 1 AS c LIMIT 5",
    ],
)
def test_quantified_and_parenthesized_path_patterns_are_rejected(query):
    rejected(query)


@pytest.mark.parametrize(
    "query",
    [
        "MATCH ANY SHORTEST (a:Step)-[:NEXT]->(b:Step) RETURN b.id LIMIT 5",
        "MATCH ALL SHORTEST (a:Step)-[:NEXT]->(b:Step) RETURN b.id LIMIT 5",
        "MATCH SHORTEST 1 (a:Step)-[:NEXT]->(b:Step) RETURN b.id LIMIT 5",
        "MATCH ANY (n) RETURN 1 AS c LIMIT 5",
        "MATCH ALL (n) RETURN 1 AS c LIMIT 5",
        "MATCH DIFFERENT RELATIONSHIPS (n) RETURN 1 AS c LIMIT 5",
        "MATCH REPEATABLE ELEMENTS (n) RETURN 1 AS c LIMIT 5",
        "MATCH p = shortestPath((a:Step)-[:NEXT]->(b:Step)) RETURN 1 AS c LIMIT 5",
        "MATCH p = allShortestPaths((a:Step)-[:NEXT]->(b:Step)) RETURN 1 AS c LIMIT 5",
        "MATCH (a:Step) 5 RETURN a.id LIMIT 5",
        "MATCH (a:Step) = (b:Step) RETURN a.id LIMIT 5",
        "MATCH (a:Step)[0] RETURN a.id LIMIT 5",
        "MATCH (a:Step) + (b:Step) RETURN a.id LIMIT 5",
    ],
)
def test_a_match_clause_holds_only_patterns(query):
    rejected(query, "unsupported MATCH syntax")


def test_path_selectors_cannot_carry_an_unlabeled_node_past_the_label_rule():
    # `(n)` after a selector is neither right after MATCH nor next to a relationship, so the
    # label rule alone did not see it.
    for query in (
        "MATCH ANY (n) RETURN n.id LIMIT 5",
        "MATCH DIFFERENT RELATIONSHIPS (n) RETURN n.id LIMIT 5",
        "MATCH (a:Step), REPEATABLE ELEMENTS (n) RETURN n.id LIMIT 5",
    ):
        rejected(query)


@pytest.mark.parametrize(
    "query",
    [
        "MATCH (s:Service)-[:REQUIRES]->(r:Requirement) RETURN r.text LIMIT 5",
        "MATCH (s:Service)<-[:OFFERS]-(o:Office) RETURN o.name LIMIT 5",
        "MATCH (s:Service)-[:REQUIRES|HAS_FEE]->(x:Requirement|Fee) RETURN x.id LIMIT 5",
        "MATCH (s:Service)-[:HAS_STEP]-(st:Step) RETURN st.order LIMIT 5",
        "MATCH (s:Service)-[:HAS_STEP]->(a:Step)-[:NEXT]->(b:Step) RETURN b.id LIMIT 5",
        "MATCH (s:Service)-[:HAS_STEP]->(a:Step), (a)-[:NEXT]->(b:Step) RETURN b.id LIMIT 5",
        ("MATCH (s:Service) OPTIONAL MATCH (s)-[:HAS_FEE]->(f:Fee) RETURN s.name, f.label LIMIT 5"),
    ],
)
def test_one_hop_patterns_still_pass(query):
    accepted(query)


# ------------------------------------------------- found by the independent review, round 1
# A pattern used as a value is a list of whole paths (on a Neo4j that allows it), and the
# variables in it sit inside a pattern, where the entity rule does not look.


@pytest.mark.parametrize(
    "query",
    [
        "MATCH (s:Service) RETURN (s)-[:REQUIRES]->(:Requirement) AS c LIMIT 5",
        "MATCH (s:Service) RETURN [(s)-[:REQUIRES]->(:Requirement)] AS c LIMIT 5",
        "MATCH (s:Service) RETURN {id: (s)-[:REQUIRES]->(:Requirement)} AS c LIMIT 5",
        (
            "MATCH (s:Service) RETURN CASE WHEN true THEN (s)-[:REQUIRES]->(:Requirement) END "
            "AS c LIMIT 5"
        ),
        (
            "MATCH (s:Service) WITH (s)-[:REQUIRES]->(:Requirement) AS ps UNWIND ps AS p "
            "RETURN p LIMIT 5"
        ),
        "MATCH (s:Service) RETURN [x IN (s)-[:REQUIRES]->(:Requirement) | x] AS c LIMIT 5",
        "MATCH (s:Service) RETURN coalesce(null, (s)-[:REQUIRES]->(:Requirement)) AS c LIMIT 5",
        "MATCH (s:Service) RETURN s.name ORDER BY (s)-[:REQUIRES]->(:Requirement) LIMIT 5",
        "MATCH (s:Service) WHERE (s)-[:REQUIRES]->(:Requirement) = [] RETURN s.name LIMIT 5",
        "MATCH (s:Service) WHERE s.id IN (s)-[:REQUIRES]->(:Requirement) RETURN s.name LIMIT 5",
    ],
)
def test_a_pattern_is_never_a_value(query):
    rejected(query, "a pattern outside MATCH")


def test_a_pattern_is_fine_as_a_predicate_or_in_a_comprehension():
    accepted("MATCH (s:Service) WHERE (s)-[:HAS_FEE]->(:Fee) RETURN s.name LIMIT 5")
    accepted("MATCH (s:Service) WHERE NOT (s)-[:HAS_FEE]->(:Fee) RETURN s.name LIMIT 5")
    accepted(
        "MATCH (s:Service) WHERE s.id = $sid AND (s)-[:HAS_FEE]->(:Fee) OR "
        "(s)-[:HAS_STEP]->(:Step) RETURN s.name LIMIT 5"
    )
    accepted("MATCH (s:Service) RETURN [(s)-[:HAS_STEP]->(st:Step) | st.id] AS ids LIMIT 5")
    accepted(
        "MATCH (s:Service) RETURN [(s)-[:HAS_STEP]->(st:Step) WHERE st.order > 1 | st.id] "
        "AS ids LIMIT 5"
    )


@pytest.mark.parametrize(
    "query",
    [
        "MATCH (s:Service) WHERE (s)-[:REQUIRES]->(n:Requirement) MATCH (n) RETURN n.id LIMIT 5",
        "MATCH (s:Service) WITH s WHERE (s)-[:HAS_FEE]->(n:Fee) MATCH (n) RETURN n.id LIMIT 5",
        "MATCH (s:Service) WHERE NOT (s)-[:HAS_FEE]->(f:Fee) RETURN s.name LIMIT 5",
    ],
)
def test_a_pattern_predicate_cannot_introduce_a_variable(query):
    # Otherwise `n` counts as labeled and a later bare `MATCH (n)` is accepted.
    rejected(query, "cannot introduce a new variable")


@pytest.mark.parametrize(
    "query",
    [
        "MATCH (a:Step)-(b:Step) RETURN b.id LIMIT 5",
        "MATCH (a:Step)->(b:Step) RETURN b.id LIMIT 5",
        "MATCH (a:Step)<-(b:Step) RETURN b.id LIMIT 5",
        "MATCH (a:Step)<-[:NEXT]->(b:Step) RETURN b.id LIMIT 5",
        "MATCH (a:Step) > () RETURN a.id LIMIT 5",
        "MATCH (s:Service) RETURN -(s) AS c LIMIT 5",
        "MATCH (s:Service) RETURN (s) < -1 AS c LIMIT 5",
        "MATCH (s:Service) RETURN s.name ORDER BY -(s) LIMIT 5",
    ],
)
def test_a_link_without_a_relationship_bracket_is_rejected(query):
    rejected(query)


def test_a_label_test_inside_a_list_is_checked_as_a_label_not_as_a_type():
    rejected("MATCH (s:Service) RETURN [x IN [1] WHERE s:NEXT] AS c LIMIT 5", "unknown label")
    rejected("MATCH (s:Service) RETURN [x IN [1] WHERE s:Application] AS c LIMIT 5", "label")
    accepted("MATCH (s:Service) RETURN [x IN [1] WHERE s:Service] AS c LIMIT 5")
    # a type is still a type inside a relationship bracket
    rejected("MATCH (s:Service)-[:Service]->(r:Requirement) RETURN r.id LIMIT 5", "type")


@pytest.mark.parametrize(
    "query",
    [
        "MATCH (s:Service) RETURN s {.name}['name'] AS c LIMIT 5",
        "MATCH (s:Service) RETURN COLLECT { MATCH (x:Service) RETURN x.id }[0] AS c LIMIT 5",
        "MATCH (s:Service) RETURN {id: 1}['id'] AS c LIMIT 5",
    ],
)
def test_a_subscript_after_a_closing_brace_is_rejected(query):
    rejected(query, "subscript")


@pytest.mark.parametrize(
    "query",
    [
        "MATCH (s:Service) RETURN (s IN [1]) AS c LIMIT 5",
        "MATCH (s:Service) RETURN [s IN [1]] AS c LIMIT 5",
        "MATCH (s:Service) RETURN any(s IN [1] WHERE true) AS c LIMIT 5",
    ],
)
def test_an_entity_name_is_not_reused_as_a_comprehension_variable(query):
    rejected(query, "is a node, relationship or path")


def test_a_parameter_cannot_stand_in_for_a_property_map():
    rejected("MATCH (s:Service $props) RETURN s.name LIMIT 5")
    rejected("MATCH (a:Step)-[:NEXT]->(b:Step $props) RETURN b.id LIMIT 5")
    accepted("MATCH (s:Service {id: $sid}) RETURN s.name LIMIT 5")


def test_a_subquery_word_used_as_a_label_does_not_open_a_subquery():
    # With a custom schema a label may be spelled like EXISTS / COUNT / COLLECT.
    from citizengraph.guardrail.schema import Schema

    custom = Schema(
        labels=frozenset({"Count", "Service"}),
        relationship_types=frozenset(),
        properties=frozenset({"name"}),
    )
    query = "MATCH (s:Count {review_status: 'reviewed'}) RETURN s.name LIMIT 5"
    result = validate_cypher(query, schema=custom)
    assert result.ok is False
    assert any("unknown property 'review_status'" in r for r in result.reasons)
    assert validate_cypher("MATCH (s:Count {name: 'x'}) RETURN s.name LIMIT 5", schema=custom).ok


def test_queries_that_stay_accepted_read_only_allow_listed_data():
    # Reported by the review and left alone on purpose: nothing outside the allow-list.
    accepted("MATCH (s:Service) RETURN s {} AS c LIMIT 5")
    accepted("MATCH (all:Service) RETURN all.name AS NAME ORDER BY NAME LIMIT 5")
    accepted(
        "MATCH (s:Service) RETURN COLLECT { MATCH (x:Requirement) RETURN x.text } AS c LIMIT 1"
    )


def test_bounded_variable_length_is_rejected_too():
    # These two were pinned as valid in tests/test_guardrail_patterns.py until this change.
    for query in (
        "MATCH (s:Service)-[:HAS_STEP*1..3]->(st:Step) RETURN st.id LIMIT 5",
        "MATCH (a:Step)-[r:NEXT*1..2]->(b:Step) RETURN b.id LIMIT 5",
    ):
        rejected(query, "variable-length, quantified or filtered")


# ------------------------------------------------- found by the independent review, round 2
# A chain whose end is not shaped like a node (`(s.name)`, `(1)`) was passed over by the
# node checks, so the placement rule never saw the pattern.


@pytest.mark.parametrize(
    "query",
    [
        "MATCH (s:Service) RETURN (s.name)-[:REQUIRES]->(:Requirement) LIMIT 5",
        "MATCH (s:Service) RETURN (s.id)-[:REQUIRES]->(s) LIMIT 5",
        "MATCH (s:Service) RETURN (1)-[:REQUIRES]->(:Requirement) LIMIT 5",
        "MATCH (s:Service) WHERE (s)-[:REQUIRES]->(s.name) RETURN s.name LIMIT 5",
        ("MATCH (s:Service) RETURN s.name ORDER BY (s.name)-[:REQUIRES]->(:Requirement) LIMIT 5"),
        "MATCH (s:Service) RETURN (s.name)<-[:OFFERS]-(:Office) LIMIT 5",
        "MATCH (s:Service) RETURN (:Office)-[:OFFERS]->(s.name) LIMIT 5",
        "MATCH (s:Service) RETURN s.name-[:REQUIRES]->(:Requirement) LIMIT 5",
        "MATCH (s:Service) RETURN [1]-[:REQUIRES]->(:Requirement) LIMIT 5",
        "MATCH (s:Service) RETURN (s)-[:REQUIRES]->(s.id)-[:REQUIRES]->(:Requirement) LIMIT 5",
    ],
)
def test_a_relationship_needs_a_node_pattern_on_both_sides(query):
    rejected(query, "a relationship must be written")


def test_a_pattern_value_right_before_a_clause_word_is_rejected():
    rejected(
        "MATCH (s:Service) RETURN (s)-[:REQUIRES]->(:Requirement) LIMIT 5",
        "a pattern outside MATCH",
    )
    # NOT makes it a boolean: accepted, and nothing but true/false comes back.
    accepted("MATCH (s:Service) RETURN NOT (s)-[:HAS_FEE]->(:Fee) LIMIT 5")


def test_map_keys_are_property_names():
    # Safe-side over-rejection: a result map may only use allow-listed property names as keys.
    rejected("MATCH (s:Service) RETURN {myKey: s.name} AS m LIMIT 5", "unknown property")
    accepted("MATCH (s:Service) RETURN {name: s.name} AS m LIMIT 5")


# ------------------------------------------------------------------------- fail closed


def test_the_new_passes_never_raise_on_broken_input():
    for query in (
        "MATCH (s:Service) RETURN",
        "MATCH (s:Service) RETURN AS",
        "MATCH = (s:Service) RETURN s.name LIMIT 5",
        "MATCH (s:Service) RETURN * *",
        "AS AS AS",
        "IS",
        "MATCH (s:Service) WHERE s IS",
        "MATCH (s:Service)-[",
        "MATCH (s:Service)-[:REQUIRES]",
        "MATCH (s:Service)-[:REQUIRES]-",
        "MATCH (s:Service)-[:REQUIRES]->",
        "RETURN count( LIMIT 5",
        "RETURN {: LIMIT 5",
        "\\",
        "\\u",
    ):
        result = validate_cypher(query)
        assert isinstance(result, ValidationResult)
        assert result.ok is False, query
        assert result.reasons
