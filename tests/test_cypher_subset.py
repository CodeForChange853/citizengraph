"""The test interpreter itself (``cypher_subset.py``), on small hand-made graphs.

If this interpreter were wrong, the semantic tests in ``test_core1_semantics.py`` could pass or
fail for the wrong reason, so its three-valued logic, OPTIONAL MATCH, aggregation and ordering are
pinned here. Nothing here needs Neo4j.
"""

from __future__ import annotations

import pytest
from cypher_subset import PropertyGraph, Unsupported, graph_from_plan, run_cypher

from citizengraph.graph.loader import DEFAULT_SEED_DIR, load_seed


@pytest.fixture
def g() -> PropertyGraph:
    graph = PropertyGraph()
    a = graph.add_node("Office", {"id": "a", "name": "Office A"})
    b = graph.add_node("Office", {"id": "b", "name": "Office B"})
    s1 = graph.add_node("Service", {"id": "s1", "name": "One"})
    s2 = graph.add_node("Service", {"id": "s2", "name": "Two"})
    s3 = graph.add_node("Service", {"id": "s3", "name": "Three"})
    for office, svc in ((a, s1), (a, s2), (b, s3)):
        graph.add_rel("OFFERS", office, svc)
    f1 = graph.add_node("Fee", {"id": "f1", "amount_min": 10, "amount_max": 20})
    f2 = graph.add_node("Fee", {"id": "f2", "amount_min": 5, "amount_max": 5})
    graph.add_rel("HAS_FEE", s1, f1)
    graph.add_rel("HAS_FEE", s1, f2)  # s2 and s3 have no fee rows
    r1 = graph.add_node("Requirement", {"id": "r1", "text": "Cedula", "group": False})
    r2 = graph.add_node("Requirement", {"id": "r2", "text": "Group", "group": True})
    graph.add_rel("REQUIRES", s1, r1)
    graph.add_rel("REQUIRES", s1, r2)
    return graph


def rows(g, cypher, **params):
    return run_cypher(g, cypher, params)


def test_match_with_property_map_and_direction(g):
    got = rows(
        g, "MATCH (o:Office {id: $o})-[:OFFERS]->(s:Service)\nRETURN s.id\nORDER BY s.id", o="a"
    )
    assert got == [{"s.id": "s1"}, {"s.id": "s2"}]
    got = rows(g, "MATCH (s:Service {id: $s})<-[:OFFERS]-(o:Office)\nRETURN o.name", s="s3")
    assert got == [{"o.name": "Office B"}]


def test_optional_match_keeps_the_row_with_nulls_and_count_ignores_them(g):
    got = rows(
        g,
        "MATCH (s:Service)\nOPTIONAL MATCH (s)-[:HAS_FEE]->(f:Fee)\n"
        "RETURN s.id, count(f) AS n, min(f.amount_min) AS lo, max(f.amount_max) AS hi\nORDER BY s.id",
    )
    assert got == [
        {"s.id": "s1", "n": 2, "lo": 5, "hi": 20},
        {"s.id": "s2", "n": 0, "lo": None, "hi": None},
        {"s.id": "s3", "n": 0, "lo": None, "hi": None},
    ]


def test_a_plain_match_drops_rows_without_a_match(g):
    got = rows(g, "MATCH (s:Service)-[:HAS_FEE]->(f:Fee)\nRETURN s.id, count(f) AS n")
    assert got == [{"s.id": "s1", "n": 2}]


def test_where_uses_three_valued_logic(g):
    # s2 has no fee: f is null, so `f.amount_min > 1` is null and the row is dropped, not kept
    q = (
        "MATCH (s:Service)\nOPTIONAL MATCH (s)-[:HAS_FEE]->(f:Fee)\nWITH s, f\n"
        "WHERE f IS NOT NULL AND f.amount_min > $x\nRETURN s.id, f.id\nORDER BY f.id"
    )
    assert rows(g, q, x=7) == [{"s.id": "s1", "f.id": "f1"}]
    # NOT null is null (dropped); a false AND null is false; true OR null is true
    q = (
        "MATCH (s:Service)\nOPTIONAL MATCH (s)-[:HAS_FEE]->(f:Fee)\nWITH s, f\n"
        "WHERE NOT f.amount_min > 7\nRETURN s.id, f.id"
    )
    assert rows(g, q) == [{"s.id": "s1", "f.id": "f2"}]
    q = (
        "MATCH (s:Service)\nOPTIONAL MATCH (s)-[:HAS_FEE]->(f:Fee)\nWITH s, f\n"
        "WHERE f IS NULL OR f.amount_min > 7\nRETURN s.id, f.id\nORDER BY s.id"
    )
    assert [(r["s.id"], r["f.id"]) for r in rows(g, q)] == [
        ("s1", "f1"),
        ("s2", None),
        ("s3", None),
    ]


