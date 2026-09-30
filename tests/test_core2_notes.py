"""docs/core2_notes.md must stay in step with the code (Filipino list, frozen baseline, counts)."""

import re
from pathlib import Path

from citizengraph.core2 import alerts, report
from citizengraph.core2.eval import load_scenarios

NOTES = (Path(__file__).resolve().parents[1] / "docs" / "core2_notes.md").read_text(
    encoding="utf-8"
)


def test_every_filipino_string_is_listed_for_review():
    for text in (*alerts.FILIPINO_STRINGS, *report.FILIPINO_STRINGS):
        assert text in NOTES, text


def test_filipino_strings_in_code_are_marked_for_review():
    for name in ("alerts.py", "report.py"):
        src = (Path(__file__).resolve().parents[1] / "src/citizengraph/core2" / name).read_text(
            encoding="utf-8"
        )
        assert src.count("NEEDS-NATIVE-REVIEW") >= 10, name


def test_the_frozen_baseline_rules_are_documented():
    for rule in (f"B{i}" for i in range(1, 11)):
        assert re.search(rf"\| {rule} \|", NOTES), rule
    assert "FROZEN" in NOTES


def test_the_scenario_count_in_the_notes_is_the_real_one():
    n = len(load_scenarios())
    assert f"scenarios/*.yaml`, {n})" in NOTES
    for s in load_scenarios():
        assert f"`{s.id.split('_')[0]}`" in NOTES, s.id


def test_the_test_double_is_labelled_wherever_it_appears():
    assert "test double" in NOTES.lower()
    src = (Path(__file__).resolve().parents[1] / "src/citizengraph/core2/scripted.py").read_text(
        encoding="utf-8"
    )
    assert "not evidence of model quality" in src.lower()
