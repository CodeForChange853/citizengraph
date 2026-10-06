"""Suspect records are held back from the default load (graph/load.py, graph/holdback.py).

The markers are seed data: ``Requirement.suspect`` (+ ``suspect_reason``) and ``Service.held_back``.
By default the loader's plan leaves the marked records out, with their child requirements and
every relationship that touches them, and marks the service ``info_status = "pending_lgu"``.
``include_suspect_records=True`` writes the full seed and marks nobody.

Behaviour is tested on the invented fixture (``graph_fixtures.minimal_seed_raw``) so it does not
depend on real ids; the real seed is used for what must hold for the data as it is today. Nothing
here needs Neo4j: a recording fake stands in for the driver.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from graph_fixtures import minimal_seed_raw
from pydantic import ValidationError
from test_graph_schema_alignment import BOOKKEEPING

from citizengraph.core1.prompt import full_schema_slice, render_schema, schema_slice
from citizengraph.core1.templates import CORE1_INTENTS, TEMPLATES, build_templates
from citizengraph.graph.holdback import HoldBack, hold_back
from citizengraph.graph.ids import slug
from citizengraph.graph.loader import DEFAULT_SEED_DIR, load_seed, parse_seed, validate_seed
from citizengraph.graph.models import HeldBack, Requirement, Seed, Service
from citizengraph.guardrail.schema import OFFICIAL_SCHEMA, Schema
from citizengraph.guardrail.validator import validate_cypher

ROOT = Path(__file__).resolve().parents[1]

# The real seed as marked today (the tests below also derive these from the markers).
HELD_REQUIREMENTS = {
    "death_registration_timely-R01",
    "death_registration_timely-R02",
    "business_permit-R13",
    "business_permit-R14",
    "birth_registration_timely-R01",
}
PENDING = {
    "business_permit",
    "birth_registration_timely",
    "death_registration_timely",
    "cho_cadaver_transfer_permit",
}
WHO_HELD = "cho_cadaver_transfer_permit"
MARRIAGE_TEXTS = (
    "Affidavit of Delayed Registration of Marriage certificate",
    "Marriage Certificate duly signed by the solemnizing officer",
)
MARKER_NAMES = {"suspect", "suspect_reason", "held_back", "reason"}

FLAGS = [(links, suspects) for links in (False, True) for suspects in (False, True)]
FLAG_IDS = [f"links={int(links)},suspects={int(suspects)}" for links, suspects in FLAGS]

_ENDPOINT = re.compile(r"MATCH \((a|b):(\w+) \{id: row\.(a|b)\}\)")


def _import_loader():
    spec = importlib.util.spec_from_file_location(
        "citizengraph_admin_load_holdback", ROOT / "graph/load.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


loadmod = _import_loader()


@pytest.fixture(scope="module")
def seed() -> Seed:
    return load_seed(DEFAULT_SEED_DIR)


@pytest.fixture(scope="module")
def plans(seed):
    """All four plans of the real seed, keyed by (suggested links, suspect records)."""
    return {
        (links, suspects): loadmod.build_plan(
            seed, include_unreviewed_links=links, include_suspect_records=suspects
        )
        for links, suspects in FLAGS
    }


@pytest.fixture(scope="module")
def default(plans):
    return plans[(False, False)]


@pytest.fixture(scope="module")
def full(plans):
    return plans[(False, True)]


def by_name(plan) -> dict[str, Any]:
    return {b.name: b for b in plan}


def frozen(plan) -> list[tuple[str, str, list[dict[str, Any]]]]:
    return [(b.name, b.cypher, b.rows) for b in plan]


def node_ids(plan, label: str) -> set[str]:
    return {row["id"] for row in by_name(plan)[f"node:{label}"].rows}


def service_props(plan) -> dict[str, dict[str, Any]]:
    return {row["id"]: row["props"] for row in by_name(plan)["node:Service"].rows}


def endpoints(batch) -> tuple[str, str]:
    """(source label, target label) of a relationship batch, read from its Cypher."""
    found = {
        var: label for var, label, row_key in _ENDPOINT.findall(batch.cypher) if var == row_key
    }
    assert set(found) == {"a", "b"}, batch.cypher
    return found["a"], found["b"]


def strings(value: Any) -> Iterator[str]:
    """Every string anywhere inside plan rows (keys and values)."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from strings(k)
            yield from strings(v)
    elif isinstance(value, list | tuple):
        for v in value:
            yield from strings(v)


def plan_strings(plan) -> list[str]:
    return list(strings([b.rows for b in plan]))


def ids_anywhere(plan) -> set[str]:
    """Every node id and relationship endpoint id of a plan."""
    found: set[str] = set()
    for b in plan:
        for row in b.rows:
            found |= {row["id"]} if b.name.startswith("node:") else {row["a"], row["b"]}
    return found


def minus_removed(plan, removed: dict[str, set[str]]) -> list[tuple[str, str, list[dict]]]:
    """The plan without the given node ids (label -> ids) and without any row touching them."""
    out = []
    for b in plan:
        if b.name.startswith("node:"):
            gone = removed.get(b.name.split(":")[1], set())
            rows = [row for row in b.rows if row["id"] not in gone]
        else:
            src, dst = endpoints(b)
            rows = [
                row
                for row in b.rows
                if row["a"] not in removed.get(src, set())
                and row["b"] not in removed.get(dst, set())
            ]
        out.append((b.name, b.cypher, rows))
    return out


def orphaned_agencies(plan, held_requirements: set[str]) -> set[str]:
    """Agency ids of a full plan that only the given requirements are secured at."""
    still_named = {
        row["b"]
        for row in by_name(plan)["rel:SECURED_AT"].rows
        if row["a"] not in held_requirements
    }
    return node_ids(plan, "Agency") - still_named


