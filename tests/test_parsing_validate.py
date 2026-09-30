"""Validation: stated TOTAL vs sum of parsed step fees/times. Reports; never corrects."""

from pathlib import Path

import pytest

from citizengraph.parsing.durations import parse_duration
from citizengraph.parsing.fees import parse_fees
from citizengraph.parsing.splitter import ServiceDraft, StatedTotal, Step, split_workbook
from citizengraph.parsing.validate import (
    build_flags_report,
    build_report,
    check_service,
)

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"


def mk(steps: list[tuple[str | None, str | None]], total: tuple[str | None, str | None]):
    """A ServiceDraft from (fee cell, time cell) pairs and a (fee, time) stated total."""
    built = [
        Step(
            order=i,
            label=None,
            citizen_step_group=i,
            citizen_action=None,
            agency_action=f"step {i}",
            fees=parse_fees(fee),
            time=parse_duration(time),
            person_responsible_raw=None,
            source_row=i,
        )
        for i, (fee, time) in enumerate(steps, start=1)
    ]
    return ServiceDraft(
        draft_id="T-01",
        source_file="T.xlsx",
        source_sheet="S",
        source_number=1,
        source_rows=(1, 2),
        title="1. T",
        description=None,
        name="T",
        office="O",
        classification="SIMPLE",
        classification_raw="Simple",
        transaction_type=None,
        who_may_avail=None,
        steps=built,
        total=StatedTotal(total[0], total[1], parse_fees(total[0]), parse_duration(total[1]), 3),
    )


# ------------------------------------------------------------------------------ fees


def test_fee_sum_matches():
    d = mk(
        [("₱200.00", "1 minute"), ("none", "1 minute"), ("₱100.00", "1 minute")],
        ("₱300.00", "3 minutes"),
    )
    assert check_service(d).fee.verdict == "match"


def test_fee_sum_mismatch_reports_both_numbers_and_does_not_correct():
    d = mk([("₱200.00", None), ("₱50.00", None)], ("₱300.00", None))
    r = check_service(d).fee
    assert r.verdict == "mismatch"
    assert "₱300.00" in r.stated and "₱250.00" in r.derived
    assert d.total.fee.items[0].amount_max == 300  # draft untouched


def test_stated_none_with_no_step_fees_matches():
    d = mk([("none", None), ("none", None)], ("none", None))
    assert check_service(d).fee.verdict == "match"


def test_stated_none_but_a_step_charges_is_a_mismatch():
    d = mk([("none", None), ("₱20.00", None)], ("none", None))
    assert check_service(d).fee.verdict == "mismatch"


def test_qualifier_totals_are_checked_per_qualifier():
    steps = [
        ("A - ₱25.00\nB - ₱30.00\nTax - ₱120.00 (company)\n₱215.00 (individual)", None),
        ("- - -", None),
    ]
    ok = mk(steps, ("₱175.00 (company)\n₱270.00 (individual)", None))
    assert check_service(ok).fee.verdict == "match"
    bad = mk(steps, ("₱175.00 (company)\n₱310.00 (individual)", None))
    r = check_service(bad).fee
    assert r.verdict == "mismatch"
    assert "individual" in "\n".join(r.details)


def test_labelled_tier_totals_compare_as_sets_not_sums():
    tiers = "MD - ₱1,000 / cock\nDerby - ₱1,500 / cock\n2C - ₱3,000"
    ok = mk(
        [("*ALL FEES TO BE SETTLED AT THE CTO*", None), (tiers, None)],
        ("MD - ₱1,000/cock\nDerby - ₱1,500/cock\n2C - ₱3,000", None),
    )
    assert check_service(ok).fee.verdict == "match"
    bad = mk([(tiers, None)], ("MD - ₱1,000/cock\nDerby - ₱1,500/cock\n2C - ₱3,500", None))
    r = check_service(bad).fee
    assert r.verdict == "mismatch"
    assert "2C" in "\n".join(r.details)


def test_range_total_uses_max_and_hints_at_alternatives():
    d = mk([("₱100.00", None), ("₱195.00", None), ("₱155.00", None)], ("₱255.00 - ₱295.00", None))
    r = check_service(d).fee
    assert r.verdict == "mismatch"  # sum of maxima is 450, stated max is 295
    assert any("subset" in h for h in r.hints)  # 255 = 100+155 and 295 = 100+195


def test_range_total_without_subset_explanation_has_no_hint():
    d = mk([("₱100.00", None), ("₱7.00", None)], ("₱50.00 - ₱60.00", None))
    r = check_service(d).fee
    assert r.verdict == "mismatch" and r.hints == ()


def test_per_unit_fee_counts_once_and_says_so():
    d = mk([("₱50.00", None), ("₱20.00 per copy", None)], ("₱70.00", None))
    r = check_service(d).fee
    assert r.verdict == "match"
    assert any("per copy" in x for x in r.details)


