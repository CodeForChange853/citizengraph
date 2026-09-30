"""What three Core 1 query shapes MEAN, checked without Neo4j.

``test_core1_templates.py`` checks that the templates are valid and well formed, and the
``integration`` tests check them against a real Neo4j, but only when one is running. These tests
run the real template text (``build_request_query``) through the small interpreter in
``cypher_subset.py`` over a graph built from the loader's own plan of the real seed, and compare
the rows with what ``InMemoryGraph`` says. They fail when a change alters the meaning of:

* ``office_prereqs``: prerequisites that point back at the SAME office are left out;
* the ``compare_*`` shapes: both services come back, also when one of them has no fee rows;
* ``agency_services``: the agency is matched by ``Agency.id`` (the slug), never by its name.

The interpreter has never been compared with a real Neo4j here (see ``cypher_subset.py``), so a
pass is evidence about the query text, not a replacement for the integration tests.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from cypher_subset import graph_from_plan, run_cypher

from citizengraph.core1.targets import Request, Target, build_request_query
from citizengraph.core1.templates import ROW_LIMIT, TEMPLATES
from citizengraph.graph.ids import clean_name, slug
from citizengraph.graph.loader import DEFAULT_SEED_DIR, load_seed
from citizengraph.graph.memory import InMemoryGraph

ROOT = Path(__file__).resolve().parents[1]


def _loader_module():
    spec = importlib.util.spec_from_file_location(
        "citizengraph_admin_load_sem", ROOT / "graph/load.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def seed():
    return load_seed(DEFAULT_SEED_DIR)


@pytest.fixture(scope="module")
def mem(seed):
    return InMemoryGraph(seed)


@pytest.fixture(scope="module")
def graph(seed):
    # with the suggested cross-office links, as tests/test_core1_templates_integration.py loads them
    return graph_from_plan(_loader_module().build_plan(seed, include_unreviewed_links=True))


def ask(graph, intent: str, shape: str, *targets: tuple[str, str]):
    request = Request(
        targets=[Target(kind=k, id=i) for k, i in targets], phrase="test", language="en"
    )
    q = build_request_query(request, intent, shape)
    return run_cypher(graph, q.cypher, q.params)


def _sort_key(row: tuple) -> tuple:
    return tuple("" if x is None else x for x in row)


# ---- office_prereqs: same-office links are excluded ---------------------------------------------


def _agency_names(mem: InMemoryGraph) -> dict[str, str]:
    names: dict[str, str] = {}
    for r in mem.seed.requirements:
        if r.secured_at:
            names.setdefault(slug(r.secured_at), clean_name(r.secured_at))
    return names


def _prereq_candidates(mem: InMemoryGraph, oid: str):
    """(service, requirement, [(satisfying service, its office)], (agency slug, its office id))
    for every requirement of an office's services that has ANY cross-requirement link."""
    office_of_agency = {
        slug(link.agency): link.office_id
        for link in mem.links("agency_is_office")
        if link.agency and link.office_id
    }
    for s in sorted(mem.services(oid), key=lambda s: s.id):
        for r in mem.requirements(s.id):
            served = [(d, mem.office_of(d.id)) for d in mem.satisfied_by(r.id)]
            agency = slug(r.secured_at) if r.secured_at else None
            agency_office = office_of_agency.get(agency) if agency else None
            if served or agency_office:
                yield s, r, served, (agency, agency_office)


def _expected_prereqs(mem: InMemoryGraph, oid: str) -> list[tuple]:
    offices = {o.id: o.name for o in mem.seed.offices}
    names = _agency_names(mem)
    want = []
    for s, r, served, (agency, agency_office) in _prereq_candidates(mem, oid):
        for d, o1 in served or [(None, None)]:
            if (d is not None and o1.id != oid) or (agency_office and agency_office != oid):
                want.append(
                    (
                        s.id, r.id, d.name if d else None, o1.name if o1 else None,
                        names[agency] if agency_office else None,
                        offices[agency_office] if agency_office else None,
                    )
                )  # fmt: skip
    return want


def _prereq_rows(graph, oid: str) -> list[tuple]:
    rows = ask(graph, "where_to_secure", "office_prereqs", ("office", oid))
    return [
        (x["s.id"], x["r.id"], x["d.name"], x["o1.name"], x["a.name"], x["o2.name"]) for x in rows
    ]


def test_office_prereqs_match_the_in_memory_graph_for_every_office(mem, graph):
    total = 0
    for office in mem.seed.offices:
        want = _expected_prereqs(mem, office.id)
        assert len(want) <= ROW_LIMIT  # the LIMIT must not be what makes the lists agree
        got = _prereq_rows(graph, office.id)
        assert sorted(got, key=_sort_key) == sorted(want, key=_sort_key), office.id
        total += len(want)
    assert total > 0