# ---- the invented fixture ------------------------------------------------------------------


def family_raw() -> dict[str, list[dict[str, Any]]]:
    """The minimal seed plus a grandchild, a `who may avail` text and two kinds of link.

    svc-R02 (group) > svc-R03 (group, secured at "Other Agency") > svc-R06. link-01 names
    svc-R01 and its agency ("Some Agency", which svc-R05 also names); link-02 names only the
    agency "Other Agency", which svc-R03 alone is secured at.
    """
    raw = minimal_seed_raw()
    raw["services"][0]["who_may_avail"] = "Anyone with a test"
    child = raw["requirements"][2]
    assert child["id"] == "svc-R03"
    child["group"] = True
    raw["requirements"].append(
        {
            **child,
            "id": "svc-R06",
            "text": "Grandchild document",
            "group": False,
            "parent_id": "svc-R03",
            "secured_at": None,
            "source_row": 25,
        }
    )
    raw["links"][0]["requirement_id"] = "svc-R01"
    raw["links"].append(
        {**raw["links"][0], "id": "link-02", "requirement_id": None, "agency": "Other Agency"}
    )
    return raw


def mark(raw: dict[str, list[dict[str, Any]]], requirement_id: str, reason: str) -> None:
    rec = next(r for r in raw["requirements"] if r["id"] == requirement_id)
    rec["suspect"] = True
    rec["suspect_reason"] = reason


def held_ids(held: HoldBack, kind: str) -> set[str | None]:
    return {i.record_id for i in held.items if i.kind == kind}


# ---- 1. models -----------------------------------------------------------------------------


def service_raw() -> dict[str, Any]:
    """The fixture service, with a `who may avail` text so that it can be held back."""
    return {**minimal_seed_raw()["services"][0], "who_may_avail": "Anyone with a test"}


class TestMarkerModels:
    def test_defaults_are_unmarked(self):
        raw = minimal_seed_raw()
        requirement = Requirement.model_validate(raw["requirements"][0])
        assert requirement.suspect is False
        assert requirement.suspect_reason is None
        assert Service.model_validate(raw["services"][0]).held_back == []

    def test_a_suspect_requirement_parses_with_a_reason(self):
        rec = {**minimal_seed_raw()["requirements"][0], "suspect": True, "suspect_reason": "why"}
        requirement = Requirement.model_validate(rec)
        assert requirement.suspect is True
        assert requirement.suspect_reason == "why"

    @pytest.mark.parametrize("reason", [None, "", "   "])
    def test_suspect_needs_a_reason(self, reason):
        rec = {**minimal_seed_raw()["requirements"][0], "suspect": True, "suspect_reason": reason}
        with pytest.raises(ValidationError, match="suspect_reason"):
            Requirement.model_validate(rec)

    def test_suspect_without_the_reason_key_is_rejected(self):
        rec = {**minimal_seed_raw()["requirements"][0], "suspect": True}
        with pytest.raises(ValidationError, match="suspect_reason"):
            Requirement.model_validate(rec)

    @pytest.mark.parametrize("extra", [{}, {"suspect": False}])
    def test_a_reason_without_suspect_is_rejected(self, extra):
        rec = {**minimal_seed_raw()["requirements"][0], **extra, "suspect_reason": "why"}
        with pytest.raises(ValidationError, match="only for a suspect requirement"):
            Requirement.model_validate(rec)

    @pytest.mark.parametrize("value", ["yes", "true", 1, None])
    def test_suspect_must_be_a_real_boolean(self, value):
        rec = {**minimal_seed_raw()["requirements"][0], "suspect": value, "suspect_reason": "why"}
        with pytest.raises(ValidationError):
            Requirement.model_validate(rec)

    @pytest.mark.parametrize("field", ["requirements", "who_may_avail"])
    def test_held_back_accepts_the_two_fields(self, field):
        rec = {**service_raw(), "held_back": [{"field": field, "reason": "x"}]}
        assert Service.model_validate(rec).held_back == [HeldBack(field=field, reason="x")]

    @pytest.mark.parametrize(
        "entry",
        [
            {"field": "fees", "reason": "x"},
            {"field": "requirement", "reason": "x"},
            {"field": "requirements", "reason": ""},
            {"field": "requirements", "reason": "   "},
            {"field": "requirements"},
            {"reason": "x"},
            {"field": "requirements", "reason": "x", "surprise": 1},
        ],
    )
    def test_held_back_rejects_bad_entries(self, entry):
        rec = {**service_raw(), "held_back": [entry]}
        with pytest.raises(ValidationError):
            Service.model_validate(rec)

    def test_held_back_rejects_a_field_listed_twice(self):
        entries = [
            {"field": "requirements", "reason": "a"},
            {"field": "requirements", "reason": "b"},
        ]
        rec = {**service_raw(), "held_back": entries}
        with pytest.raises(ValidationError, match="more than once"):
            Service.model_validate(rec)

    def test_who_may_avail_cannot_be_held_back_when_there_is_no_text(self):
        entries = [{"field": "who_may_avail", "reason": "x"}]
        rec = {**service_raw(), "who_may_avail": None, "held_back": entries}
        with pytest.raises(ValidationError, match="who_may_avail"):
            Service.model_validate(rec)

    def test_both_fields_may_be_held_back_together(self):
        entries = [
            {"field": "requirements", "reason": "a"},
            {"field": "who_may_avail", "reason": "b"},
        ]
        rec = {**service_raw(), "held_back": entries}
        assert len(Service.model_validate(rec).held_back) == 2


