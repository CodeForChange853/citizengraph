"""In-memory graph helpers, tested on the tiny fixture (no Neo4j, no files)."""

from __future__ import annotations

import pytest
from graph_fixtures import minimal_seed_raw

from citizengraph.graph.loader import parse_seed
from citizengraph.graph.memory import InMemoryGraph, UnknownServiceError


@pytest.fixture
def graph() -> InMemoryGraph:
    return InMemoryGraph(parse_seed(minimal_seed_raw()))


def ids(items) -> list[str]:
    return [i.id for i in items]


class TestServiceLookup:
    def test_by_id_and_by_name(self, graph):
        assert graph.service("svc").name == "Test Service"
        assert graph.find_service("  test SERVICE ").id == "svc"
        assert graph.find_service("nothing like it") is None

    def test_unknown_id_raises(self, graph):
        with pytest.raises(UnknownServiceError):
            graph.service("ghost")
        for call in (graph.requirements, graph.fees, graph.steps):
            with pytest.raises(UnknownServiceError):
                call("ghost")

    def test_office_and_listing(self, graph):
        assert ids(graph.services()) == ["svc"]
        assert graph.office_of("svc").name == "Test Office"
        assert ids(graph.services(office_id="o1")) == ["svc"]
        assert graph.services(office_id="elsewhere") == []


class TestSteps:
    def test_steps_come_back_in_chain_order(self, graph):
        assert ids(graph.steps("svc")) == ["svc-S01", "svc-S02", "svc-S03"]
        assert [s.order for s in graph.steps("svc")] == [1, 2, 3]

    def test_order_follows_the_next_chain_not_the_file_order(self):
        raw = minimal_seed_raw()
        raw["steps"].reverse()
        assert ids(InMemoryGraph(parse_seed(raw)).steps("svc")) == [
            "svc-S01",
            "svc-S02",
            "svc-S03",
        ]

    def test_external_agency_is_kept(self, graph):
        assert [s.external_agency for s in graph.steps("svc")] == [
            None,
            "City Treasurer's Office",
            None,
        ]


class TestRequirements:
    def test_no_variants_means_nothing_is_filtered_out(self, graph):
        assert ids(graph.requirements("svc")) == [
            "svc-R01",
            "svc-R02",
            "svc-R03",
            "svc-R04",
            "svc-R05",
        ]

    def test_a_given_variant_drops_the_other_branches(self, graph):
        got = ids(graph.requirements("svc", {"birth_status": "marital"}))
        assert "svc-R05" not in got
        assert {"svc-R01", "svc-R02", "svc-R03", "svc-R04"} <= set(got)

    def test_matching_variant_keeps_its_records_and_children(self, graph):
        got = ids(graph.requirements("svc", {"taxpayer": "company"}))
        assert {"svc-R02", "svc-R03"} <= set(got)
        got = ids(graph.requirements("svc", {"taxpayer": "individual"}))
        assert not {"svc-R02", "svc-R03"} & set(got)

    def test_dimensions_combine_with_and_values_within_one_dimension_with_or(self, graph):
        got = ids(graph.requirements("svc", {"taxpayer": ["individual", "company"]}))
        assert {"svc-R02", "svc-R03"} <= set(got)
        got = ids(
            graph.requirements("svc", {"taxpayer": "individual", "birth_status": "non_marital"})
        )
        assert "svc-R05" in got
        assert "svc-R02" not in got

    def test_unstructured_conditions_are_always_returned_and_marked(self, graph):
        got = ids(graph.requirements("svc", {"taxpayer": "individual"}))
        assert "svc-R04" in got
        assert graph.condition_unresolved("svc-R04") is True
        assert graph.condition_unresolved("svc-R01") is False
        assert graph.condition_unresolved("svc-R05") is False

    def test_unresolved_condition_is_inherited_from_the_parent(self):
        raw = minimal_seed_raw()
        parent = next(r for r in raw["requirements"] if r["id"] == "svc-R02")
        parent["variant_ids"] = []
        parent["condition_structured"] = False
        child = next(r for r in raw["requirements"] if r["id"] == "svc-R03")
        child["variant_ids"] = []
        child["condition_structured"] = False
        graph = InMemoryGraph(parse_seed(raw))
        assert graph.condition_unresolved("svc-R03") is True

    def test_unknown_variant_dimension_is_ignored_not_an_error(self, graph):
        assert len(graph.requirements("svc", {"planet": "mars"})) == 5


class TestFees:
    def test_all_fees_without_variants(self, graph):
        assert ids(graph.fees("svc")) == ["svc-F01", "svc-F02", "svc-F03", "svc-F04"]

    def test_variant_selects_the_matching_tier(self, graph):
        got = graph.fees("svc", {"taxpayer": "company"})
        assert ids(got) == ["svc-F01", "svc-F02", "svc-F04"]
        assert [f.amount_min for f in got if f.label == "Tax"] == [120]
        got = graph.fees("svc", {"taxpayer": "individual"})
        assert [f.amount_min for f in got if f.label == "Tax"] == [215]

    def test_unresolved_fee_is_returned_but_marked(self, graph):
        assert graph.fee_condition_unresolved("svc-F04") is True
        assert graph.fee_condition_unresolved("svc-F02") is False


class TestNothingPrivateLeaks:
    def test_no_helper_output_contains_staff_names(self, graph):
        dumped = " ".join(
            str(x.model_dump())
            for x in [
                *graph.steps("svc"),
                *graph.requirements("svc"),
                *graph.fees("svc"),
                graph.service("svc"),
            ]
        )
        assert "Juan" not in dumped
        assert "Maria" not in dumped