def test_text_only_step_fee_is_named_when_total_has_amounts():
    d = mk([("As determined by the CSWMO", None), ("- - -", None)], ("₱215.00", None))
    r = check_service(d).fee
    assert r.verdict == "mismatch"
    assert "As determined by the CSWMO" in "\n".join(r.details)


def test_total_fee_not_stated_is_not_comparable():
    d = mk([("- - -", None), ("- - -", None)], ("- - -", None))
    assert check_service(d).fee.verdict == "not_comparable"


# ------------------------------------------------------------------------------ times


def test_time_sum_matches_with_ranges_using_max():
    d = mk(
        [(None, "2 minutes"), (None, "5-10 minutes"), (None, "3 - 5 minutes")], (None, "17 mins")
    )
    assert check_service(d).time.verdict == "match"


def test_time_mismatch_reports_delta():
    d = mk([(None, "10 minutes"), (None, "5 minutes")], (None, "20 minutes"))
    r = check_service(d).time
    assert r.verdict == "mismatch"
    assert "20" in r.stated and "15" in r.derived
    assert any("-5" in x for x in r.details)


def test_time_days_and_minutes_are_compared_on_separate_axes():
    d = mk(
        [(None, "10 minutes"), (None, "10 days"), (None, "23 minutes")],
        (None, "10 days, 33 minutes"),
    )
    assert check_service(d).time.verdict == "match"
    wrong_days = mk([(None, "7 - 10 days"), (None, "26 minutes")], (None, "7 days, 26 minutes"))
    assert check_service(wrong_days).time.verdict == "mismatch"


def test_hours_and_minutes_combine():
    d = mk([(None, "2 hours"), (None, "51 minutes")], (None, "2 hours, 51 minutes"))
    assert check_service(d).time.verdict == "match"


def test_steps_without_time_are_listed_and_left_out_of_the_sum():
    d = mk([(None, "10 minutes"), (None, "- - -"), (None, None)], (None, "12 minutes"))
    r = check_service(d).time
    assert r.verdict == "mismatch"
    assert "2" in "\n".join(r.details) and "3" in "\n".join(r.details)


def test_unparsed_step_time_is_not_comparable():
    d = mk([(None, "10 minutes"), (None, "a while")], (None, "10 minutes"))
    r = check_service(d).time
    assert r.verdict == "not_comparable"


def test_total_time_not_stated_is_not_comparable():
    d = mk([(None, "10 minutes")], (None, "- - -"))
    assert check_service(d).time.verdict == "not_comparable"


# ------------------------------------------------------------------------------ real charters


@pytest.fixture(scope="module")
def checks():
    drafts = split_workbook(RAW / "BPLO-CC.xlsx") + split_workbook(RAW / "LCRO-CC.xlsx")
    return drafts, {d.draft_id: check_service(d) for d in drafts}


def verdicts(checks, attr):
    return {k: getattr(v, attr).verdict for k, v in checks[1].items()}


def test_all_24_services_checked(checks):
    assert len(checks[1]) == 24


def test_real_fee_verdicts(checks):
    v = verdicts(checks, "fee")
    mismatches = {k for k, x in v.items() if x == "mismatch"}
    assert mismatches == {"BPLO-03", "LCRO-15", "LCRO-17"}
    assert {k for k, x in v.items() if x == "not_comparable"} == {"BPLO-07"}


def test_real_time_verdicts(checks):
    v = verdicts(checks, "time")
    mismatches = {k for k, x in v.items() if x == "mismatch"}
    assert mismatches == {
        "BPLO-06",
        "LCRO-03",
        "LCRO-05",
        "LCRO-07",
        "LCRO-08",
        "LCRO-10",
        "LCRO-12",
        "LCRO-16",
        "LCRO-17",
    }
    assert not {k for k, x in v.items() if x == "not_comparable"}


def test_known_issues_from_charter_data_are_reproduced(checks):
    by_id = checks[1]
    # Indigency Certification: states 16 minutes, steps sum to 13
    assert "16" in by_id["BPLO-06"].time.stated and "13" in by_id["BPLO-06"].time.derived
    # Streamers & Tarpaulins: states the Occupational Permit total, steps give no amount
    assert by_id["BPLO-03"].fee.verdict == "mismatch"
    # Service 15: two fee variants, one range total -> mismatch with an alternatives hint
    assert by_id["LCRO-15"].fee.hints
    # Service 3: seminar step of 3 hours is inside the sum
    assert "243" in by_id["LCRO-03"].time.derived


def test_reports_are_deterministic_and_list_every_mismatch(checks):
    drafts, by_id = checks
    report = build_report(drafts)
    assert report == build_report(drafts)
    for draft_id, c in by_id.items():
        if "mismatch" in (c.fee.verdict, c.time.verdict):
            assert f"### {draft_id}" in report
        else:
            assert f"### {draft_id}" not in report
    assert "Nothing in this report is auto-corrected" in report


def test_flags_report_covers_all_services(checks):
    text = build_flags_report(checks[0])
    for draft_id in checks[1]:
        assert draft_id in text