# ---- 2 and 3. the default plan leaves the suspect requirements out -------------------------


class TestDefaultPlanExcludesSuspects:
    def test_the_real_markers_are_the_ones_these_tests_name(self, seed):
        marked = {r.id for r in seed.requirements if r.suspect}
        checklist = {
            s.id for s in seed.services if any(h.field == "requirements" for h in s.held_back)
        }
        whole = {r.id for r in seed.requirements if r.service_id in checklist}
        assert marked | whole == HELD_REQUIREMENTS
        assert hold_back(seed).requirement_ids == HELD_REQUIREMENTS

    @pytest.mark.parametrize("links", [False, True])
    def test_held_back_requirements_are_in_no_node_and_no_relationship(self, plans, links):
        assert not HELD_REQUIREMENTS & ids_anywhere(plans[(links, False)])

    @pytest.mark.parametrize("links", [False, True])
    def test_the_flag_includes_them_all(self, plans, links):
        plan = plans[(links, True)]
        assert HELD_REQUIREMENTS <= node_ids(plan, "Requirement")
        assert HELD_REQUIREMENTS <= {row["b"] for row in by_name(plan)["rel:REQUIRES"].rows}

    def test_only_those_requirements_are_missing(self, seed, default):
        assert (
            node_ids(default, "Requirement")
            == {r.id for r in seed.requirements} - HELD_REQUIREMENTS
        )
        assert len(by_name(default)["node:Requirement"].rows) == len(seed.requirements) - 5

    def test_no_marriage_document_is_listed_for_death_registration(self, default, full):
        service = "death_registration_timely"
        rows = by_name(default)["node:Requirement"].rows
        assert [row["id"] for row in rows if row["id"].startswith(service)] == []
        assert [row for row in by_name(default)["rel:REQUIRES"].rows if row["a"] == service] == []
        # the texts may belong to a marriage service, never to anything reachable from this one
        required = {
            row["b"] for row in by_name(default)["rel:REQUIRES"].rows if row["a"] == service
        }
        for row in rows:
            if row["props"]["text"] in MARRIAGE_TEXTS:
                assert not row["id"].startswith(service)
                assert row["id"] not in required
        # not vacuous: the full seed does list both texts under this service
        listed = {
            row["props"]["text"]
            for row in by_name(full)["node:Requirement"].rows
            if row["id"].startswith(service)
        }
        assert listed == set(MARRIAGE_TEXTS)

    def test_steps_and_fees_are_never_held_back(self, seed, default, full):
        for name in (
            "node:Step",
            "node:Fee",
            "rel:HAS_STEP",
            "rel:NEXT",
            "rel:HAS_FEE",
            "rel:CHARGES",
        ):
            assert by_name(default)[name].rows == by_name(full)[name].rows, name
        assert len(by_name(default)["node:Step"].rows) == len(seed.steps)
        assert node_ids(default, "Service") == {s.id for s in seed.services}


# ---- 4 and 5. pending_lgu and who_may_avail ------------------------------------------------


class TestPendingStatus:
    def test_pending_is_exactly_the_services_with_a_held_back_item(self, seed, default):
        marked = {s.id for s in seed.services if s.held_back}
        marked |= {r.service_id for r in seed.requirements if r.suspect}
        with_status = {
            sid for sid, props in service_props(default).items() if "info_status" in props
        }
        assert with_status == hold_back(seed).pending_services == marked == PENDING

    @pytest.mark.parametrize("links", [False, True])
    def test_the_only_value_is_pending_lgu(self, plans, links):
        values = [
            props["info_status"]
            for props in service_props(plans[(links, False)]).values()
            if "info_status" in props
        ]
        assert values == ["pending_lgu"] * len(PENDING)
        assert loadmod.PENDING_LGU == "pending_lgu"

    @pytest.mark.parametrize("links", [False, True])
    def test_with_the_flag_no_service_has_the_property(self, plans, links):
        assert all(
            "info_status" not in props for props in service_props(plans[(links, True)]).values()
        )

    def test_no_other_label_carries_info_status(self, plans):
        for plan in plans.values():
            for b in plan:
                if b.name.startswith("node:") and b.name != "node:Service":
                    assert all("info_status" not in row["props"] for row in b.rows), b.name


class TestHeldBackWhoMayAvail:
    def test_it_is_absent_by_default_and_present_with_the_flag(self, seed, default, full):
        text = next(s.who_may_avail for s in seed.services if s.id == WHO_HELD)
        assert text
        assert "who_may_avail" not in service_props(default)[WHO_HELD]
        assert service_props(full)[WHO_HELD]["who_may_avail"] == text

    def test_other_services_keep_theirs(self, default, full):
        mine, theirs = service_props(default), service_props(full)
        others = [sid for sid in theirs if sid != WHO_HELD]
        assert len(others) == 25
        assert sum("who_may_avail" in theirs[sid] for sid in others) > 15
        for sid in others:
            assert mine[sid].get("who_may_avail") == theirs[sid].get("who_may_avail"), sid


# ---- 6. nothing dangles ---------------------------------------------------------------------


