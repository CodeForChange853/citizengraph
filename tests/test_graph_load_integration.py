"""Real-Neo4j check of graph/load.py. Skipped by default (`-m integration` to run).

Point it at an EMPTY throwaway database:

    NEO4J_TEST_URI=bolt://localhost:7687 NEO4J_TEST_USER=neo4j NEO4J_TEST_PASSWORD=... \
        pytest -m integration tests/test_graph_load_integration.py

The test itself only reads; every write goes through graph/load.py.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from collections import Counter
from pathlib import Path

import pytest
from graph_fixtures import staff_names

from citizengraph.graph.loader import DEFAULT_SEED_DIR, load_seed
from citizengraph.graph.memory import InMemoryGraph

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[1]


def _loadmod():
    spec = importlib.util.spec_from_file_location("citizengraph_admin_load_it", ROOT / "graph/load.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def driver():
    uri = os.environ.get("NEO4J_TEST_URI")
    password = os.environ.get("NEO4J_TEST_PASSWORD")
    if not uri or not password:
        pytest.skip("set NEO4J_TEST_URI and NEO4J_TEST_PASSWORD to run against a real Neo4j")
    from neo4j import GraphDatabase

    drv = GraphDatabase.driver(uri, auth=(os.environ.get("NEO4J_TEST_USER", "neo4j"), password))
    with drv.session() as s:
        if s.execute_read(lambda tx: tx.run("MATCH (n) RETURN count(n) AS c").single()["c"]):
            pytest.skip("database is not empty; use an empty throwaway database")
    yield drv
    drv.close()


def counts(driver):
    def work(tx):
        nodes = {r["l"]: r["c"] for r in tx.run(
            "MATCH (n) UNWIND labels(n) AS l RETURN l, count(*) AS c")}
        rels = {r["t"]: r["c"] for r in tx.run(
            "MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS c")}
        return nodes, rels

    with driver.session() as s:
        return s.execute_read(work)


@pytest.fixture(scope="module")
def loaded(driver):
    mod = _loadmod()
    seed = load_seed(DEFAULT_SEED_DIR)
    mod.write_seed(driver, seed, batch_size=25)
    first = counts(driver)
    mod.write_seed(driver, seed, batch_size=25)
    second = counts(driver)
    return seed, first, second


def test_second_run_changes_nothing(loaded):
    _, first, second = loaded
    assert first == second


def test_node_and_relationship_counts_match_the_seed(loaded):
    seed, (nodes, rels), _ = loaded
    assert nodes["Service"] == 13
    assert nodes["Office"] == 2
    assert nodes["Requirement"] == len(seed.requirements)
    assert nodes["Step"] == len(seed.steps)
    assert nodes["Fee"] == len(seed.fees)
    assert nodes["Variant"] == len(seed.variants)
    assert rels["HAS_STEP"] == len(seed.steps)
    assert rels["NEXT"] == len(seed.steps) - len(seed.services)
    assert rels["REQUIRES"] == len(seed.requirements)
    assert rels["HAS_FEE"] == len(seed.fees)


def test_constraints_exist(driver, loaded):
    with driver.session() as s:
        n = s.execute_read(lambda tx: len(list(tx.run("SHOW CONSTRAINTS"))))
    assert n >= 8


def test_graph_answers_match_the_in_memory_graph(driver, loaded):
    seed, _, _ = loaded
    mem = InMemoryGraph(seed)
    for svc in seed.services:
        want = Counter(r.text for r in mem.requirements(svc.id))
        with driver.session() as s:
            got = s.execute_read(
                lambda tx, sid=svc.id: [
                    r["t"]
                    for r in tx.run(
                        "MATCH (s:Service {id: $sid})-[:REQUIRES]->(r:Requirement) "
                        "RETURN r.text AS t",
                        sid=sid,
                    )
                ]
            )
        assert Counter(got) == want

        want_steps = [st.id for st in mem.steps(svc.id)]
        with driver.session() as s:
            got_steps = s.execute_read(
                lambda tx, sid=svc.id: [
                    r["id"]
                    for r in tx.run(
                        "MATCH (s:Service {id: $sid})-[:HAS_STEP]->(t:Step) "
                        "RETURN t.id AS id ORDER BY t.order",
                        sid=sid,
                    )
                ]
            )
        assert got_steps == want_steps


def test_no_staff_name_is_stored_anywhere(driver, loaded):
    seed, _, _ = loaded
    names = staff_names(seed)
    assert names
    with driver.session() as s:
        for name in sorted(names):
            hit = s.execute_read(
                lambda tx, n=name: tx.run(
                    "MATCH (x) WHERE any(k IN keys(x) WHERE toString(x[k]) CONTAINS $n) "
                    "RETURN count(x) AS c",
                    n=n,
                ).single()["c"]
            )
            assert hit == 0, name
