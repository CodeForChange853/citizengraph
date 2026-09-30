"""Real-Neo4j check of the canonical Core 1 queries. Skipped by default (`-m integration`).

Runs every template in ``core1/templates.py`` against a real Neo4j holding the curated seed and
compares the rows with the in-memory graph helpers (``InMemoryGraph``), for every service and for
every combination of variant values (plus combinations that include dimensions a service does not
link, which must filter nothing).

Status: run once (session 5) against an embedded Neo4j 5.26.12 Community started from the Maven
Central jars (Bolt on, auth off; steps in docs/training_notes.md): all 9 tests passed, and a
deliberately naive variant filter made three of them fail, so the comparison is not vacuous.
It has NOT been run against the Docker image or a server install.

How to run (an EMPTY throwaway database; this file loads the seed itself, WITH the suggested
cross-office links, so do not share the database with tests/test_graph_load_integration.py, which
expects those links to be held back):

    NEO4J_TEST_URI=bolt://localhost:7687 NEO4J_TEST_USER=neo4j NEO4J_TEST_PASSWORD=... \\
        pytest -m integration tests/test_core1_templates_integration.py

The test itself only reads (``session.execute_read``); every write goes through graph/load.py.
"""

from __future__ import annotations

import importlib.util
import itertools
import os
import sys
from pathlib import Path

import pytest
from test_training_common import load

from citizengraph.core1 import templates as T
from citizengraph.core1.slots import Slots
from citizengraph.graph.ids import clean_name, slug
from citizengraph.graph.loader import DEFAULT_SEED_DIR, load_seed
from citizengraph.graph.memory import InMemoryGraph

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[1]
G = load("generate_dataset")


def _loadmod():
    spec = importlib.util.spec_from_file_location(
        "citizengraph_admin_load_core1_it", ROOT / "graph/load.py"
    )
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


@pytest.fixture(scope="module")
def mem(driver):
    seed = load_seed(DEFAULT_SEED_DIR)
    _loadmod().write_seed(driver, seed, batch_size=25, include_unreviewed_links=True)
    return InMemoryGraph(seed)


def run(driver, cypher: str, **params):
    def work(tx):
        return [record.data() for record in tx.run(cypher, **params)]

    with driver.session() as session:
        return session.execute_read(work)


def query(driver, slots: Slots, shape: str):
    q = T.build_query(slots, shape)
    return run(driver, q.cypher, **q.params)


def slots_for(service_id: str, intent: str, combo: dict[str, str]) -> Slots:
    return Slots(service_id=service_id, intent=intent, variants=combo, phrase="test", language="en")


def combos_for(mem: InMemoryGraph, service_id: str) -> list[dict[str, str]]:
    combos = [dict(c) for c in G.variant_combos(mem, service_id)]
    by_dimension: dict[str, list[str]] = {}
    for v in mem.seed.variants:
        by_dimension.setdefault(v.dimension, []).append(v.value)
    # one value from every dimension of the catalogue, including dimensions the service does
    # not link (they must not filter anything)
    for pick in (0, -1):
        combos.append({d: values[pick] for d, values in sorted(by_dimension.items())})
    return combos


def services(mem: InMemoryGraph) -> list[str]:
    return [s.id for s in mem.services()]


def test_every_template_is_accepted_by_neo4j_as_a_read_query(driver, mem):
    for template in T.TEMPLATES.values():
        params = {"sid": "business_permit"}
        if template.filtered:
            params["variant_ids"] = ["business_type:corporation"]
        run(driver, "EXPLAIN " + template.cypher, **params)  # raises on a syntax error


def test_requirements_list_and_count(driver, mem):
    for sid in services(mem):
        for combo in combos_for(mem, sid):
            want = mem.requirements(sid, combo)
            rows = query(driver, slots_for(sid, "requirements", combo), "list")
            assert [r["r.id"] for r in rows] == sorted(r.id for r in want), (sid, combo)
            by_id = {r.id: r for r in want}
            for row in rows:
                rec = by_id[row["r.id"]]
                assert row["r.text"] == rec.text
                assert row["r.group"] == rec.group
                assert row["r.parent_id"] == rec.parent_id
                assert row["r.min_required"] == rec.min_required
                assert row["r.condition_text"] == rec.condition_text
            count = query(driver, slots_for(sid, "requirements", combo), "count")
            assert count == [{"n": sum(1 for r in want if not r.group)}], (sid, combo)


def test_requirements_ignore_variants_in_unfiltered_intents(driver, mem):
    # steps have no variant links: variants in the slots must not change the result
    for sid in services(mem):
        plain = query(driver, slots_for(sid, "steps", {}), "list")
        for combo in combos_for(mem, sid):
            assert query(driver, slots_for(sid, "steps", combo), "list") == plain