class TestNoDanglingEndpoints:
    @pytest.mark.parametrize("flags", FLAGS, ids=FLAG_IDS)
    def test_every_relationship_endpoint_is_a_node_of_the_plan(self, plans, flags):
        plan = plans[flags]
        checked = 0
        for b in plan:
            if not b.name.startswith("rel:"):
                continue
            src, dst = endpoints(b)
            sources, targets = node_ids(plan, src), node_ids(plan, dst)
            for row in b.rows:
                assert row["a"] in sources, (b.name, row)
                assert row["b"] in targets, (b.name, row)
                checked += 1
        assert checked > 400

    @pytest.mark.parametrize("flags", FLAGS, ids=FLAG_IDS)
    def test_every_agency_is_named_by_a_requirement_that_is_loaded(self, plans, flags):
        plan = plans[flags]
        named = {row["b"] for row in by_name(plan)["rel:SECURED_AT"].rows}
        assert node_ids(plan, "Agency") == named

    def test_an_agency_only_a_held_back_requirement_names_is_not_loaded(self, seed, default, full):
        cda = "Cooperative Development Authority (CDA)"
        assert [r.id for r in seed.requirements if r.secured_at == cda] == ["business_permit-R14"]
        assert slug(cda) in node_ids(full, "Agency")
        assert slug(cda) not in node_ids(default, "Agency")
        assert node_ids(full, "Agency") - node_ids(default, "Agency") == {slug(cda)}
        assert orphaned_agencies(full, HELD_REQUIREMENTS) == {slug(cda)}

    @pytest.mark.parametrize("flags", FLAGS, ids=FLAG_IDS)
    def test_every_stored_property_is_specified_or_bookkeeping(self, plans, flags):
        stored: set[str] = set()
        for b in plans[flags]:
            if b.name.startswith("node:"):
                for row in b.rows:
                    stored |= set(row["props"])
        assert stored - OFFICIAL_SCHEMA.properties <= BOOKKEEPING
        assert ("info_status" in stored) is (not flags[1])


# ---- 7. children, whole checklists and links (invented data) -------------------------------


