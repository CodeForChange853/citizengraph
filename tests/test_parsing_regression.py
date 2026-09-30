"""Regression: adding the health and social-welfare layouts must not change the first 24 drafts."""

from pathlib import Path

import pytest

from citizengraph.parsing.__main__ import run
from citizengraph.parsing.splitter import split_workbook, write_drafts

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
DRAFTS = ROOT / "graph" / "seed" / "draft"


def _bplo_lcro_names() -> list[str]:
    return [f"BPLO-{i:02d}.yaml" for i in range(1, 8)] + [
        f"LCRO-{i:02d}.yaml" for i in range(1, 18)
    ]


def test_bplo_and_lcro_drafts_regenerate_byte_identical(tmp_path):
    drafts = split_workbook(RAW / "BPLO-CC.xlsx") + split_workbook(RAW / "LCRO-CC.xlsx")
    written = write_drafts(drafts, tmp_path)
    assert sorted(p.name for p in written) == _bplo_lcro_names()
    for path in written:
        assert path.read_bytes() == (DRAFTS / path.name).read_bytes(), path.name


def test_new_keys_never_leak_into_old_drafts():
    for name in _bplo_lcro_names():
        text = (DRAFTS / name).read_text(encoding="utf-8")
        for key in ("agency_action_items", "normalizations", "review:"):
            assert key not in text, (name, key)
        assert "status: ambiguous" not in text


@pytest.fixture(scope="module")
def full_run(tmp_path_factory):
    out = tmp_path_factory.mktemp("draft")
    docs = tmp_path_factory.mktemp("docs")
    drafts = run(RAW, out, docs)
    return drafts, out, docs


def test_full_run_writes_40_drafts_and_the_old_24_are_identical(full_run):
    drafts, out, _ = full_run
    assert len(drafts) == 40
    assert [d.draft_id for d in drafts] == (
        [f"BPLO-{i:02d}" for i in range(1, 8)]
        + [f"LCRO-{i:02d}" for i in range(1, 18)]
        + [f"CHO-{i:02d}" for i in range(1, 16)]
        + ["CSWDO-01"]
    )
    for name in _bplo_lcro_names():
        assert (out / name).read_bytes() == (DRAFTS / name).read_bytes(), name


def test_committed_generated_files_are_current(full_run):
    """Guards against forgetting to regenerate: drafts, reports and cross-office doc."""
    _, out, docs = full_run
    for path in sorted(out.iterdir()):
        assert (DRAFTS / path.name).read_bytes() == path.read_bytes(), path.name
    assert (ROOT / "docs" / "cross_office_links.md").read_bytes() == (
        docs / "cross_office_links.md"
    ).read_bytes()
