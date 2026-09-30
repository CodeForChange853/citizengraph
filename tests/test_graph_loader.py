"""Seed loader: reads the YAML files and cross-validates them. Only in-memory data is used."""

from __future__ import annotations

from typing import Any

import pytest
import yaml
from graph_fixtures import minimal_seed_raw

from citizengraph.graph.loader import SeedError, load_seed, parse_seed, validate_seed


def codes(raw: dict[str, list[dict[str, Any]]]) -> set[str]:
    """Error codes raised for `raw` (empty if it loads cleanly)."""
    try:
        parse_seed(raw)
    except SeedError as exc:
        return {issue.code for issue in exc.issues}
    return set()


def find(raw: dict, kind: str, rec_id: str) -> dict[str, Any]:
    return next(r for r in raw[kind] if r["id"] == rec_id)


def test_the_minimal_seed_is_valid():
    seed = parse_seed(minimal_seed_raw())
    assert validate_seed(seed) == []
    assert [s.id for s in seed.services] == ["svc"]


def test_every_problem_is_reported_not_just_the_first():
    raw = minimal_seed_raw()
    find(raw, "steps", "svc-S01")["service_id"] = "nope"
    find(raw, "fees", "svc-F01")["variant_ids"] = ["taxpayer:ghost"]
    find(raw, "fees", "svc-F01")["condition_text"] = "x"
    find(raw, "fees", "svc-F01")["condition_structured"] = True
    with pytest.raises(SeedError) as info:
        parse_seed(raw)
    assert {"unknown_service", "unknown_variant"} <= {i.code for i in info.value.issues}
    assert len(info.value.issues) >= 2
    assert "svc-S01" in str(info.value)


class TestDuplicateIds:
    @pytest.mark.parametrize(
        ("kind", "rec_id"),
        [
            ("offices", "o1"),
            ("services", "svc"),
            ("requirements", "svc-R01"),
            ("steps", "svc-S01"),
            ("fees", "svc-F01"),
            ("variants", "taxpayer:company"),
            ("links", "link-01"),
        ],
    )
    def test_duplicate_id_within_a_file(self, kind, rec_id):
        raw = minimal_seed_raw()
        raw[kind].append(dict(find(raw, kind, rec_id)))
        assert "duplicate_id" in codes(raw)

    def test_an_id_reused_across_node_kinds_is_rejected(self):
        raw = minimal_seed_raw()
        find(raw, "fees", "svc-F01")["id"] = "svc-S01"
        assert "duplicate_id" in codes(raw)


class TestReferences:
    def test_service_needs_a_known_office(self):
        raw = minimal_seed_raw()
        raw["services"][0]["office_id"] = "ghost"
        assert "unknown_office" in codes(raw)

    @pytest.mark.parametrize("kind", ["requirements", "steps", "fees"])
    def test_children_need_a_known_service(self, kind):
        raw = minimal_seed_raw()
        raw[kind][0]["service_id"] = "ghost"
        assert "unknown_service" in codes(raw)

    def test_requirement_variant_must_exist(self):
        raw = minimal_seed_raw()
        find(raw, "requirements", "svc-R05")["variant_ids"] = ["birth_status:ghost"]
        assert "unknown_variant" in codes(raw)

    def test_fee_variant_must_exist(self):
        raw = minimal_seed_raw()
        find(raw, "fees", "svc-F02")["variant_ids"] = ["taxpayer:ghost"]
        assert "unknown_variant" in codes(raw)

    def test_fee_step_must_exist_in_the_same_service(self):
        raw = minimal_seed_raw()
        find(raw, "fees", "svc-F01")["step_id"] = "svc-S99"
        assert "unknown_step" in codes(raw)

        raw = minimal_seed_raw()
        raw["services"].append({**raw["services"][0], "id": "other", "charter_ref": "T-02"})
        raw["steps"].append(
            {
                **find(raw, "steps", "svc-S01"),
                "id": "other-S01",
                "service_id": "other",
                "next_id": None,
            }
        )
        find(raw, "fees", "svc-F01")["step_id"] = "other-S01"
        assert "step_other_service" in codes(raw)

    def test_a_fee_may_have_no_step(self):
        raw = minimal_seed_raw()
        find(raw, "fees", "svc-F01")["step_id"] = None
        assert codes(raw) == set()