class TestHoldBackBehaviour:
    def test_an_unmarked_seed_is_left_alone(self):
        seed = parse_seed(family_raw())
        held = hold_back(seed)
        assert held.items == ()
        assert held.pending_services == frozenset()
        assert held.requirement_ids == frozenset()
        assert held.by_service() == {}
        assert held.seed == seed
        assert frozen(loadmod.build_plan(seed)) == frozen(
            loadmod.build_plan(seed, include_suspect_records=True)
        )
        assert "info_status" not in service_props(loadmod.build_plan(seed))["svc"]

    def test_a_suspect_parent_takes_its_children_and_grandchildren(self):
        raw = family_raw()
        mark(raw, "svc-R02", "the heading is unclear")
        seed = parse_seed(raw)
        assert [r.id for r in seed.requirements if r.suspect] == ["svc-R02"]
        held = hold_back(seed)
        assert held.requirement_ids == {"svc-R02", "svc-R03", "svc-R06"}
        assert [r.id for r in held.seed.requirements] == ["svc-R01", "svc-R04", "svc-R05"]
        assert held.pending_services == {"svc"}
        reasons = {i.record_id: i.reason for i in held.items if i.kind == "requirement"}
        assert reasons["svc-R02"] == "the heading is unclear"
        assert "svc-R02" in reasons["svc-R03"]
        assert "svc-R03" in reasons["svc-R06"]

    def test_the_plan_has_no_trace_of_the_family(self):
        raw = family_raw()
        mark(raw, "svc-R02", "the heading is unclear")
        seed = parse_seed(raw)
        family = {"svc-R02", "svc-R03", "svc-R06"}
        for links in (False, True):
            plan = loadmod.build_plan(seed, include_unreviewed_links=links)
            assert not family & ids_anywhere(plan)
            assert node_ids(plan, "Requirement") == {"svc-R01", "svc-R04", "svc-R05"}
            assert node_ids(plan, "Agency") == {slug("Some Agency")}
            assert by_name(plan)["rel:PART_OF"].rows == []
            assert service_props(plan)["svc"]["info_status"] == "pending_lgu"
            full = loadmod.build_plan(
                seed, include_unreviewed_links=links, include_suspect_records=True
            )
            assert family <= node_ids(full, "Requirement")
            assert len(by_name(full)["rel:PART_OF"].rows) == 2
            assert "info_status" not in service_props(full)["svc"]

    def test_a_suspect_child_takes_its_whole_group_and_nothing_else(self):
        """A group is shown whole or not at all: its min_required would count a missing part."""
        raw = family_raw()
        mark(raw, "svc-R03", "wrong document")
        seed = parse_seed(raw)
        held = hold_back(seed)
        tree = {"svc-R02"}
        while True:
            more = {r.id for r in seed.requirements if r.parent_id in tree} - tree
            if not more:
                break
            tree |= more
        assert {"svc-R02", "svc-R03", "svc-R06"} <= tree
        assert held.requirement_ids == tree
        assert "svc-R01" in {r.id for r in held.seed.requirements}
        assert validate_seed(held.seed) == []

    def test_a_group_never_keeps_min_required_over_missing_parts(self):
        raw = family_raw()
        group = next(r for r in raw["requirements"] if r["id"] == "svc-R02")
        kids = [r for r in raw["requirements"] if r["parent_id"] == "svc-R02"]
        group["min_required"] = len(kids)
        mark(raw, kids[-1]["id"], "wrong document")
        seed = parse_seed(raw)
        held = hold_back(seed)
        assert validate_seed(held.seed) == []
        kept = {r.id for r in held.seed.requirements}
        assert "svc-R02" not in kept and not kept & {k["id"] for k in kids}
        assert held.pending_services == {"svc"}

    def test_a_held_back_checklist_loses_every_requirement(self):
        raw = family_raw()
        raw["services"][0]["held_back"] = [{"field": "requirements", "reason": "incomplete list"}]
        seed = parse_seed(raw)
        held = hold_back(seed)
        assert held.seed.requirements == []
        assert held.requirement_ids == {r.id for r in seed.requirements}
        assert held.pending_services == {"svc"}
        assert [(i.kind, i.reason) for i in held.items if i.kind == "requirements"] == [
            ("requirements", "incomplete list")
        ]
        assert held.seed.services[0].who_may_avail == "Anyone with a test"
        plan = loadmod.build_plan(seed, include_unreviewed_links=True)
        for name in ("node:Requirement", "node:Agency", "rel:REQUIRES", "rel:SECURED_AT",
                     "rel:PART_OF", "rel:APPLIES_WHEN:Requirement", "rel:IS_OFFICE"):  # fmt: skip
            assert by_name(plan)[name].rows == [], name
        assert len(by_name(plan)["node:Step"].rows) == 3
        assert len(by_name(plan)["node:Fee"].rows) == 4
        assert service_props(plan)["svc"]["info_status"] == "pending_lgu"

    def test_a_held_back_who_may_avail_becomes_null_and_nothing_else_changes(self):
        raw = family_raw()
        raw["services"][0]["held_back"] = [{"field": "who_may_avail", "reason": "copied text"}]
        seed = parse_seed(raw)
        held = hold_back(seed)
        assert held.seed.services[0].who_may_avail is None
        assert held.seed.requirements == seed.requirements
        assert held.seed.links == seed.links
        assert held.requirement_ids == frozenset()
        assert held.pending_services == {"svc"}
        props = service_props(loadmod.build_plan(seed))["svc"]
        assert "who_may_avail" not in props
        assert props["info_status"] == "pending_lgu"
        with_flag = service_props(loadmod.build_plan(seed, include_suspect_records=True))["svc"]
        assert with_flag["who_may_avail"] == "Anyone with a test"

    def test_a_link_naming_a_held_back_requirement_is_dropped(self):
        raw = family_raw()
        mark(raw, "svc-R01", "wrong office")
        seed = parse_seed(raw)
        held = hold_back(seed)
        assert [x.id for x in held.seed.links] == ["link-02"]
        assert held_ids(held, "link") == {"link-01"}
        # svc-R05 still names the agency, so the agency itself stays
        plan = loadmod.build_plan(seed, include_unreviewed_links=True)
        assert slug("Some Agency") in node_ids(plan, "Agency")
        assert by_name(plan)["rel:IS_OFFICE"].rows == [{"a": slug("Other Agency"), "b": "o1"}]
        full = loadmod.build_plan(seed, include_unreviewed_links=True, include_suspect_records=True)
        assert len(by_name(full)["rel:IS_OFFICE"].rows) == 2

    def test_a_link_to_an_agency_only_held_back_requirements_name_is_dropped(self):
        raw = family_raw()
        mark(raw, "svc-R03", "wrong document")
        seed = parse_seed(raw)
        held = hold_back(seed)
        assert [x.id for x in held.seed.links] == ["link-01"]
        assert held_ids(held, "link") == {"link-02"}
        plan = loadmod.build_plan(seed, include_unreviewed_links=True)
        assert slug("Other Agency") not in node_ids(plan, "Agency")
        assert by_name(plan)["rel:IS_OFFICE"].rows == [{"a": slug("Some Agency"), "b": "o1"}]

    def test_a_reviewed_link_is_held_back_with_its_requirement(self):
        raw = family_raw()
        mark(raw, "svc-R01", "wrong office")
        for link in raw["links"]:
            link["review_status"] = "reviewed"
        plan = loadmod.build_plan(parse_seed(raw))  # reviewed links are written by default
        assert by_name(plan)["rel:IS_OFFICE"].rows == [{"a": slug("Other Agency"), "b": "o1"}]

    def test_what_is_left_is_a_valid_seed(self, seed):
        assert validate_seed(hold_back(seed).seed) == []
        raw = family_raw()
        mark(raw, "svc-R02", "the heading is unclear")
        assert validate_seed(hold_back(parse_seed(raw)).seed) == []

    def test_hold_back_does_not_change_its_input(self, seed):
        raw = family_raw()
        mark(raw, "svc-R02", "the heading is unclear")
        raw["services"][0]["held_back"] = [{"field": "who_may_avail", "reason": "copied text"}]
        for subject in (seed, parse_seed(raw)):
            before = subject.model_dump()
            held = hold_back(subject)
            loadmod.build_plan(subject)
            assert subject.model_dump() == before
            assert held.seed is not subject
            assert held.seed.model_dump() != before

    def test_real_seed_items_say_what_and_why(self, seed):
        held = hold_back(seed)
        assert list(held.by_service()) == [s.id for s in seed.services if s.id in PENDING]
        assert all(item.reason.strip() for item in held.items)
        assert held_ids(held, "link") == set()
        assert {i.service_id for i in held.items if i.kind == "who_may_avail"} == {WHO_HELD}
        assert {i.service_id for i in held.items if i.kind == "requirements"} == {
            "birth_registration_timely"
        }


# ---- 8. determinism, and the default plan is the full plan minus the held-back rows --------


