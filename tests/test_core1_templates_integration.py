"""Real-Neo4j check of the canonical Core 1 queries. Skipped by default (`-m integration`).

Runs every template in ``core1/templates.py`` against a real Neo4j holding the curated seed and
compares the rows with the in-memory graph helpers (``InMemoryGraph``), for every service and for
every combination of variant values (plus combinations that include dimensions a service does not
link, which must filter nothing).

Status: the session 5 tests ran once against an embedded Neo4j 5.26.12 Community started from the
Maven Central jars (Bolt on, auth off; steps in docs/training_notes.md) and passed; a deliberately
naive variant filter made three of them fail, so the comparison is not vacuous. The session 5b
tests (the 18 new shapes, and execution accuracy of gold and of the baseline) were run the same
way; see docs/training_notes.md for the result. NOT run against the Docker image or a server
install.

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
from citizengraph.core1.targets import Request, Target, build_request_query
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
    # with the suspect records too: every answer is compared with InMemoryGraph (the full seed)
    _loadmod().write_seed(
        driver, seed, batch_size=25, include_unreviewed_links=True, include_suspect_records=True
    )
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


# ---- session 5b: the new shapes ---------------------------------------------------------------


def request_of(*targets: tuple[str, str]) -> Request:
    return Request(targets=[Target(kind=k, id=i) for k, i in targets], phrase="test", language="en")


def ask(driver, request: Request, intent: str, shape: str, variant_ids=()):
    q = build_request_query(request, intent, shape, list(variant_ids))
    return run(driver, q.cypher, **q.params)


def service_request(mem: InMemoryGraph, sid: str, *extra: tuple[str, str]) -> Request:
    return request_of(("service", sid), ("office", mem.service(sid).office_id), *extra)


def variant_ids_of(combo: dict[str, str]) -> list[str]:
    return sorted(f"{d}:{v}" for d, v in combo.items())


def leaf_count(mem: InMemoryGraph, sid: str) -> int:
    return sum(1 for r in mem.requirements(sid) if not r.group)


def test_doc_services_doc_where_and_doc_in_service(driver, mem):
    agencies = _agency_names(mem)
    for doc in ("cedula", "marriage certificate", "affidavit", "proof of payment", "clearance"):
        rows = [r for r in mem.seed.requirements if doc in r.text.lower()]
        assert rows
        got = ask(driver, request_of(("document", doc)), "requirements", "doc_services")
        want = sorted((r.service_id, r.id) for r in rows)
        assert [(x["s.id"], x["r.id"]) for x in got] == want, doc
        got = ask(driver, request_of(("document", doc)), "where_to_secure", "doc_where")
        want = sorted(
            (r.service_id, r.id, agencies[slug(r.secured_at)]) for r in rows if r.secured_at
        )
        assert [(x["s.id"], x["r.id"], x["a.name"]) for x in got] == want, doc
        for sid in sorted({r.service_id for r in rows}):
            for combo in combos_for(mem, sid):
                req = service_request(mem, sid, ("document", doc))
                got = ask(driver, req, "requirements", "doc_in_service", variant_ids_of(combo))
                want = sorted(r.id for r in mem.requirements(sid, combo) if doc in r.text.lower())
                assert [x["r.id"] for x in got] == want, (doc, sid, combo)


def test_agency_services(driver, mem):
    names = _agency_names(mem)
    for aid, name in names.items():
        per_service: dict[str, int] = {}
        for r in mem.seed.requirements:
            if r.secured_at and slug(r.secured_at) == aid:
                per_service[r.service_id] = per_service.get(r.service_id, 0) + 1
        got = ask(driver, request_of(("agency", aid)), "where_to_secure", "agency_services")
        assert [(x["s.id"], x["n"], x["a.name"]) for x in got] == [
            (sid, n, name) for sid, n in sorted(per_service.items())
        ], aid


def test_office_listings_counts_and_who_may_avail(driver, mem):
    for office in mem.seed.offices:
        oid = office.id
        services = sorted(mem.services(oid), key=lambda s: s.id)
        req = request_of(("office", oid))
        got = ask(driver, req, "office", "office_services")
        assert [(x["s.id"], x["o.name"]) for x in got] == [(s.id, office.name) for s in services]
        assert ask(driver, req, "office", "office_count") == [
            {"o.name": office.name, "n": len(services)}
        ]
        got = ask(driver, req, "who_may_avail", "office_who")
        assert [(x["s.id"], x["s.who_may_avail"]) for x in got] == [
            (s.id, s.who_may_avail) for s in services
        ]
        got = ask(driver, req, "requirements", "office_req_counts")
        want = sorted(
            ((s.id, leaf_count(mem, s.id)) for s in services), key=lambda t: (-t[1], t[0])
        )
        assert [(x["s.id"], x["n"]) for x in got] == want, oid


def test_cheapest_and_no_fee_rows(driver, mem):
    for office in mem.seed.offices:
        oid = office.id
        req = request_of(("office", oid))
        lows = {
            s.id: min(f.amount_min for f in mem.fees(s.id))
            for s in mem.services(oid)
            if mem.fees(s.id)
        }
        got = ask(driver, req, "fees", "cheapest")
        assert [(x["s.id"], x["lowest"]) for x in got] == sorted(
            lows.items(), key=lambda t: (t[1], t[0])
        )[:5], oid
        got = ask(driver, req, "fees", "no_fee_rows")
        assert [x["s.id"] for x in got] == sorted(
            s.id for s in mem.services(oid) if not mem.fees(s.id)
        ), oid


def test_office_prereqs(driver, mem):
    agencies = _agency_names(mem)
    offices = {o.id: o.name for o in mem.seed.offices}
    office_of_agency = {
        slug(link.agency): link.office_id
        for link in mem.links("agency_is_office")
        if link.agency and link.office_id
    }
    seen_rows = 0
    for oid in offices:
        want = []
        for s in sorted(mem.services(oid), key=lambda s: s.id):
            for r in mem.requirements(s.id):
                served = [(d, mem.office_of(d.id)) for d in mem.satisfied_by(r.id)] or [
                    (None, None)
                ]
                slug_ = slug(r.secured_at) if r.secured_at else None
                o2 = office_of_agency.get(slug_) if slug_ else None
                for d, o1 in served:
                    keep = (d is not None and o1.id != oid) or (o2 is not None and o2 != oid)
                    if keep:
                        want.append(
                            (
                                s.id, r.id,
                                d.name if d else None, o1.name if o1 else None,
                                agencies[slug_] if o2 else None, offices[o2] if o2 else None,
                            )
                        )  # fmt: skip
        got = ask(driver, request_of(("office", oid)), "where_to_secure", "office_prereqs")
        got = [
            (x["s.id"], x["r.id"], x["d.name"], x["o1.name"], x["a.name"], x["o2.name"])
            for x in got
        ]
        assert sorted(got, key=_sort_key) == sorted(want, key=_sort_key), oid
        seen_rows += len(want)
    assert seen_rows > 0


def test_fees_total_and_fee_time(driver, mem):
    for sid in services(mem):
        if not mem.fees(sid):
            continue
        svc = mem.service(sid)
        for combo in combos_for(mem, sid):
            ids = variant_ids_of(combo)
            kept = mem.fees(sid, combo)
            got = ask(driver, service_request(mem, sid), "fees", "fees_total", ids)
            if not kept:
                assert got == [], (sid, combo)
            else:
                unresolved = sum(1 for f in kept if f.condition_text and not f.variant_ids)
                assert got == [
                    {
                        "s.total_fee_text": svc.total_fee_text,
                        "total_min": sum(f.amount_min for f in kept),
                        "total_max": sum(f.amount_max for f in kept),
                        "n_fees": len(kept),
                        "n_unresolved": unresolved,
                    }
                ], (sid, combo)
            kept_ids = {f.id for f in kept}
            want = []
            for st in mem.steps(sid):
                fees = sorted(
                    (f for f in mem.fees_of_step(st.id) if f.id in kept_ids), key=lambda f: f.id
                )
                want += [(st.id, f.id) for f in fees] or [(st.id, None)]
            rows = ask(driver, service_request(mem, sid), "fees", "fee_time", ids)
            assert [(x["st.id"], x["f.id"]) for x in rows] == want, (sid, combo)


def test_longest_and_external_steps(driver, mem):
    for sid in services(mem):
        steps = mem.steps(sid)
        timed = [st for st in steps if st.duration.minutes_max is not None]
        got = ask(driver, service_request(mem, sid), "processing_time", "longest_step")
        if timed:
            best = min(timed, key=lambda st: (-st.duration.minutes_max, st.order))
            assert [x["st.id"] for x in got] == [best.id], sid
        else:
            assert got == []
        got = ask(driver, service_request(mem, sid), "steps", "external_steps")
        assert [x["st.id"] for x in got] == [st.id for st in steps if st.external_agency], sid


def test_comparisons(driver, mem):
    ids = services(mem)
    pairs = [("business_permit", "occupational_permit"), ("cockfight_permit", "fishing_permit"),
             ("birth_registration_delayed", "cho_sanitary_permit"), (ids[0], ids[-1])]  # fmt: skip
    for a, b in pairs:
        req = request_of(("service", a), ("service", b))
        rows = ask(driver, req, "fees", "compare_fees")
        want = []
        for sid in sorted((a, b)):
            fees = mem.fees(sid)
            want.append((
                sid, len(fees),
                min((f.amount_min for f in fees), default=None),
                max((f.amount_max for f in fees), default=None),
            ))  # fmt: skip
        assert [(x["s.id"], x["n_fees"], x["lowest"], x["highest"]) for x in rows] == want
        rows = ask(driver, req, "requirements", "compare_requirements")
        assert [(x["s.id"], x["n_requirements"], x["n_steps"]) for x in rows] == [
            (sid, leaf_count(mem, sid), len(mem.steps(sid))) for sid in sorted((a, b))
        ]
        rows = ask(driver, req, "processing_time", "compare_time")
        assert [(x["s.id"], x["st.id"]) for x in rows] == [
            (sid, st.id) for sid in sorted((a, b)) for st in mem.steps(sid)
        ]


# ---- session 5b: execution accuracy -----------------------------------------------------------


def test_every_gold_query_of_the_dataset_executes_and_equals_itself(driver, mem):
    """The gold of every example runs on the real graph (a failing gold would make execution
    accuracy meaningless), and scoring the gold as predictions gives execution accuracy 1."""
    gen = load("generate_dataset")
    ev = load("eval_generate")
    ds = gen.build_dataset(seed=0, eval_fraction=0.05)
    rows = ds.examples["test_synthetic"][::3] + ds.examples["test_unseen_shape"][::5]
    items = [ev.Item(e.id, [], e.completion, {**e.meta(), "params": e.params}) for e in rows]
    executor = ev.Neo4jExecutor(driver)
    report = ev.score(items, [e.completion for e in rows], executor=executor)
    rates = report.overall.rates()
    assert rates["execution_accuracy"] == 1.0 and rates["exact_match"] == 1.0
    assert rates["n"] > 300


def test_a_wrong_shape_is_caught_by_execution_accuracy(driver, mem):
    gen = load("generate_dataset")
    ev = load("eval_generate")
    ds = gen.build_dataset(seed=0, eval_fraction=0.05)
    counts = [e for e in ds.examples["test_synthetic"] if e.shape == "count"][:10]
    lists = {e.template_key: e for e in ds.examples["test_synthetic"] if e.shape == "list"}
    items = [ev.Item(e.id, [], e.completion, {**e.meta(), "params": e.params}) for e in counts]
    wrong = []
    for e in counts:
        intent = e.template_key.split("/")[0]
        key = f"{intent}/list/{str(bool(e.variant_ids)).lower()}"
        wrong.append(lists[key].completion if key in lists else "")
    executor = ev.Neo4jExecutor(driver)
    rates = ev.score(items, wrong, executor=executor).overall.rates()
    assert rates["execution_accuracy"] == 0.0 and rates["intent_accuracy"] > 0.5


def test_the_baseline_scored_with_execution_accuracy(driver, mem):
    gen = load("generate_dataset")
    ev = load("eval_generate")
    ds = gen.build_dataset(seed=0, eval_fraction=0.05)
    rows = ds.examples["test_synthetic"][::4]
    items = [ev.Item(e.id, [], e.completion, {**e.meta(), "params": e.params}) for e in rows]
    outputs = ev.baseline_outputs(items)
    executor = ev.Neo4jExecutor(driver)
    base = ev.score(items, outputs, executor=executor).overall.rates()
    perfect = ev.score(items, [e.completion for e in rows], executor=executor).overall.rates()
    assert perfect["execution_accuracy"] == 1.0
    assert base["execution_accuracy"] < 0.5  # it cannot do counts, totals, comparisons, lookups
