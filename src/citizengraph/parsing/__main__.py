"""Regenerate the draft YAML and reports: ``python -m citizengraph.parsing``.

Reads ``data/raw/*-CC.xlsx`` (never modified) and writes under ``graph/seed/draft/``:
one ``<OFFICE>-<NN>.yaml`` per service, ``validation_report.md`` and ``parse_flags.md``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from citizengraph.parsing.splitter import ServiceDraft, split_workbook, write_drafts
from citizengraph.parsing.validate import build_flags_report, build_report


def run(raw_dir: Path, out_dir: Path) -> list[ServiceDraft]:
    drafts: list[ServiceDraft] = []
    for workbook in sorted(raw_dir.glob("*-CC.xlsx")):
        drafts.extend(split_workbook(workbook))
    write_drafts(drafts, out_dir)
    (out_dir / "validation_report.md").write_text(build_report(drafts), encoding="utf-8")
    (out_dir / "parse_flags.md").write_text(build_flags_report(drafts), encoding="utf-8")
    return drafts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=Path("data/raw"))
    parser.add_argument("--out", type=Path, default=Path("graph/seed/draft"))
    args = parser.parse_args(argv)
    drafts = run(args.raw, args.out)
    print(f"wrote {len(drafts)} service drafts and 2 reports to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