class TestDeterminism:
    @pytest.mark.parametrize("flags", FLAGS, ids=FLAG_IDS)
    def test_building_twice_gives_the_same_plan(self, seed, plans, flags):
        links, suspects = flags
        again = loadmod.build_plan(
            seed, include_unreviewed_links=links, include_suspect_records=suspects
        )
        assert frozen(again) == frozen(plans[flags])

    def test_a_freshly_loaded_seed_gives_the_same_plan(self, default):
        assert frozen(loadmod.build_plan(load_seed(DEFAULT_SEED_DIR))) == frozen(default)

    @pytest.mark.parametrize("included", [False, True])
    def test_the_held_back_report_is_stable(self, seed, included):
        first = loadmod.held_back_lines(hold_back(seed), included)
        assert first == loadmod.held_back_lines(hold_back(load_seed(DEFAULT_SEED_DIR)), included)
        assert first and all(isinstance(line, str) and line.strip() for line in first)

    @pytest.mark.parametrize("links", [False, True])
    def test_same_statements_in_the_same_order(self, plans, links):
        held, whole = plans[(links, False)], plans[(links, True)]
        assert [(b.name, b.cypher) for b in held] == [(b.name, b.cypher) for b in whole]

    @pytest.mark.parametrize("links", [False, True])
    def test_default_is_the_full_plan_minus_the_held_back_rows(self, plans, links):
        held, whole = plans[(links, False)], plans[(links, True)]
        removed = {
            "Requirement": set(HELD_REQUIREMENTS),
            "Agency": orphaned_agencies(whole, HELD_REQUIREMENTS),
        }
        expected = minus_removed(whole, removed)
        for got, want in zip(frozen(held), expected, strict=True):
            if got[0] == "node:Agency":
                # Agency rows are derived in the order requirements first name them, so holding
                # back the first requirement that names an agency moves that agency's row. The
                # rows themselves are the same; only this batch is compared without its order.
                assert sorted(got[2], key=str) == sorted(want[2], key=str)
            elif got[0] != "node:Service":
                assert got == want, got[0]

    @pytest.mark.parametrize("links", [False, True])
    def test_service_rows_differ_only_in_the_two_held_back_properties(self, plans, links):
        held = by_name(plans[(links, False)])["node:Service"].rows
        whole = by_name(plans[(links, True)])["node:Service"].rows
        assert [row["id"] for row in held] == [row["id"] for row in whole]
        for mine, theirs in zip(held, whole, strict=True):
            sid = mine["id"]
            want = dict(theirs["props"])
            if sid == WHO_HELD:
                del want["who_may_avail"]
            if sid in PENDING:
                want["info_status"] = "pending_lgu"
            assert mine["props"] == want, sid
            assert [k for k in mine["props"] if k != "info_status"] == [
                k for k in want if k != "info_status"
            ]


# ---- 9. cross-office links are still suggestions -------------------------------------------


class TestCrossOfficeLinksStayHeldBack:
    def test_all_nine_links_are_still_unreviewed(self, seed):
        assert len(seed.links) == 9
        assert {x.review_status for x in seed.links} == {"needs_review"}

    @pytest.mark.parametrize("suspects", [False, True])
    def test_no_link_is_written_by_default(self, plans, suspects):
        plan = by_name(plans[(False, suspects)])
        assert plan["rel:SATISFIED_BY"].rows == []
        assert plan["rel:IS_OFFICE"].rows == []

    @pytest.mark.parametrize("suspects", [False, True])
    def test_all_nine_can_be_included(self, seed, plans, suspects):
        plan = by_name(plans[(True, suspects)])
        assert len(plan["rel:SATISFIED_BY"].rows) == 3
        assert len(plan["rel:IS_OFFICE"].rows) == 6
        assert {(row["a"], row["b"]) for row in plan["rel:SATISFIED_BY"].rows} == {
            (x.requirement_id, x.service_id)
            for x in seed.links
            if x.kind == "requirement_satisfied_by"
        }
        assert {(row["a"], row["b"]) for row in plan["rel:IS_OFFICE"].rows} == {
            (slug(x.agency), x.office_id) for x in seed.links if x.kind == "agency_is_office"
        }

    def test_holding_back_suspects_drops_no_link(self, seed):
        assert hold_back(seed).seed.links == seed.links


# ---- 10. the gateway's withheld list --------------------------------------------------------


def test_every_withheld_service_is_pending_in_the_graph(seed):
    cfg = yaml.safe_load((ROOT / "config" / "limits.yaml").read_text(encoding="utf-8"))
    withheld = cfg["gateway"]["withheld_services"]
    assert isinstance(withheld, list)
    assert set(withheld) <= hold_back(seed).pending_services
    # One direction only. A pending service does not have to be withheld: the gateway may still
    # answer its fees or steps while the graph says its checklist is being confirmed.


# ---- 11. which records are suspect is data, never code -------------------------------------


@pytest.mark.parametrize("path", ["graph/load.py", "src/citizengraph/graph/holdback.py"])
def test_loader_code_names_no_seed_record(seed, path):
    text = (ROOT / path).read_text(encoding="utf-8")
    ids = [s.id for s in seed.services] + [r.id for r in seed.requirements]
    ids += [s.charter_ref for s in seed.services]
    assert len(ids) == 26 + 74 + 26
    assert [i for i in ids if i in text] == []


# ---- 12. the markers and their reasons are not stored --------------------------------------


class TestMarkersAreNotStored:
    @pytest.mark.parametrize("flags", FLAGS, ids=FLAG_IDS)
    def test_no_row_has_a_marker_property(self, plans, flags):
        for b in plans[flags]:
            for row in b.rows:
                assert not MARKER_NAMES & set(row), b.name
                assert not MARKER_NAMES & set(row.get("props", {})), b.name

    @pytest.mark.parametrize("flags", FLAGS, ids=FLAG_IDS)
    def test_no_reason_text_is_stored(self, seed, plans, flags):
        reasons = {r.suspect_reason for r in seed.requirements if r.suspect_reason}
        reasons |= {h.reason for s in seed.services for h in s.held_back}
        reasons |= {item.reason for item in hold_back(seed).items}
        assert len(reasons) >= 6
        stored = plan_strings(plans[flags])
        assert len(stored) > 1000
        for reason in reasons:
            assert [text for text in stored if reason in text] == [], reason

    def test_the_fixture_reasons_are_not_stored_either(self):
        raw = family_raw()
        mark(raw, "svc-R02", "REASON-ONE unclear heading")
        raw["services"][0]["held_back"] = [
            {"field": "who_may_avail", "reason": "REASON-TWO copied"}
        ]
        seed = parse_seed(raw)
        for links, suspects in FLAGS:
            plan = loadmod.build_plan(
                seed, include_unreviewed_links=links, include_suspect_records=suspects
            )
            assert [text for text in plan_strings(plan) if "REASON-" in text] == []
            assert not MARKER_NAMES & set(plan_strings(plan))