class TestRequirementTree:
    def test_unknown_parent(self):
        raw = minimal_seed_raw()
        find(raw, "requirements", "svc-R03")["parent_id"] = "svc-R99"
        assert "unknown_parent" in codes(raw)

    def test_parent_in_another_service(self):
        raw = minimal_seed_raw()
        raw["services"].append({**raw["services"][0], "id": "other", "charter_ref": "T-02"})
        raw["steps"].append(
            {
                **find(raw, "steps", "svc-S01"),
                "id": "other-S01",
                "service_id": "other",
                "next_id": None,
            }
        )
        raw["requirements"].append(
            {
                **find(raw, "requirements", "svc-R01"),
                "id": "other-R01",
                "service_id": "other",
                "parent_id": "svc-R02",
            }
        )
        assert "parent_other_service" in codes(raw)

    def test_parent_cycle(self):
        raw = minimal_seed_raw()
        find(raw, "requirements", "svc-R02")["parent_id"] = "svc-R03"
        assert "parent_cycle" in codes(raw)

    def test_a_requirement_cannot_be_its_own_parent(self):
        raw = minimal_seed_raw()
        find(raw, "requirements", "svc-R02")["parent_id"] = "svc-R02"
        assert "parent_cycle" in codes(raw)

    def test_children_must_carry_all_variants_of_their_parent(self):
        raw = minimal_seed_raw()
        child = find(raw, "requirements", "svc-R03")
        child["variant_ids"] = []
        child["condition_text"] = None
        child["condition_structured"] = None
        assert "variant_not_inherited" in codes(raw)

    def test_a_parent_must_be_marked_as_a_group(self):
        raw = minimal_seed_raw()
        find(raw, "requirements", "svc-R02")["group"] = False
        find(raw, "requirements", "svc-R02")["min_required"] = None
        assert "group_mismatch" in codes(raw)

    def test_min_required_cannot_exceed_the_number_of_children(self):
        raw = minimal_seed_raw()
        find(raw, "requirements", "svc-R02")["min_required"] = 2
        assert "min_required_too_large" in codes(raw)


class TestStepChain:
    def test_service_without_steps(self):
        raw = minimal_seed_raw()
        raw["steps"] = []
        raw["fees"] = []
        assert "no_steps" in codes(raw)

    def test_orders_must_be_1_to_n_without_gaps_or_repeats(self):
        raw = minimal_seed_raw()
        find(raw, "steps", "svc-S03")["order"] = 4
        assert "step_order" in codes(raw)
        raw = minimal_seed_raw()
        find(raw, "steps", "svc-S03")["order"] = 2
        assert "step_order" in codes(raw)

    def test_unknown_next(self):
        raw = minimal_seed_raw()
        find(raw, "steps", "svc-S01")["next_id"] = "svc-S99"
        assert "unknown_next" in codes(raw)

    def test_next_in_another_service(self):
        raw = minimal_seed_raw()
        raw["services"].append({**raw["services"][0], "id": "other", "charter_ref": "T-02"})
        raw["steps"].append(
            {**find(raw, "steps", "svc-S03"), "id": "other-S01", "service_id": "other", "order": 1}
        )
        find(raw, "steps", "svc-S03")["next_id"] = "other-S01"
        assert "next_other_service" in codes(raw)

    def test_broken_chain_missing_link(self):
        raw = minimal_seed_raw()
        find(raw, "steps", "svc-S01")["next_id"] = None
        assert "next_chain" in codes(raw)

    def test_chain_cannot_loop_back(self):
        raw = minimal_seed_raw()
        find(raw, "steps", "svc-S03")["next_id"] = "svc-S01"
        assert "next_chain" in codes(raw)

    def test_two_steps_cannot_share_a_successor(self):
        raw = minimal_seed_raw()
        find(raw, "steps", "svc-S01")["next_id"] = "svc-S03"
        assert "next_chain" in codes(raw)

    def test_chain_must_follow_the_order_numbers(self):
        raw = minimal_seed_raw()
        find(raw, "steps", "svc-S01")["next_id"] = "svc-S03"
        find(raw, "steps", "svc-S03")["next_id"] = "svc-S02"
        find(raw, "steps", "svc-S02")["next_id"] = None
        assert "next_chain" in codes(raw)

    def test_shared_duration_must_point_at_an_earlier_step_with_a_value(self):
        raw = minimal_seed_raw()
        find(raw, "steps", "svc-S03")["duration_shared_from"] = "svc-S99"
        assert "unknown_shared_from" in codes(raw)
        raw = minimal_seed_raw()
        find(raw, "steps", "svc-S01")["duration_shared_from"] = "svc-S03"
        assert "unknown_shared_from" in codes(raw)
        raw = minimal_seed_raw()
        step = find(raw, "steps", "svc-S03")
        step["duration_shared_from"] = "svc-S01"
        step["duration"] = {"status": "not_stated", "day_type": "unknown"}
        assert codes(raw) == set()


class TestSourceReferences:
    def test_row_must_lie_inside_the_service_block(self):
        raw = minimal_seed_raw()
        find(raw, "requirements", "svc-R01")["source_row"] = 99
        assert "source_row_outside" in codes(raw)

    def test_service_total_row_must_lie_inside_the_block(self):
        raw = minimal_seed_raw()
        raw["services"][0]["total_source_row"] = 99
        assert "source_row_outside" in codes(raw)

    def test_child_source_must_be_the_services_block(self):
        raw = minimal_seed_raw()
        find(raw, "steps", "svc-S01")["source"] = {"file": "X.xlsx", "sheet": "T", "rows": [10, 40]}
        assert "source_mismatch" in codes(raw)


def test_agency_and_role_names_that_collapse_to_one_id_are_rejected():
    raw = minimal_seed_raw()
    find(raw, "requirements", "svc-R01")["secured_at"] = "City Treasurer's Office"
    find(raw, "requirements", "svc-R05")["secured_at"] = "City Treasurers Office"
    assert "duplicate_slug" in codes(raw)