def test_office_prereqs_leave_out_prerequisites_inside_the_same_office(mem, graph):
    """The seed links a BPLO requirement to another BPLO service (occupational permit). That is
    not a "go to another office first" item for the BPLO, and must not be listed for it."""
    same_office = []
    for office in mem.seed.offices:
        for s, r, served, (_, agency_office) in _prereq_candidates(mem, office.id):
            only_here = all(o.id == office.id for _, o in served) and agency_office in (
                None,
                office.id,
            )
            if (served or agency_office) and only_here:
                same_office.append((office.id, s.id, r.id))
    assert same_office, "the seed no longer has a same-office link: this test would prove nothing"

    for oid, sid, rid in same_office:
        assert (sid, rid) not in {(s, r) for s, r, *_ in _prereq_rows(graph, oid)}, (oid, rid)

    # and every row that is listed really leaves the office
    for office in mem.seed.offices:
        for row in _prereq_rows(graph, office.id):
            _, _, _, o1_name, _, o2_name = row
            elsewhere = [n for n in (o1_name, o2_name) if n is not None and n != office.name]
            assert elsewhere, (office.id, row)
    # while a cross-office link is kept (CHO sanitary permit is a BPLO prerequisite)
    bplo = {(s, r) for s, r, *_ in _prereq_rows(graph, "bplo")}
    assert ("business_permit", "business_permit-R16") in bplo


# ---- compare shapes return both services ---------------------------------------------------------

PAIRS = [
    ("business_permit", "occupational_permit"),  # both have fee rows
    ("cockfight_permit", "fishing_permit"),  # the second has no fee rows
    ("birth_registration_delayed", "cho_sanitary_permit"),  # none has fee rows, other offices
]


def _pair(mem, a: str, b: str):
    assert a in {s.id for s in mem.services()} and b in {s.id for s in mem.services()}
    return sorted((a, b))


@pytest.mark.parametrize(("a", "b"), PAIRS)
def test_compare_shapes_return_both_services(mem, graph, a, b):
    ids = _pair(mem, a, b)
    targets = (("service", a), ("service", b))

    rows = ask(graph, "fees", "compare_fees", *targets)
    want = []
    for sid in ids:
        fees = mem.fees(sid)
        want.append(
            (
                sid, len(fees),
                min((f.amount_min for f in fees), default=None),
                max((f.amount_max for f in fees), default=None),
            )
        )  # fmt: skip
    assert [(x["s.id"], x["n_fees"], x["lowest"], x["highest"]) for x in rows] == want

    rows = ask(graph, "requirements", "compare_requirements", *targets)
    assert [(x["s.id"], x["n_requirements"], x["n_steps"]) for x in rows] == [
        (sid, sum(1 for r in mem.requirements(sid) if not r.group), len(mem.steps(sid)))
        for sid in ids
    ]

    rows = ask(graph, "processing_time", "compare_time", *targets)
    assert [(x["s.id"], x["st.id"]) for x in rows] == [
        (sid, st.id) for sid in ids for st in mem.steps(sid)
    ]
    assert {x["s.id"] for x in rows} == set(ids)


def test_a_service_without_fee_rows_still_appears_in_compare_fees(mem, graph):
    no_fees = [s.id for s in mem.services() if not mem.fees(s.id)]
    with_fees = [s.id for s in mem.services() if mem.fees(s.id)]
    assert no_fees and with_fees
    a, b = with_fees[0], no_fees[0]
    rows = ask(graph, "fees", "compare_fees", ("service", a), ("service", b))
    assert {x["s.id"]: x["n_fees"] for x in rows} == {a: len(mem.fees(a)), b: 0}


def test_compare_does_not_depend_on_which_service_is_named_first(mem, graph):
    a, b = PAIRS[0]
    for intent, shape in (
        ("fees", "compare_fees"),
        ("requirements", "compare_requirements"),
        ("processing_time", "compare_time"),
    ):
        first = ask(graph, intent, shape, ("service", a), ("service", b))
        second = ask(graph, intent, shape, ("service", b), ("service", a))
        assert first == second and first


# ---- agency_services matches by Agency.id --------------------------------------------------------


AGENCY_QUERY = TEMPLATES[("where_to_secure", "agency_services", False)]  # Target rejects non-slugs


def _services_needing(mem: InMemoryGraph, aid: str) -> dict[str, int]:
    per_service: dict[str, int] = {}
    for r in mem.seed.requirements:
        if r.secured_at and slug(r.secured_at) == aid:
            per_service[r.service_id] = per_service.get(r.service_id, 0) + 1
    return per_service


def test_agency_services_match_the_in_memory_graph_for_every_agency(mem, graph):
    names = _agency_names(mem)
    assert len(names) > 10
    for aid, name in names.items():
        rows = ask(graph, "where_to_secure", "agency_services", ("agency", aid))
        assert [(x["s.id"], x["n"], x["a.name"]) for x in rows] == [
            (sid, n, name) for sid, n in sorted(_services_needing(mem, aid).items())
        ], aid


def test_agency_services_match_the_id_and_not_the_name(mem, graph):
    names = _agency_names(mem)
    differing = [(aid, name) for aid, name in names.items() if aid != name]
    assert differing
    for aid, name in differing:
        # the id finds the agency; the display name is not an id and finds nothing
        assert ask(graph, "where_to_secure", "agency_services", ("agency", aid))
        assert run_cypher(graph, AGENCY_QUERY.cypher, {"aid": name}) == [], name


def test_agency_ids_that_contain_each_other_do_not_bleed_into_each_other(mem, graph):
    """ "city-health-office" is inside "city-health-office-cho": an id match must not widen."""
    names = _agency_names(mem)
    nested = [(a, b) for a in names for b in names if a != b and a in b]
    assert nested, "the seed has no agency id inside another: this test would prove nothing"
    for short, long in nested:
        rows = ask(graph, "where_to_secure", "agency_services", ("agency", short))
        assert {x["a.name"] for x in rows} == {names[short]}, (short, long)