# ---- 13. write_seed and the command line ----------------------------------------------------


class FakeTx:
    def __init__(self, log):
        self.log = log

    def run(self, query, parameters=None, **kwargs):
        self.log.append(("run", query, {**(parameters or {}), **kwargs}))


class FakeSession:
    def __init__(self, log):
        self.log = log

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute_write(self, fn, *args, **kwargs):
        return fn(FakeTx(self.log), *args, **kwargs)


class FakeDriver:
    """Records every statement and its rows; no database."""

    def __init__(self):
        self.log: list[tuple] = []

    def session(self, **kwargs):
        return FakeSession(self.log)

    def written(self) -> list[tuple[str, list[dict[str, Any]]]]:
        return [(e[1], e[2]["rows"]) for e in self.log if e[0] == "run" and "rows" in e[2]]


def written_ids(driver: FakeDriver) -> set[str]:
    found: set[str] = set()
    for _, rows in driver.written():
        for row in rows:
            found |= {v for k, v in row.items() if k in ("id", "a", "b")}
    return found


def written_service_props(driver: FakeDriver) -> dict[str, dict[str, Any]]:
    statement = by_name(loadmod.build_plan(parse_seed(minimal_seed_raw())))["node:Service"].cypher
    return {
        row["id"]: row["props"]
        for cypher, rows in driver.written()
        if cypher == statement
        for row in rows
    }


class TestWriteSeed:
    def test_suspect_records_are_not_written_by_default(self, seed, default):
        driver = FakeDriver()
        report = loadmod.write_seed(driver, seed, batch_size=7)
        assert frozen(report.plan) == frozen(default)
        assert not HELD_REQUIREMENTS & written_ids(driver)
        assert report.counts["node:Requirement"] == len(seed.requirements) - 5
        assert report.counts["rel:REQUIRES"] == len(seed.requirements) - 5
        props = written_service_props(driver)
        assert len(props) == 26
        assert {sid for sid, p in props.items() if p.get("info_status") == "pending_lgu"} == PENDING
        assert "who_may_avail" not in props[WHO_HELD]

    def test_the_switch_is_passed_through(self, seed, full):
        driver = FakeDriver()
        report = loadmod.write_seed(driver, seed, batch_size=7, include_suspect_records=True)
        assert frozen(report.plan) == frozen(full)
        assert HELD_REQUIREMENTS <= written_ids(driver)
        assert report.counts["node:Requirement"] == len(seed.requirements)
        props = written_service_props(driver)
        assert all("info_status" not in p for p in props.values())
        assert props[WHO_HELD]["who_may_avail"]

    @pytest.mark.parametrize("flags", FLAGS, ids=FLAG_IDS)
    def test_both_switches_together(self, seed, plans, flags):
        links, suspects = flags
        driver = FakeDriver()
        report = loadmod.write_seed(
            driver, seed, include_unreviewed_links=links, include_suspect_records=suspects
        )
        assert frozen(report.plan) == frozen(plans[flags])
        assert report.counts["rel:SATISFIED_BY"] == (3 if links else 0)
        assert report.counts["rel:IS_OFFICE"] == (6 if links else 0)
        assert sum(len(rows) for _, rows in driver.written()) == sum(
            len(b.rows) for b in plans[flags]
        )


def _base_env() -> dict[str, str]:
    keep = ("PATH", "PYTHON", "HOME", "VIRTUAL", "SYSTEMROOT")
    return {k: v for k, v in os.environ.items() if k.upper().startswith(keep)}