def second_service(raw):
    raw["services"].append({**raw["services"][0], "id": "other", "charter_ref": "T-02"})
    raw["steps"].append(
        {**find(raw, "steps", "svc-S01"), "id": "other-S01", "service_id": "other", "next_id": None}
    )


def satisfied_by(raw, **over):
    raw["links"].append(
        {
            "id": "link-02",
            "kind": "requirement_satisfied_by",
            "requirement_id": "svc-R01",
            "agency": None,
            "service_id": "other",
            "office_id": None,
            "review_status": "needs_review",
            "flags": [],
            "sources": [{"file": "TEST.xlsx", "sheet": "T", "rows": [10, 40]}],
            **over,
        }
    )


class TestLinks:
    def test_a_valid_cross_service_link(self):
        raw = minimal_seed_raw()
        second_service(raw)
        satisfied_by(raw)
        assert codes(raw) == set()

    def test_requirement_must_exist(self):
        raw = minimal_seed_raw()
        second_service(raw)
        satisfied_by(raw, requirement_id="svc-R99")
        assert "unknown_requirement" in codes(raw)

    def test_target_service_must_exist(self):
        raw = minimal_seed_raw()
        satisfied_by(raw, service_id="ghost")
        assert "unknown_service" in codes(raw)

    def test_a_requirement_cannot_be_satisfied_by_its_own_service(self):
        raw = minimal_seed_raw()
        satisfied_by(raw, service_id="svc")
        assert "link_self" in codes(raw)

    def test_target_office_must_exist(self):
        raw = minimal_seed_raw()
        raw["links"][0]["office_id"] = "ghost"
        assert "unknown_office" in codes(raw)

    def test_agency_must_be_named_by_some_requirement(self):
        raw = minimal_seed_raw()
        raw["links"][0]["agency"] = "Nobody At All"
        assert "unknown_agency" in codes(raw)

    def test_agency_wording_is_matched_after_collapsing_whitespace_only(self):
        raw = minimal_seed_raw()
        raw["links"][0]["agency"] = "  Some   Agency "
        assert codes(raw) == set()
        raw["links"][0]["agency"] = "some agency"
        assert "unknown_agency" in codes(raw)

    def test_context_requirement_must_be_secured_at_that_agency(self):
        raw = minimal_seed_raw()
        raw["links"][0]["requirement_id"] = "svc-R03"  # secured at "Other Agency"
        assert "agency_context_mismatch" in codes(raw)

    def test_one_agency_cannot_be_two_offices(self):
        raw = minimal_seed_raw()
        raw["offices"].append({**raw["offices"][0], "id": "o2", "name": "Second Office"})
        raw["links"].append({**raw["links"][0], "id": "link-02", "office_id": "o2"})
        assert "agency_two_offices" in codes(raw)

    def test_the_same_link_twice_is_a_duplicate(self):
        raw = minimal_seed_raw()
        raw["links"].append({**raw["links"][0], "id": "link-02"})
        assert "duplicate_link" in codes(raw)

    def test_link_sources_must_be_service_blocks_of_the_seed(self):
        raw = minimal_seed_raw()
        second_service(raw)
        satisfied_by(raw, sources=[{"file": "TEST.xlsx", "sheet": "T", "rows": [90, 99]}])
        assert "source_mismatch" in codes(raw)


class TestFiles:
    def write(self, tmp_path, raw):
        for kind, records in raw.items():
            (tmp_path / f"{kind}.yaml").write_text(
                yaml.safe_dump({kind: records}, sort_keys=False), encoding="utf-8"
            )

    def test_loads_from_a_directory(self, tmp_path):
        self.write(tmp_path, minimal_seed_raw())
        seed = load_seed(tmp_path)
        assert len(seed.requirements) == 5
        assert seed.steps[0].internal_person_raw == "Juan Dela Cruz"

    def test_missing_file(self, tmp_path):
        raw = minimal_seed_raw()
        del raw["fees"]
        self.write(tmp_path, raw)
        with pytest.raises(SeedError) as info:
            load_seed(tmp_path)
        assert [i.code for i in info.value.issues] == ["missing_file"]

    def test_malformed_yaml_and_wrong_top_level_shape(self, tmp_path):
        self.write(tmp_path, minimal_seed_raw())
        (tmp_path / "offices.yaml").write_text("offices: [unclosed", encoding="utf-8")
        with pytest.raises(SeedError) as info:
            load_seed(tmp_path)
        assert info.value.issues[0].code == "bad_yaml"

        (tmp_path / "offices.yaml").write_text("- just a list\n", encoding="utf-8")
        with pytest.raises(SeedError) as info:
            load_seed(tmp_path)
        assert info.value.issues[0].code == "bad_yaml"

    def test_schema_errors_name_the_file_and_record(self, tmp_path):
        raw = minimal_seed_raw()
        find(raw, "fees", "svc-F01")["amount_min"] = "many"
        self.write(tmp_path, raw)
        with pytest.raises(SeedError) as info:
            load_seed(tmp_path)
        issue = info.value.issues[0]
        assert issue.code == "schema"
        assert "svc-F01" in issue.message
