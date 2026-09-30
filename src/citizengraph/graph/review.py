"""Render ``docs/seed_review.md``: a per-service checklist to review against the spreadsheet.

Regenerate after editing the seed (a test fails when the file is out of date):

    python -m citizengraph.graph.review            # rewrite docs/seed_review.md
    python -m citizengraph.graph.review --check    # exit 1 if it is out of date

Staff names are never printed; the person cell is described by kind only.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

from citizengraph.graph.loader import DEFAULT_SEED_DIR, load_seed
from citizengraph.graph.models import Duration, Fee, Requirement, Seed, Service, Step

REVIEW_PATH = Path(__file__).resolve().parents[3] / "docs" / "seed_review.md"


def _cell(text: object) -> str:
    if text is None or text == "":
        return "—"
    return str(text).replace("|", "\\|").replace("\n", "<br>").strip()


def _num(x: float) -> str:
    return f"{x:g}"


def _duration(d: Duration, shared_from: str | None) -> str:
    if shared_from:
        return f"shared with {shared_from.rsplit('-', 1)[-1]}"
    if d.status == "not_stated":
        return "not stated"
    if d.status == "unparsed":
        return f"unparsed: {d.raw}"
    unit = {"minute": "min", "hour": "h", "day": "days"}[d.unit or "minute"]
    span = _num(d.value_min or 0)
    if d.value_max != d.value_min:
        span += f"–{_num(d.value_max or 0)}"
    return f"{span} {unit}"


def _amount(f: Fee) -> str:
    peso = "₱{:,.2f}"
    text = peso.format(f.amount_min)
    if f.amount_max != f.amount_min:
        text += " – " + peso.format(f.amount_max)
    return text + (f" {f.unit}" if f.unit else "")


def _person_kind(step: Step) -> str:
    raw = step.internal_person_raw
    if raw is None:
        return "blank"
    if step.role is None:
        return "names only"
    if raw.strip().lower() == step.role.lower():
        return "role title"
    return "names + role title"


def _rows(a: int, b: int) -> str:
    return f"rows {a}–{b}"


def _flag_lines(items: list[tuple[int, str, list]]) -> list[str]:
    out: list[str] = []
    for row, label, flags in sorted(items, key=lambda t: (t[0], t[1])):
        for f in flags:
            out.append(f"- [ ] row {row} · {label} · `{f.code}`: {f.message}")
    return out


def _service_section(seed: Seed, svc: Service) -> list[str]:
    reqs = [r for r in seed.requirements if r.service_id == svc.id]
    steps = sorted((s for s in seed.steps if s.service_id == svc.id), key=lambda s: s.order)
    fees = [f for f in seed.fees if f.service_id == svc.id]
    office = next(o for o in seed.offices if o.id == svc.office_id)
    lo, hi = svc.source.rows
    lines = [
        f"## {svc.charter_ref}: {svc.name}",
        "",
        f"- id `{svc.id}` · {office.name} · {svc.classification} · {svc.transaction_type or '—'}",
        f"- Source: `{svc.source.file}`, sheet `{svc.source.sheet}`, {_rows(lo, hi)}"
        f" (total row {svc.total_source_row}) · {svc.review_status}",
        f"- Who may avail: {_cell(svc.who_may_avail)}",
        f"- Stated total fee: {_cell(svc.total_fee_text)}",
        f"- Stated total time: {_cell(svc.total_time_text)}",
        f"- Description: {_cell(svc.description)}",
        "",
        "### Requirements",
        "",
    ]
    if reqs:
        lines += [
            "| ✓ | Row | Id | Requirement | Where to secure | Applies when | ⚑ |",
            "|---|---|---|---|---|---|---|",
        ]
        depth = {r.id: 0 for r in reqs}
        by_id = {r.id: r for r in reqs}
        for r in reqs:
            cur = r
            while cur.parent_id in by_id:
                depth[r.id] += 1
                cur = by_id[cur.parent_id]
        for r in reqs:
            lines.append(_requirement_row(r, depth[r.id]))
    else:
        lines.append("_None in the charter._")
    lines += ["", "### Steps", ""]
    lines += [
        "| ✓ | Row | Id | Label | Citizen step | Agency action | Time | Role | Person cell "
        "| Other agency | ⚑ |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in steps:
        lines.append(
            f"| ☐ | {s.source_row} | {s.id.rsplit('-', 1)[-1]} | {_cell(s.label)} "
            f"| {_cell(s.citizen_action)} | {_cell(s.agency_action)} "
            f"| {_duration(s.duration, s.duration_shared_from)} | {_cell(s.role)} "
            f"| {_person_kind(s)} | {_cell(s.external_agency)} | {len(s.flags) or ''} |"
        )
    lines += ["", "### Fees", ""]
    if fees:
        lines += [
            "| ✓ | Row | Id | Step | Fee | Amount | Applies when | ⚑ |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for f in fees:
            when = _cell(f.condition_text)
            if f.variant_ids:
                when += " → " + ", ".join(f"`{v}`" for v in f.variant_ids)
            elif f.condition_text:
                when += " (text only)"
            step_no = f.step_id.rsplit("-", 1)[-1] if f.step_id else "—"
            lines.append(
                f"| ☐ | {f.source_row} | {f.id.rsplit('-', 1)[-1]} | {step_no} "
                f"| {_cell(f.label)}{' — ' + f.note if f.note else ''} | {_amount(f)} "
                f"| {when} | {len(f.flags) or ''} |"
            )
    else:
        lines.append("_No fee rows._ See the stated total fee above.")
    items: list[tuple[int, str, list]] = [(svc.source.rows[0], "service", svc.flags)]
    items += [(r.source_row, f"requirement {r.id.rsplit('-', 1)[-1]}", r.flags) for r in reqs]
    items += [(s.source_row, f"step {s.order}", s.flags) for s in steps]
    items += [(f.source_row, f"fee {f.id.rsplit('-', 1)[-1]}", f.flags) for f in fees]
    flag_lines = _flag_lines(items)
    lines += ["", f"### Review flags ({len(flag_lines)})", ""]
    lines += flag_lines or ["_None._"]
    lines.append("")
    return lines


def _requirement_row(r: Requirement, depth: int) -> str:
    text = ("↳ " * depth) + _cell(r.text)
    if r.group:
        text += f" _(group{f', any {r.min_required}' if r.min_required else ''})_"
    when = _cell(r.condition_text)
    if r.variant_ids:
        when += " → " + ", ".join(f"`{v}`" for v in r.variant_ids)
        if r.condition_structured is False:
            when += " (partly text only)"
    elif r.condition_text:
        when += " (text only)"
    return (
        f"| ☐ | {r.source_row} | {r.id.rsplit('-', 1)[-1]} | {text} "
        f"| {_cell(r.secured_at)} | {when} | {len(r.flags) or ''} |"
    )


def render_review(seed: Seed) -> str:
    n_flags = sum(
        len(x.flags)
        for x in [*seed.services, *seed.requirements, *seed.steps, *seed.fees]
    )
    lines = [
        "# Seed review checklist",
        "",
        "Generated by `python -m citizengraph.graph.review` from `graph/seed/*.yaml`; do not "
        "edit by hand (a test checks it is in sync). Review each service side by side with the "
        "spreadsheet named in its source line: the **Row** column is the spreadsheet row. "
        "Every record is `needs_review`; the tick boxes are for a working copy, and the durable "
        "record of a check is `review_status: reviewed` in the seed (then regenerate this file).",
        "",
        "How to read it:",
        "",
        "- **Applies when** shows the charter's own wording; `→ dimension:value` marks the "
        "structured variant links; *text only* means no variant could be linked without guessing.",
        "- **Time** keeps the parsed range; day-based times have `day_type: unknown` "
        "(calendar vs working days is not stated). *shared with N* means a merged spreadsheet "
        "cell: the value sits on step N and is counted once.",
        "- **Role** is set only when the charter gives a role title. **Person cell** says what "
        "the sheet had (blank, names only, role title, names + role title); names are never "
        "printed here or shown to citizens.",
        "- **Other agency** marks a step that belongs to another agency (Core 2 must not blame "
        "the LGU for it).",
        "- **⚑** counts review flags; each one is listed under the service's *Review flags* "
        "with a tick box.",
        "",
        f"{len(seed.services)} services · {len(seed.requirements)} requirements · "
        f"{len(seed.steps)} steps · {len(seed.fees)} fees · {len(seed.variants)} variants · "
        f"{n_flags} review flags. Services left out of the seed: see `docs/seed_status.md`.",
        "",
        "| Service | Id | Requirements | Steps | Fees | Flags |",
        "|---|---|---|---|---|---|",
    ]
    for svc in seed.services:
        n_req = sum(r.service_id == svc.id for r in seed.requirements)
        n_step = sum(s.service_id == svc.id for s in seed.steps)
        n_fee = sum(f.service_id == svc.id for f in seed.fees)
        nf = (
            len(svc.flags)
            + sum(len(r.flags) for r in seed.requirements if r.service_id == svc.id)
            + sum(len(s.flags) for s in seed.steps if s.service_id == svc.id)
            + sum(len(f.flags) for f in seed.fees if f.service_id == svc.id)
        )
        lines.append(
            f"| [{svc.charter_ref}](#{_anchor(svc)}) {svc.name} | `{svc.id}` "
            f"| {n_req} | {n_step} | {n_fee} | {nf} |"
        )
    lines += ["", "## Offices and variants", ""]
    for o in seed.offices:
        srcs = ", ".join(f"{_rows(*s.rows)}" for s in o.sources)
        lines.append(f"- Office `{o.id}`: {o.name} (`{o.sources[0].file}`, {srcs})")
        for f in o.flags:
            lines.append(f"  - [ ] `{f.code}`: {f.message}")
    lines += ["", "| Variant | Dimension | Value | Used by |", "|---|---|---|---|"]
    used: dict[str, set[str]] = defaultdict(set)
    svc_ref = {s.id: s.charter_ref for s in seed.services}
    for rec in [*seed.requirements, *seed.fees]:
        for v in rec.variant_ids:
            used[v].add(svc_ref[rec.service_id])
    for v in seed.variants:
        lines.append(
            f"| `{v.id}` | {v.dimension} | {v.value} | {', '.join(sorted(used[v.id])) or '—'} |"
        )
    lines.append("")
    for svc in seed.services:
        lines += _service_section(seed, svc)
    return "\n".join(lines).rstrip() + "\n"


def _anchor(svc: Service) -> str:
    """GitHub-style heading anchor for '## REF: Name'."""
    import re

    heading = f"{svc.charter_ref}: {svc.name}".lower()
    heading = re.sub(r"[^\w\- ]", "", heading, flags=re.UNICODE)
    return heading.replace(" ", "-")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    text = render_review(load_seed(DEFAULT_SEED_DIR))
    if "--check" in args:
        if not REVIEW_PATH.exists() or REVIEW_PATH.read_text(encoding="utf-8") != text:
            print("docs/seed_review.md is out of date; run python -m citizengraph.graph.review")
            return 1
        return 0
    REVIEW_PATH.write_text(text, encoding="utf-8")
    print(f"wrote {REVIEW_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
