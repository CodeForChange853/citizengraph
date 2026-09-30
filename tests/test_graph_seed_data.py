"""The curated seed under graph/seed/: what is in it, what is not, and that it matches the charter.

Expected numbers come from the source spreadsheets (see graph/seed/draft/*.yaml and
docs/charter_data.md), not from the seed itself.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest
from graph_fixtures import staff_names

from citizengraph.graph.loader import DEFAULT_SEED_DIR, load_seed
from citizengraph.graph.memory import InMemoryGraph

ROOT = Path(__file__).resolve().parents[1]

INCLUDED = [
    "BPLO-01", "BPLO-02", "BPLO-04", "BPLO-05", "BPLO-07",
    "LCRO-01", "LCRO-02", "LCRO-04", "LCRO-06", "LCRO-09", "LCRO-11", "LCRO-13", "LCRO-14",
]  # fmt: skip
EXCLUDED = [
    "BPLO-03", "BPLO-06",
    "LCRO-03", "LCRO-05", "LCRO-07", "LCRO-08", "LCRO-10", "LCRO-12", "LCRO-15", "LCRO-16",
    "LCRO-17",
]  # fmt: skip


@pytest.fixture(scope="module")
def seed():
    return load_seed(DEFAULT_SEED_DIR)


@pytest.fixture(scope="module")
def graph(seed):
    return InMemoryGraph(seed)


@pytest.fixture(scope="module")
def sid(seed):
    """charter_ref -> service id."""
    return {s.charter_ref: s.id for s in seed.services}


def steps_by_order(graph, sid, ref):
    return {s.order: s for s in graph.steps(sid[ref])}


def reqs_by_text(graph, sid, ref, text):
    return [r for r in graph.requirements(sid[ref]) if r.text.startswith(text)]


class TestScope:
    def test_exactly_the_thirteen_clean_services(self, seed):
        assert sorted(s.charter_ref for s in seed.services) == sorted(INCLUDED)

    def test_services_with_validation_mismatches_are_left_out(self, seed):
        present = {s.charter_ref for s in seed.services}
        assert not present & set(EXCLUDED)
        assert len(INCLUDED) == 13
        assert len(EXCLUDED) == 11

    def test_two_offices_and_every_service_belongs_to_one(self, seed):
        assert {o.id for o in seed.offices} == {"bplo", "lcro"}
        by_prefix = {"BPLO": "bplo", "LCRO": "lcro"}
        for s in seed.services:
            assert s.office_id == by_prefix[s.charter_ref.split("-")[0]]

    def test_every_service_has_steps_and_no_orphans(self, seed):
        service_ids = {s.id for s in seed.services}
        assert {st.service_id for st in seed.steps} == service_ids
        assert {r.service_id for r in seed.requirements} <= service_ids
        assert {f.service_id for f in seed.fees} <= service_ids


class TestProvenance:
    def test_every_record_needs_review(self, seed):
        everything = [
            *seed.offices, *seed.services, *seed.requirements,
            *seed.steps, *seed.fees, *seed.variants,
        ]  # fmt: skip
        assert everything
        assert {r.review_status for r in everything} == {"needs_review"}

    def test_every_record_points_at_a_sheet_and_row_range(self, seed):
        for s in seed.services:
            assert s.source.sheet == ("BPLO" if s.charter_ref.startswith("BPLO") else "CRO")
            assert s.source.file in {"BPLO-CC.xlsx", "LCRO-CC.xlsx"}
            lo, hi = s.source.rows
            assert 1 <= lo < hi
        for rec in [*seed.requirements, *seed.steps, *seed.fees]:
            assert rec.source.sheet
            lo, hi = rec.source.rows
            assert lo <= rec.source_row <= hi
        for rec in [*seed.offices, *seed.variants]:
            assert rec.sources

    def test_service_blocks_match_the_charter_row_ranges(self, seed):
        rows = {s.charter_ref: tuple(s.source.rows) for s in seed.services}
        assert rows["BPLO-01"] == (11, 49)
        assert rows["BPLO-05"] == (113, 130)
        assert rows["LCRO-01"] == (21, 40)
        assert rows["LCRO-11"] == (250, 276)


class TestDurations:
    def test_day_type_is_unknown_everywhere(self, seed):
        assert {st.duration.day_type for st in seed.steps} == {"unknown"}

    def test_stated_durations_keep_the_parsed_structure(self, seed):
        stated = [st.duration for st in seed.steps if st.duration.status == "stated"]
        assert stated
        for d in stated:
            assert d.value_min is not None
            assert d.value_max is not None
            assert d.unit in {"minute", "hour", "day"}
            assert d.raw

    def test_range_and_day_durations(self, graph, sid):
        d = steps_by_order(graph, sid, "BPLO-01")[4].duration
        assert (d.value_min, d.value_max, d.unit) == (5, 10, "minute")
        d = steps_by_order(graph, sid, "LCRO-02")[4].duration
        assert (d.value_min, d.value_max, d.unit) == (10, 10, "day")

    def test_unstated_durations_are_null_not_zero(self, graph, sid):
        d = steps_by_order(graph, sid, "BPLO-01")[5].duration
        assert d.status == "not_stated"
        assert d.value_min is None and d.value_max is None and d.unit is None

    def test_shared_cells_are_counted_once(self, graph, sid):
        steps = steps_by_order(graph, sid, "BPLO-02")
        assert steps[5].duration.value_max == 2
        assert steps[6].duration.status == "not_stated"
        assert steps[6].duration_shared_from == steps[5].id
        assert steps[7].duration_shared_from == steps[5].id

    @pytest.mark.parametrize(
        ("ref", "minutes", "days"),
        [
            ("BPLO-01", 37, 0), ("BPLO-02", 13, 0), ("BPLO-04", 16, 0), ("BPLO-05", 18, 0),
            ("BPLO-07", 25, 0), ("LCRO-01", 38, 0), ("LCRO-02", 33, 10), ("LCRO-04", 31, 0),
            ("LCRO-06", 38, 0), ("LCRO-09", 28, 0), ("LCRO-11", 74, 0), ("LCRO-13", 74, 0),
            ("LCRO-14", 74, 0),
        ],
    )  # fmt: skip
    def test_step_times_add_up_to_the_stated_total(self, graph, sid, ref, minutes, days):
        got_min = got_days = 0.0
        for st in graph.steps(sid[ref]):
            d = st.duration
            if d.status != "stated":
                continue
            if d.unit == "day":
                got_days += d.value_max
            elif d.unit == "hour":
                got_min += d.value_max * 60
            else:
                got_min += d.value_max
        assert (got_min, got_days) == (minutes, days)


class TestFees:
    @pytest.mark.parametrize(
        ("ref", "total"),
        [("BPLO-01", 235.5), ("BPLO-04", 250), ("LCRO-09", 110), ("LCRO-11", 220),
         ("LCRO-13", 540), ("LCRO-14", 300)],
    )  # fmt: skip
    def test_unconditional_fees_add_up_to_the_stated_total(self, graph, sid, ref, total):
        fees = [
            f for f in graph.fees(sid[ref]) if not graph.fee_condition_unresolved(f.id)
        ]
        assert sum(f.amount_max for f in fees) == pytest.approx(total)
        assert all(f.amount_min == f.amount_max for f in fees)

    @pytest.mark.parametrize(
        ("taxpayer", "total"), [("company", 215), ("individual", 310)]
    )
    def test_occupational_permit_fee_depends_on_taxpayer(self, graph, sid, taxpayer, total):
        fees = graph.fees(sid["BPLO-02"], {"taxpayer": taxpayer})
        assert sum(f.amount_max for f in fees) == pytest.approx(total)
        tax = [f for f in fees if f.label == "Occupational Tax"]
        assert len(tax) == 1

    @pytest.mark.parametrize(
        ("category", "amount", "unit"),
        [("MD", 1000, "per cock"), ("Derby", 1500, "per cock"), ("2C", 3000, None),
         ("3C", 4500, None), ("4C", 6000, None), ("5C", 7500, None)],
    )  # fmt: skip
    def test_cockfight_fee_by_category(self, graph, sid, category, amount, unit):
        fees = graph.fees(sid["BPLO-05"], {"cockfight_category": category})
        assert [(f.amount_min, f.amount_max, f.unit) for f in fees] == [(amount, amount, unit)]

    def test_cockfight_without_a_category_lists_all_six(self, graph, sid):
        assert len(graph.fees(sid["BPLO-05"])) == 6

    @pytest.mark.parametrize(
        "ref", ["LCRO-01", "LCRO-02", "LCRO-04", "LCRO-06", "BPLO-07"]
    )
    def test_services_with_no_fee_rows(self, graph, seed, sid, ref):
        assert graph.fees(sid[ref]) == []
        service = graph.service(sid[ref])
        assert service.total_fee_text is not None

    def test_bplo_04_fixed_fee_keeps_its_note_and_has_no_invented_label(self, graph, sid):
        fees = graph.fees(sid["BPLO-04"])
        fixed = next(f for f in fees if f.amount_max == 200)
        assert fixed.note == "fixed"
        assert fixed.label is None
        assert next(f for f in fees if f.amount_max == 50).label == "garbage fee"

    def test_court_order_local_tax_code_fees_are_curated_but_marked_conditional(self, graph, sid):
        cond = [f for f in graph.fees(sid["LCRO-11"]) if graph.fee_condition_unresolved(f.id)]
        assert sorted(f.amount_max for f in cond) == [200, 200, 200, 200, 500, 500, 500, 500, 500]
        assert all(f.condition_text and not f.variant_ids for f in cond)
        assert all(f.label for f in cond)
        labels = " | ".join(f.label for f in cond)
        assert "Annulment/Legal separation" in labels
        assert "Presumptive Death" in labels

    def test_every_fee_points_at_a_step_of_its_own_service(self, seed):
        steps = {s.id: s for s in seed.steps}
        for f in seed.fees:
            assert f.step_id is not None
            assert steps[f.step_id].service_id == f.service_id


class TestVariants:
    def test_dimensions_in_use(self, seed):
        dims = Counter(v.dimension for v in seed.variants)
        assert dims == {
            "business_type": 3,
            "applicant_type": 1,
            "taxpayer": 2,
            "cockfight_category": 6,
            "birth_status": 2,
            "foreign_parent": 1,
        }

    def test_business_permit_documents_depend_on_business_type(self, graph, sid):
        def texts(business_type):
            return {
                r.text
                for r in graph.requirements(sid["BPLO-01"], {"business_type": business_type})
            }

        assert "DTI Certification of Registration" in texts("single_proprietor")
        assert "DTI Certification of Registration" not in texts("association")
        assert "SEC Certificate of Registration" in texts("association")
        assert "SEC Certificate of Registration" not in texts("single_proprietor")
        assert "SEC Certificate of Incorporation" in texts("corporation")
        assert "Duly accomplished Mayor’s Permit Application Form" in texts("corporation")

    def test_for_new_business_bullets_link_applicant_type_new(self, graph, sid):
        for text in ("By-Laws", "Articles of Incorporation"):
            (r,) = reqs_by_text(graph, sid, "BPLO-01", text)
            assert set(r.variant_ids) == {"business_type:corporation", "applicant_type:new"}
            assert "new business" in r.condition_text
        assert not [
            r
            for r in graph.requirements(sid["BPLO-01"], {"applicant_type": "renewal"})
            if r.text.startswith("By-Laws")
        ]

    def test_second_corporation_heading_is_not_guessed_to_mean_cooperative(self, graph, sid):
        groups = [r for r in graph.requirements(sid["BPLO-01"]) if r.text == "Corporation:"]
        assert len(groups) == 2
        linked, unlinked = sorted(groups, key=lambda r: len(r.variant_ids), reverse=True)
        assert linked.variant_ids == ["business_type:corporation"]
        assert unlinked.variant_ids == []
        assert unlinked.condition_structured is False
        assert any(f.code == "heading_maybe_cooperative" for f in unlinked.flags)
        (cda,) = reqs_by_text(graph, sid, "BPLO-01", "CDA Certificate")
        assert cda.variant_ids == []
        assert graph.condition_unresolved(cda.id)

    def test_no_cooperative_variant_exists(self, seed):
        assert "business_type:cooperative" not in {v.id for v in seed.variants}

    def test_foreign_parent_documents(self, graph, sid):
        with_foreign = {r.text for r in graph.requirements(sid["LCRO-02"], {"foreign_parent": "yes"})}
        without = {r.text for r in graph.requirements(sid["LCRO-02"], {"foreign_parent": "no"})}
        assert any("Valid passport or BI Clearance" in t for t in with_foreign)
        assert not any("Valid passport or BI Clearance" in t for t in without)

    def test_birth_status_documents(self, graph, sid):
        non_marital = {
            r.text for r in graph.requirements(sid["LCRO-02"], {"birth_status": "non_marital"})
        }
        marital = {r.text for r in graph.requirements(sid["LCRO-02"], {"birth_status": "marital"})}
        assert any(t.startswith("Affidavit to Use Surname of the Father") for t in non_marital)
        assert not any(t.startswith("Affidavit to Use Surname of the Father") for t in marital)
        assert any("Appearance only of mother" in t for t in non_marital)
        assert not any("Appearance only of mother" in t for t in marital)
        assert any("Appearance of both parents" in t for t in marital)
        assert (
            len(reqs_by_text(graph, sid, "LCRO-01", "Affidavit to Use Surname of the Father")) == 1
        )

    def test_timely_and_delayed_are_separate_services_not_variants(self, seed):
        assert not {v.dimension for v in seed.variants} & {"timeliness", "registration_timing"}

    def test_any_two_documents_group_carries_min_required(self, graph, sid):
        (group,) = reqs_by_text(graph, sid, "LCRO-02", "Any two (2) documentary evidence")
        assert group.group is True
        assert group.min_required == 2
        children = [r for r in graph.requirements(sid["LCRO-02"]) if r.parent_id == group.id]
        assert len(children) == 4
        (deceased,) = [c for c in children if "deceased" in c.text]
        assert deceased.condition_text and deceased.condition_structured is False

    def test_vague_any_two_documents_is_not_guessed_into_a_group(self, graph, sid):
        (a,) = reqs_by_text(graph, sid, "LCRO-02", "Baptismal Certificate")
        assert a.group is False
        assert a.min_required is None
        assert any(f.code == "min_required_unclear" for f in a.flags)


class TestExternalAgencies:
    def test_steps_belonging_to_other_agencies(self, seed):
        refs = {s.id: s.charter_ref for s in seed.services}
        got = {
            (refs[st.service_id], st.order): st.external_agency
            for st in seed.steps
            if st.external_agency
        }
        treasurer = "City Treasurer’s Office"
        assert got == {
            ("BPLO-01", 5): treasurer,
            ("BPLO-02", 3): treasurer,
            ("BPLO-04", 2): treasurer,
            ("BPLO-05", 2): treasurer,
            ("BPLO-07", 1): "City Agriculture Office",
            ("BPLO-07", 2): "City Agriculture Office",
        }

    def test_treasurer_staff_steps_that_are_not_clearly_external_are_flagged(self, graph, sid):
        for order in (3, 4):
            st = steps_by_order(graph, sid, "BPLO-01")[order]
            assert st.external_agency is None
            assert any(f.code == "external_agency_unclear" for f in st.flags)


ALLOWED_ROLES = {
    "Any authorized office personnel/staff",
    "Any authorized CTO staff",
    "Any authorized City Treasurer’s Office collector",
    "BPLO Chief",
    "Any authorized BPLO personnel & staff",
    "Any BPLO personnel or staff",
    "Any BPLO authorized staff",
    "Any CTO Office authorized collector",
    "Any authorized BPLO staff",
    "Any authorized CTO collector",
    "City Agriculture Office authorized personnel",
    "Any authorized City Agriculture Office collector",
    "Registration Officer",
    "City Civil Registrar",
    "LCR Personnel",
}


class TestRolesAndStaffNames:
    def test_roles_come_only_from_titles_the_charter_gives(self, seed):
        assert {st.role for st in seed.steps if st.role} <= ALLOWED_ROLES

    def test_named_only_steps_have_no_role_and_a_flag(self, graph, sid):
        st = steps_by_order(graph, sid, "BPLO-01")[2]
        assert st.role is None
        assert st.internal_person_raw == "Nila Bernardo / Reina Sabenicio"
        assert any(f.code == "role_not_given" for f in st.flags)
        assert steps_by_order(graph, sid, "LCRO-01")[1].role is None

    def test_missing_person_is_null_with_a_flag(self, graph, sid):
        st = steps_by_order(graph, sid, "BPLO-01")[10]
        assert st.role is None and st.internal_person_raw is None
        assert any(f.code == "person_missing" for f in st.flags)

    def test_title_plus_names_keeps_only_the_title(self, graph, sid):
        st = steps_by_order(graph, sid, "BPLO-01")[3]
        assert st.role == "Any authorized CTO staff"
        assert "Evangeline" in st.internal_person_raw
        assert steps_by_order(graph, sid, "BPLO-04")[4].role == "BPLO Chief"
        assert steps_by_order(graph, sid, "LCRO-01")[3].role == "Registration Officer"
        assert steps_by_order(graph, sid, "LCRO-01")[4].role == "City Civil Registrar"

    def test_every_step_without_a_role_is_flagged(self, seed):
        for st in seed.steps:
            if st.role is None:
                assert {f.code for f in st.flags} & {"role_not_given", "person_missing"}, st.id

    def test_staff_names_appear_nowhere_except_the_internal_field(self, seed):
        names = staff_names(seed)
        assert len(names) > 20
        everything = [
            *seed.offices, *seed.services, *seed.requirements,
            *seed.steps, *seed.fees, *seed.variants,
        ]  # fmt: skip
        dumped = json.dumps([r.model_dump(mode="json") for r in everything], ensure_ascii=False)
        assert sorted(n for n in names if n in dumped) == []


class TestFlags:
    def test_blank_who_may_avail_is_null_and_flagged(self, graph, sid):
        for ref in ("BPLO-04", "BPLO-07"):
            s = graph.service(sid[ref])
            assert s.who_may_avail is None
            assert any(f.code == "who_may_avail_blank" for f in s.flags)
        assert graph.service(sid["BPLO-05"]).who_may_avail == "Open to all cockfight enthusiasts"

    def test_missing_where_to_secure_is_null_and_flagged(self, graph, sid):
        for text in ("By-Laws", "Articles of Incorporation"):
            (r,) = reqs_by_text(graph, sid, "BPLO-01", text)
            assert r.secured_at is None
            assert any(f.code == "where_to_secure_missing" for f in r.flags)

    def test_merged_where_to_secure_is_copied_and_flagged(self, graph, sid):
        reqs = graph.requirements(sid["LCRO-11"])
        shared = [r for r in reqs if any(f.code == "where_to_secure_shared" for f in r.flags)]
        assert len(shared) == 4
        assert {r.secured_at for r in shared} == {"Judicial Court"}

    def test_every_leaf_requirement_without_a_place_is_flagged(self, seed):
        for r in seed.requirements:
            if not r.group and r.secured_at is None:
                assert any(f.code == "where_to_secure_missing" for f in r.flags), r.id

    def test_every_unstated_time_is_flagged(self, seed):
        for st in seed.steps:
            if st.duration.status != "stated":
                codes = {f.code for f in st.flags}
                assert codes & {"time_not_stated", "merged_cell_shared"}, st.id

    def test_day_durations_are_flagged_as_calendar_or_working_unknown(self, graph, sid):
        st = steps_by_order(graph, sid, "LCRO-02")[4]
        assert any(f.code == "day_type_unknown" for f in st.flags)

    def test_suspected_copy_paste_in_death_registration(self, graph, sid):
        s = graph.service(sid["LCRO-06"])
        assert any(f.code == "suspected_copy_paste" for f in s.flags)
        for r in graph.requirements(sid["LCRO-06"]):
            assert any(f.code == "suspected_copy_paste" for f in r.flags)
        assert any(
            f.code == "suspected_copy_paste" for f in steps_by_order(graph, sid, "LCRO-06")[7].flags
        )

    def test_birth_registration_checklist_with_only_a_conditional_item_is_flagged(
        self, graph, sid
    ):
        s = graph.service(sid["LCRO-01"])
        assert any(f.code == "checklist_only_conditional" for f in s.flags)

    def test_posting_period_flag_mentions_the_open_statutory_question(self, graph, sid):
        st = steps_by_order(graph, sid, "LCRO-02")[4]
        flag = next(f for f in st.flags if f.code == "day_type_unknown")
        assert "RA 11032" in flag.message


class TestDocs:
    def test_seed_status_lists_every_included_and_excluded_service(self):
        text = (ROOT / "docs" / "seed_status.md").read_text(encoding="utf-8")
        for ref in INCLUDED + EXCLUDED:
            assert ref in text, ref
        excluded_section = text.split("## Excluded")[1]
        for ref in EXCLUDED:
            row = next(line for line in excluded_section.splitlines() if ref in line)
            assert len(row.split("|")) >= 4 and len(row.strip(" |")) > 30, ref

    def test_seed_review_is_in_sync_with_the_seed(self, seed):
        from citizengraph.graph.review import render_review

        path = ROOT / "docs" / "seed_review.md"
        assert path.read_text(encoding="utf-8") == render_review(seed)

    def test_seed_review_has_a_section_and_row_references_for_every_service(self, seed):
        text = (ROOT / "docs" / "seed_review.md").read_text(encoding="utf-8")
        for s in seed.services:
            assert f"## {s.charter_ref}" in text
        assert "row " in text
