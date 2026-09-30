"""Suggest cross-office references from "where to secure" text.

Whenever a requirement's "where to secure" names one of the four offices in scope (BPLO, City
Health Office, CSWDO, Civil Registry / LCRO) or an alias, the requirement is listed as a
*suggested* reference to that office. Nothing is linked: a person decides whether it is a real
dependency and which service it points to. The target service is deliberately not guessed:
fuzzy name matching was tried and gave misleading answers (a "Medical Certificate" matched the
Death Certificate service; "certification from BPLO" matched Indigency, which no BPLO service
issues).

Only "where to secure" text is scanned. Mentions inside step text (for example CHO 8, "death
certificate issued by the LCR is received") are listed in ``docs/charter_data.md``, not here.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from citizengraph.parsing.splitter import ServiceDraft

# office key -> (display name, [(regex, ignore_case)]). Acronyms are case-sensitive on purpose.
OFFICES: dict[str, tuple[str, list[tuple[str, bool]]]] = {
    "BPLO": (
        "Business Permits & Licensing Office (BPLO)",
        [(r"\bBPLO\b", False), (r"business\s+permits?\s*(?:and|&)\s*licens\w*\s+office", True)],
    ),
    "CHO": (
        "City Health Office (CHO)",
        [(r"\bCHO\b", False), (r"city\s+health\s+office", True)],
    ),
    "CSWDO": (
        "City Social Welfare and Development Office (CSWDO)",
        [
            (r"\bCSWDO\b", False),
            (r"city\s+social\s+welfare(?:\s+(?:and|&))?\s+development", True),
        ],
    ),
    "LCRO": (
        "Civil Registry Office (LCRO)",
        [
            (r"\bLCRO\b", False),
            (r"\bLCR\b", False),
            (r"\bCCRO\b", False),
            (r"\bCRO\b", False),
            (r"civil\s+registry", True),
            (r"civil\s+registrar", True),
        ],
    ),
}

_COMPILED = {
    office: [re.compile(p, re.IGNORECASE if ic else 0) for p, ic in patterns]
    for office, (_, patterns) in OFFICES.items()
}


@dataclass(frozen=True)
class Reference:
    from_id: str
    from_name: str | None
    ref: int
    key: str | None
    requirement: str
    where_text: str
    target_office: str
    matched: str
    same_office: bool
    shared_cell: bool
    source_row: int


def find_office_mentions(text: str | None) -> list[tuple[str, str]]:
    """(office key, matched text) for each scoped office named in ``text``, in order of appearance."""
    if not text:
        return []
    hits: list[tuple[int, str, str]] = []
    for office, patterns in _COMPILED.items():
        first = None
        for pattern in patterns:
            m = pattern.search(text)
            if m and (first is None or m.start() < first[0]):
                first = (m.start(), m.group(0))
        if first:
            hits.append((first[0], office, first[1]))
    return [(office, matched) for _, office, matched in sorted(hits)]


def _source_office(draft: ServiceDraft) -> str:
    return draft.draft_id.split("-")[0]


def find_references(drafts: Sequence[ServiceDraft]) -> list[Reference]:
    out = []
    for draft in drafts:
        source = _source_office(draft)
        for req in draft.requirements:
            for office, matched in find_office_mentions(req.where_to_secure):
                out.append(
                    Reference(
                        from_id=draft.draft_id,
                        from_name=draft.name,
                        ref=req.ref,
                        key=req.key,
                        requirement=req.text,
                        where_text=req.where_to_secure or "",
                        target_office=office,
                        matched=matched,
                        same_office=office == source,
                        shared_cell=req.where_shared_with is not None,
                        source_row=req.source_row,
                    )
                )
    return out


def _cell(text: str, limit: int = 80) -> str:
    text = " ".join(text.split())
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text.replace("|", "\\|")


def _table(refs: Sequence[Reference]) -> list[str]:
    lines = [
        "| From | Requirement | Where to secure (as written) | Suggested office | Matched on | Row | Note |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in refs:
        label = f"{r.key}. " if r.key else ""
        note = "shares a merged cell with the row above" if r.shared_cell else ""
        lines.append(
            f"| {r.from_id} | {_cell(label + r.requirement)} | {_cell(r.where_text)} | "
            f"{r.target_office} | {_cell(r.matched)} | {r.source_row} | {note} |"
        )
    return lines


def build_cross_office_doc(drafts: Sequence[ServiceDraft]) -> str:
    """Markdown list of suggested references. Deterministic (no timestamps)."""
    refs = find_references(drafts)
    cross = [r for r in refs if not r.same_office]
    same = [r for r in refs if r.same_office]
    out = [
        "# Cross-office reference suggestions",
        "",
        "Generated by `python -m citizengraph.parsing`; do not hand-edit, re-generate instead.",
        "",
        (
            'Each row is a **suggestion**: a requirement whose "where to secure" text names one of '
            "the four offices in scope, or an alias of it. **No graph link exists or has been "
            "created.** Matching is by office name only; the target *service* is not guessed (see "
            "`src/citizengraph/parsing/crossoffice.py`). A person decides whether each row is a real "
            "dependency and which service it points to. Offices outside the four (Treasurer, BFP, "
            "CPDO, Assessor, barangay, PNP and so on) are not listed. Mentions inside step text are "
            'not scanned; see the "Cross-office links" list in `docs/charter_data.md`.'
        ),
        "",
        "Offices and aliases matched (acronyms are case-sensitive):",
        "",
        "| Key | Office | Matches |",
        "|---|---|---|",
    ]
    for key, (name, patterns) in OFFICES.items():
        aliases = ", ".join(f"`{p}`" for p, _ in patterns).replace("|", "\\|")
        out.append(f"| {key} | {name} | {aliases} |")
    out += [
        "",
        f"## Across offices ({len(cross)})",
        "",
        *_table(cross),
        "",
        f"## Within the same office ({len(same)})",
        "",
        (
            "A requirement secured at the office that offers the service. Listed because some are "
            "links to another service of the same office (for example BPLO 1 requirement 8 to BPLO 2)."
        ),
        "",
        *_table(same),
    ]
    return "\n".join(out).rstrip() + "\n"
