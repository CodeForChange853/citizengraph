"""Regenerate the draft YAML and reports: ``python -m citizengraph.parsing``.

Reads the four charter workbooks under ``data/raw/`` (never modified) and writes:

* ``graph/seed/draft/<OFFICE>-<NN>.yaml``: one draft per service (BPLO 7, LCRO 17, CHO 15,
  CSWDO 1), plus ``validation_report.md`` and ``parse_flags.md``;
* ``docs/cross_office_links.md``: suggested cross-office references (no graph links).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from citizengraph.parsing.crossoffice import build_cross_office_doc
from citizengraph.parsing.splitter import ServiceDraft, split_workbook, write_drafts
from citizengraph.parsing.validate import build_flags_report, build_report

# In output order. Named explicitly (not globbed) so a stray or newer file in data/raw, such as
# a later CYPCC_BPLO.xlsx, is never ingested silently.
WORKBOOKS = ("BPLO-CC.xlsx", "LCRO-CC.xlsx", "CYPCC_HEALTH.xlsx", "CYPCC_SOCIALWELFARE.xlsx")


def run(raw_dir: Path, out_dir: Path, docs_dir: Path) -> list[ServiceDraft]:
    missing = [name for name in WORKBOOKS if not (raw_dir / name).is_file()]
    if missing:
        raise FileNotFoundError(f"missing charter workbook(s) in {raw_dir}: {', '.join(missing)}")
    drafts: list[ServiceDraft] = []
    for name in WORKBOOKS:
        drafts.extend(split_workbook(raw_dir / name))
    write_drafts(drafts, out_dir)
    (out_dir / "validation_report.md").write_text(build_report(drafts), encoding="utf-8")
    (out_dir / "parse_flags.md").write_text(build_flags_report(drafts), encoding="utf-8")
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "cross_office_links.md").write_text(
        build_cross_office_doc(drafts), encoding="utf-8"
    )
    return drafts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=Path("data/raw"))
    parser.add_argument("--out", type=Path, default=Path("graph/seed/draft"))
    parser.add_argument("--docs", type=Path, default=Path("docs"))
    args = parser.parse_args(argv)
    drafts = run(args.raw, args.out, args.docs)
    print(
        f"wrote {len(drafts)} service drafts and 2 reports to {args.out}, "
        f"and cross_office_links.md to {args.docs}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