def test_inequality_with_a_null_side_is_not_true(g):
    # the shape office_prereqs depends on: `o1.id <> $oid` must not hold when o1 is null
    q = (
        "MATCH (s:Service)\nOPTIONAL MATCH (s)-[:HAS_FEE]->(f:Fee)\nWITH s, f\n"
        "WHERE f.id <> $x\nRETURN s.id, f.id"
    )
    assert rows(g, q, x="f1") == [{"s.id": "s1", "f.id": "f2"}]


def test_in_list_contains_and_tolower(g):
    assert rows(
        g, "MATCH (s:Service)\nWHERE s.id IN [$a, $b]\nRETURN s.id\nORDER BY s.id", a="s3", b="zzz"
    ) == [{"s.id": "s3"}]
    got = rows(
        g,
        "MATCH (s:Service)-[:REQUIRES]->(r:Requirement)\nWHERE toLower(r.text) CONTAINS $d\nRETURN r.id",
        d="ced",
    )
    assert got == [{"r.id": "r1"}]


def test_count_subquery_and_limit(g):
    got = rows(
        g,
        "MATCH (s:Service)\n"
        "RETURN s.id, COUNT { (s)-[:REQUIRES]->(r:Requirement) WHERE r.group = false } AS n, "
        "COUNT { (s)-[:HAS_FEE]->(:Fee) } AS m\nORDER BY s.id\nLIMIT 2",
    )
    assert got == [{"s.id": "s1", "n": 1, "m": 2}, {"s.id": "s2", "n": 0, "m": 0}]


def test_order_by_puts_nulls_last_ascending_and_first_descending(g):
    q = (
        "MATCH (s:Service)\nOPTIONAL MATCH (s)-[:HAS_FEE]->(f:Fee)\n"
        "RETURN s.id, min(f.amount_min) AS lo\nORDER BY lo{}, s.id"
    )
    assert [r["s.id"] for r in rows(g, q.format(""))] == ["s1", "s2", "s3"]
    assert [r["s.id"] for r in rows(g, q.format(" DESC"))] == ["s2", "s3", "s1"]


def test_an_aggregate_over_no_rows_still_returns_one_row(g):
    assert rows(g, "MATCH (s:Service {id: $s})\nRETURN count(s) AS n", s="nope") == [{"n": 0}]
    assert rows(g, "MATCH (s:Service {id: $s})\nRETURN s.id, count(s) AS n", s="nope") == []


@pytest.mark.parametrize(
    "cypher",
    [
        "MATCH (n) RETURN n",
        "MATCH (s:Service)-[:OFFERS|HAS_FEE]->(x:Fee) RETURN s.id",
        "MATCH (s:Service)-[:OFFERS*]->(x:Fee) RETURN s.id",
        "MATCH (s:Service) RETURN size(s.id)",
        "MATCH (s:Service) WITH count(s) AS n RETURN n",
        "MATCH (s:Service) RETURN s.id UNION MATCH (o:Office) RETURN o.id",
        "MERGE (s:Service {id: 'x'}) RETURN s",
    ],
)
def test_anything_outside_the_subset_raises_instead_of_passing(g, cypher):
    with pytest.raises(Unsupported):
        rows(g, cypher)


def test_the_loader_plan_becomes_a_graph_with_the_same_counts():
    import importlib.util
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "citizengraph_admin_load_subset", root / "graph/load.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    seed = load_seed(DEFAULT_SEED_DIR)
    # the full seed: the counts below are the seed's own, so suspect records are not held back
    plan = module.build_plan(seed, include_unreviewed_links=True, include_suspect_records=True)
    graph = graph_from_plan(plan)
    assert len(graph.nodes["Service"]) == len(seed.services)
    assert len(graph.nodes["Requirement"]) == len(seed.requirements)
    offers = rows(graph, "MATCH (o:Office)-[:OFFERS]->(s:Service)\nRETURN count(s) AS n")
    assert offers == [{"n": len(seed.services)}]
    charges = rows(graph, "MATCH (st:Step)-[:CHARGES]->(f:Fee)\nRETURN count(f) AS n")
    assert charges == [{"n": sum(1 for f in seed.fees if f.step_id)}]