def test_fees_list(driver, mem):
    for sid in services(mem):
        for combo in combos_for(mem, sid):
            want = mem.fees(sid, combo)
            rows = query(driver, slots_for(sid, "fees", combo), "list")
            assert [r["f.id"] for r in rows] == sorted(f.id for f in want), (sid, combo)
            by_id = {f.id: f for f in want}
            for row in rows:
                fee = by_id[row["f.id"]]
                assert row["f.label"] == fee.label
                assert row["f.amount_min"] == fee.amount_min
                assert row["f.amount_max"] == fee.amount_max
                assert row["f.unit"] == fee.unit
                assert row["f.note"] == fee.note
                assert row["f.condition_text"] == fee.condition_text


def test_fees_per_step(driver, mem):
    for sid in services(mem):
        for combo in combos_for(mem, sid):
            kept = {f.id for f in mem.fees(sid, combo)}
            want = [
                (st.id, f.id)
                for st in mem.steps(sid)
                for f in sorted(mem.fees_of_step(st.id), key=lambda f: f.id)
                if f.id in kept
            ]
            rows = query(driver, slots_for(sid, "fees", combo), "per_step")
            assert [(r["st.id"], r["f.id"]) for r in rows] == want, (sid, combo)


def test_steps_and_processing_time(driver, mem):
    for sid in services(mem):
        svc = mem.service(sid)
        steps = mem.steps(sid)
        rows = query(driver, slots_for(sid, "steps", {}), "list")
        assert [r["st.id"] for r in rows] == [st.id for st in steps], sid
        assert [r["st.order"] for r in rows] == [st.order for st in steps]
        assert [r["st.citizen_action"] for r in rows] == [st.citizen_action for st in steps]
        assert [r["st.external_agency"] for r in rows] == [st.external_agency for st in steps]
        assert query(driver, slots_for(sid, "steps", {}), "count") == [{"n": len(steps)}]

        rows = query(driver, slots_for(sid, "processing_time", {}), "list")
        assert [r["st.id"] for r in rows] == [st.id for st in steps], sid
        for row, st in zip(rows, steps, strict=True):
            d = st.duration
            assert row["s.total_time_text"] == svc.total_time_text
            assert (row["st.dur_min"], row["st.dur_max"], row["st.dur_unit"]) == (
                d.value_min,
                d.value_max,
                d.unit,
            )
            assert row["st.day_type"] == d.day_type


def test_who_may_avail_and_office(driver, mem):
    for sid in services(mem):
        svc = mem.service(sid)
        assert query(driver, slots_for(sid, "who_may_avail", {}), "list") == [
            {"s.id": sid, "s.name": svc.name, "s.who_may_avail": svc.who_may_avail}
        ]
        office = mem.office_of(sid)
        assert query(driver, slots_for(sid, "office", {}), "list") == [
            {"o.id": office.id, "o.name": office.name}
        ]


def _agency_names(mem: InMemoryGraph) -> dict[str, str]:
    """Agency node name by slug: the first cleaned spelling in seed order (as the loader does)."""
    names: dict[str, str] = {}
    for r in mem.seed.requirements:
        if r.secured_at:
            names.setdefault(slug(r.secured_at), clean_name(r.secured_at))
    return names


def test_where_to_secure(driver, mem):
    agencies = _agency_names(mem)
    for sid in services(mem):
        for combo in combos_for(mem, sid):
            want = sorted(
                (r.id, agencies[slug(r.secured_at)])
                for r in mem.requirements(sid, combo)
                if r.secured_at
            )
            rows = query(driver, slots_for(sid, "where_to_secure", combo), "list")
            assert [(r["r.id"], r["a.name"]) for r in rows] == want, (sid, combo)


def _sort_key(row: tuple) -> tuple:
    return tuple("" if x is None else x for x in row)


def test_where_to_go_first_follows_satisfied_by_and_is_office(driver, mem):
    agencies = _agency_names(mem)
    offices = {o.id: o.name for o in mem.seed.offices}
    office_of_agency = {
        slug(link.agency): offices[link.office_id]
        for link in mem.links("agency_is_office")
        if link.agency and link.office_id
    }
    nonempty = 0
    for sid in services(mem):
        for combo in combos_for(mem, sid):
            want = []
            for r in mem.requirements(sid, combo):
                served = [(d.name, mem.office_of(d.id).name) for d in mem.satisfied_by(r.id)]
                agency = (
                    (agencies[slug(r.secured_at)], office_of_agency[slug(r.secured_at)])
                    if (r.secured_at and slug(r.secured_at) in office_of_agency)
                    else (None, None)
                )
                for (d_name, o1_name), (a_name, o2_name) in itertools.product(
                    served or [(None, None)], [agency]
                ):
                    if d_name is not None or o2_name is not None:
                        want.append((r.id, d_name, o1_name, a_name, o2_name))
            rows = query(driver, slots_for(sid, "where_to_secure", combo), "go_first")
            got = [(r["r.id"], r["d.name"], r["o1.name"], r["a.name"], r["o2.name"]) for r in rows]
            assert sorted(got, key=_sort_key) == sorted(want, key=_sort_key), (sid, combo)
            nonempty += bool(want)
    assert nonempty, "the seed has suggested cross-office links: some service must have rows"