class TestCli:
    def run(self, *args):
        return subprocess.run(
            [sys.executable, str(ROOT / "graph/load.py"), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=_base_env(),
            cwd=ROOT,
            timeout=60,
            check=False,
        )

    def test_dry_run_lists_what_is_held_back_and_why(self, seed):
        done = self.run("--dry-run")
        assert done.returncode == 0, done.stderr
        out = done.stdout
        assert "5 suspect requirements held back in 4 services, 4 marked pending_lgu" in out
        assert "nothing written" in out
        head, _, block = out.partition("suspect records, held back:\n")
        assert head and block
        lines = block.splitlines()
        assert lines == loadmod.held_back_lines(hold_back(seed))
        headers = [line for line in lines if not line.startswith("    ")]
        assert [line.split()[0] for line in headers] == [
            s.id for s in seed.services if s.id in PENDING
        ]
        assert all(line.endswith("info_status = pending_lgu") for line in headers)
        for rid in HELD_REQUIREMENTS:
            assert f"requirement {rid}: " in block
        assert "whole checklist: " in block
        assert "who_may_avail (written as null): " in block
        assert "NOT held back" not in out

    def test_dry_run_with_the_flag_says_they_are_included(self, seed):
        done = self.run("--dry-run", "--include-suspect-records")
        assert done.returncode == 0, done.stderr
        out = done.stdout
        assert "suspect records in 4 services included (--include-suspect-records)" in out
        head, _, block = out.partition("suspect records, NOT held back (included):\n")
        assert head and block
        lines = block.splitlines()
        assert lines == loadmod.held_back_lines(hold_back(seed), True)
        headers = [line for line in lines if not line.startswith("    ")]
        assert {line.split()[0] for line in headers} == PENDING
        assert all(line.endswith("no info_status") for line in headers)
        assert "pending_lgu" not in out
        assert "written as null" not in out

    def test_the_two_switches_are_independent(self):
        done = self.run("--dry-run", "--include-suggested-links")
        assert done.returncode == 0, done.stderr
        assert "9 suggested links included" in done.stdout
        assert "suspect records, held back:" in done.stdout
        done = self.run("--dry-run", "--include-suspect-records")
        assert "9 suggested links held back" in done.stdout

    def test_a_seed_without_markers_prints_no_block(self, tmp_path):
        for name, records in minimal_seed_raw().items():
            text = yaml.safe_dump({name: records}, sort_keys=False, allow_unicode=True)
            (tmp_path / f"{name}.yaml").write_text(text, encoding="utf-8")
        done = self.run("--dry-run", "--seed-dir", str(tmp_path))
        assert done.returncode == 0, done.stderr
        assert "0 suspect requirements held back in 0 services, 0 marked pending_lgu" in done.stdout
        assert "suspect records," not in done.stdout


# ---- 14. guardrail: one new readable property ----------------------------------------------

PREVIOUS_LABELS = frozenset(
    {"Office", "Service", "Requirement", "Agency", "Step", "Role", "Fee", "Variant", "Alias"}
)
PREVIOUS_RELATIONSHIP_TYPES = frozenset(
    {
        "OFFERS",
        "REQUIRES",
        "SECURED_AT",
        "APPLIES_WHEN",
        "PART_OF",
        "HAS_STEP",
        "NEXT",
        "PERFORMED_BY",
        "HAS_FEE",
        "CHARGES",
        "SATISFIED_BY",
        "IS_OFFICE",
        "KNOWN_AS",
    }
)
PREVIOUS_PROPERTIES = frozenset(
    {
        "id",
        "name",
        "title",
        "classification",
        "transaction_type",
        "who_may_avail",
        "total_fee_text",
        "total_time_text",
        "description",
        "text",
        "group",
        "parent_id",
        "min_required",
        "condition_text",
        "order",
        "citizen_action",
        "agency_action",
        "external_agency",
        "dur_min",
        "dur_max",
        "dur_unit",
        "minutes_min",
        "minutes_max",
        "day_type",
        "label",
        "amount_min",
        "amount_max",
        "unit",
        "note",
        "dimension",
        "value",
        "lang",
    }
)
PREVIOUS_SCHEMA = Schema(
    labels=PREVIOUS_LABELS,
    relationship_types=PREVIOUS_RELATIONSHIP_TYPES,
    properties=PREVIOUS_PROPERTIES,
)


class TestGuardrail:
    def test_info_status_is_readable(self):
        result = validate_cypher("MATCH (s:Service {id: $sid}) RETURN s.info_status LIMIT 1")
        assert result.ok, result.reasons

    def test_the_allow_list_grew_by_exactly_that_one_name(self):
        assert len(PREVIOUS_PROPERTIES) == 32
        assert OFFICIAL_SCHEMA.properties == PREVIOUS_PROPERTIES | {"info_status"}
        assert OFFICIAL_SCHEMA.relationship_types == PREVIOUS_RELATIONSHIP_TYPES
        assert OFFICIAL_SCHEMA.labels == PREVIOUS_LABELS

    @pytest.mark.parametrize(
        "query",
        [
            "MATCH (r:Requirement) RETURN r.suspect LIMIT 5",
            "MATCH (r:Requirement) RETURN r.suspect_reason LIMIT 5",
            "MATCH (s:Service) RETURN s.held_back LIMIT 5",
            "MATCH (r:Requirement) WHERE r.suspect = true RETURN r.text LIMIT 5",
            "MATCH (s:Service {id: $sid}) RETURN s.info_status, s.held_back LIMIT 1",
        ],
    )
    def test_the_marker_names_are_not_readable(self, query):
        assert not validate_cypher(query).ok
        assert not {"suspect", "suspect_reason", "held_back"} & OFFICIAL_SCHEMA.properties

    def test_info_status_was_not_readable_before(self):
        query = "MATCH (s:Service {id: $sid}) RETURN s.info_status LIMIT 1"
        assert not validate_cypher(query, schema=PREVIOUS_SCHEMA).ok


# ---- 15. the Core 1 prompt does not change --------------------------------------------------


class TestCore1PromptIsUnchanged:
    def test_no_canonical_template_reads_info_status(self):
        assert len(TEMPLATES) > 20
        assert [key for key, t in TEMPLATES.items() if "info_status" in t.cypher] == []

    def test_the_templates_are_the_ones_the_previous_allow_list_gave(self):
        assert build_templates(PREVIOUS_SCHEMA) == TEMPLATES

    @pytest.mark.parametrize("intent", CORE1_INTENTS)
    def test_the_intent_slice_does_not_show_it(self, intent):
        slice_ = schema_slice(intent)
        assert all("info_status" not in props for props in slice_.labels.values())
        assert "info_status" not in render_schema(slice_)
        assert slice_ == schema_slice(intent, PREVIOUS_SCHEMA)

    def test_the_full_slice_does_not_show_it(self):
        slice_ = full_schema_slice()
        assert "Service" in slice_.labels
        assert all("info_status" not in props for props in slice_.labels.values())
        assert "info_status" not in render_schema(slice_)
        assert slice_ == full_schema_slice(PREVIOUS_SCHEMA)
        assert render_schema(slice_) == render_schema(full_schema_slice(PREVIOUS_SCHEMA))
