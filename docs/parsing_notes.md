# Parsing notes (session 2b: health and social welfare)

Design notes for `src/citizengraph/parsing/`. Session 2 covered BPLO and LCRO (see the decisions
log in `CLAUDE.md`); this session extends the package to the City Health Office and CSWDO
charters. Written as a separate file because `CLAUDE.md` was being edited elsewhere; a
ready-to-paste log entry is at the end.

Regenerate everything (deterministic, no timestamps):

```
python -m citizengraph.parsing
```

It reads the four workbooks named in `parsing/__main__.py` (`WORKBOOKS`; not a glob, so a newer
`CYPCC_BPLO.xlsx` dropped into `data/raw/` is never ingested by accident) and writes:

| Output | Content |
|---|---|
| `graph/seed/draft/<ID>.yaml` | 40 drafts: `BPLO-01..07`, `LCRO-01..17`, `CHO-01..15`, `CSWDO-01` |
| `graph/seed/draft/validation_report.md` | stated TOTAL vs sum of steps, all 40 services |
| `graph/seed/draft/parse_flags.md` | every blank, merged, ambiguous or glued cell |
| `docs/cross_office_links.md` | suggested cross-office references (suggestions only) |

`docs/cross_office_links.md` sits outside the paths listed for this session's edits; it was asked
for by name, so it is a new generated file and nothing existing under `docs/` was changed. It is
trivial to move (`run()` in `__main__.py` takes the directory).

## Regression rule

The 24 BPLO and LCRO drafts regenerate byte-identical. `tests/test_parsing_regression.py`
regenerates them into a temp directory and compares bytes with the committed files, checks that
none of the new optional keys (`agency_action_items`, `normalizations`, `review`, status
`ambiguous`) appear in them, and checks that every committed generated file (drafts, reports,
cross-office doc) matches a fresh run. Rule for future changes: new keys are emitted only when
they have a value, so old drafts keep their shape.

## Layouts

The CHO and CSWDO sheets differ from BPLO/LCRO, so the splitter no longer assumes fixed columns.

- **Blocks** are found from the `CHECKLIST OF REQUIREMENT(S)` header row, walking back over the
  metadata rows (`Office/Section`, `Office or Department`, `Classification`, `Type of Transaction`,
  `Who may avail`, and the old `Name of frontline service`) to the `N. Title` row above them.
  The old code anchored on `Name of frontline service:`, which the new sheets do not have. When
  there is no such row, the service name is the title text after `N.` (for example
  `Routine Immunization`); typos in it are kept.
- **Metadata values** are the first non-empty cell to the right of the label (column B in the old
  sheets, D in the new ones). `Who may avail` is long free text and is stored as is.
- **Step columns** (client step, agency action, fees, time, person) and the `WHERE TO SECURE`
  column are read from their header cells. CHO uses C, F, H, J; CSWDO uses C, F, G, I. The
  `TOTAL` label may be in column A (CHO) or E (CSWDO); it is any cell left of the fees column
  that reads exactly `TOTAL`.
- **Draft ids**: `CHO-NN` and `CSWDO-NN` come from `FILE_OFFICE_CODES` in `splitter.py`
  (`CYPCC_HEALTH` and `CYPCC_SOCIALWELFARE` do not start with the office code). `NN` is the
  number in the sheet.
- **Whitespace** in every cell is normalised (runs of spaces and tabs collapse to one). So the
  sheet's `1.15  min` is stored as `1.15 min`; the row number is in the flag.

## Durations

- New units: `week` (`week(s)`, `wk(s)`), `min/s` as minutes, and the existing `min`, `mins`.
  `3 days`, `2-3 days` and `1 week, 1 hour, 40 minutes` parse as components.
- **Weeks are their own axis.** A week is not turned into 7 days or 5 working days, because
  `day_type` is unknown. Validation compares weeks, days and clock minutes separately. Only the
  benchmark-only `minutes_min/max` counts a week as 7 x 1,440 minutes.
- **Decimals are `ambiguous`**, never converted: `1.15 min` could be 1 h 15 min or 1.15 minutes.
  The parse keeps `raw`, has no components, and carries a `review` text. The splitter flags it
  (`time_ambiguous`); validation treats the service's time check as `not comparable` rather than
  guess. Any decimal counts, including `1.5 hours`.
- **Typos are a fixed table**, `_TYPO_UNITS` in `durations.py` (`dsys`, `dys`, `dyas`, all read
  as days). The reading is recorded in `normalizations`, flagged (`time_typo_normalized` /
  `total_time_typo_normalized`) and named in the validation report. Anything else stays
  `unparsed`; add to the table only for unmistakable typos.
- `1 hour (Once a month)`: the parenthetical is dropped from the parse and kept in `raw`.

## Fees

- `None`, `None ` and `none` are all status `none`. `P30.00`, `₱30.00` and `Php 30.00` are the
  same amount.
- A **bare number** (`250`) is an amount with the note `no currency sign in source`, flagged
  (`fee_no_currency_sign`). The unit of the amount (per visit? per tooth?) is not stated in the
  sheet.
- A cell is a bare number only when the whole cell is a number; `250 per session` stays
  `text_only`.

## Cell handling

- **`N/A` checklists** (13 of 15 CHO services) become an empty `requirements` list, flagged
  `no_requirements_listed`. They are not stored as a requirement called "N/A". An `N/A` in
  *where to secure* is stored as null and flagged `where_to_secure_na` (not "missing").
- **Bullets** in an agency-action cell are split into `agency_action_items`; the raw text with
  its bullets stays in `agency_action`. A line without a bullet continues the previous item (a
  soft wrap inside a bullet); a blank line ends the item. Cells without bullets get no list.
- **CSWDO wraps text over rows** (no merged cells: "Present required" / "document"). A row with
  no fee cell and no time cell that follows a step is appended to that step, column by column,
  and flagged `orphan_row_glued`. Where the step's agency action is a bullet list, the appended
  text becomes its own item (CHO 14, "Report made and signed.").
- **A labelled requirement that wraps** onto the next row (CSWDO 2 and 3) is joined when the next
  row has no key, no where-to-secure, is not a bullet or heading, and the earlier text does not
  end in `. : ; ) ? !`. Flagged `requirement_fragment_glued`.
- **A split step is not merged.** CHO 6 (Laboratory Services) has the label and person on row 73
  and the fee and time on row 74. The two rows stay two steps and the service is flagged
  `possible_split_step`. Merging them would be a guess.

## Cross-office references

`crossoffice.py` scans only *where to secure* text for the four offices and their aliases (see the
table at the top of `docs/cross_office_links.md`; acronyms are case-sensitive). The output is a
list of suggestions split into "across offices" (3 today) and "within the same office" (29).

The suggested *service* is deliberately not filled in. A fuzzy name match was tried and gave
misleading answers: "Medical Certificate" (BPLO 2) scored highest against the Death Certificate
service, and "Certification from BPLO ... no existing business" (CSWDO 1) against Indigency
Certification, which `docs/charter_data.md` says no BPLO service issues. The reviewer picks the
target. Mentions inside step text (CHO 8: "death certificate issued by the LCR") are not scanned.

## Validation

Same rules as session 2 (max of ranges, merged cells counted once, tiers and qualifiers compared
per item, subset-sum hint for fee ranges, report only, nothing corrected) plus:

- weeks are a third time axis;
- an `ambiguous` step time makes the time check `not comparable`, with the raw cell and its
  review text in the details;
- a typo reading in the stated total or a step is named in the details.

Result for all 40: 14 services have a mismatch (3 fee, 12 time), unchanged for the first 24. For
the 16 new services:

| Service | Time |
|---|---|
| CHO 5 | mismatch: steps 34 min, stated 35 |
| CHO 6 | mismatch: steps 3 days + 7 min, stated `3 dsys` (3 days) |
| CHO 10 | mismatch: steps 3 days + 10 min, stated 20 min |
| CHO 4 | not comparable: `1.15 min` kept raw |
| CSWDO 1 | match: 30 min + 1 week + 10 min + 1 hour = 1 week, 1 h 40 min |
| other CHO (11 services) | match |

Fees: only CHO 15 states a total fee (₱30.00, matches `P30.00`). The `TOTAL` row of every other
CHO service and of CSWDO 1 has no fee, so fee checks are `not comparable`.

## Data findings from reading the sheets

Not yet in `docs/charter_data.md` section 5 (that file was out of scope this session); for the
LGU to confirm. Items already listed there (CHO 4, 5, 6, 9, 10, 11, checklists, CSWDO 1) are
reproduced by the parsers and not repeated.

1. **CHO 6 (Laboratory Services)**: besides the `dsys` typo, the steps sum to 3 days + 7 minutes
   against a stated 3 days. The first step is split over rows 73 and 74 (see above); row 73 has no
   time.
2. **CHO 14 (Medico-Legal Consultation)**: "Report made and signed." (row 180) is on its own row
   with no step label, fee, time or person. It is attached to step 2 as a list item; it could also
   be a separate step without a time.
3. **CHO 11 (Dental Services)**: the fee "250" is in the step but the `TOTAL` row states no fee, so
   it cannot be validated. The cell also has no unit. The person cell reads "Person responsible /
   Dentist" (row 140), the column heading pasted before the role.
4. **CHO fee totals**: 14 of 15 CHO services have no fee in the `TOTAL` row; only CHO 15 has one.
   Thirteen of the 14 have only `None` step fees; the fourteenth is CHO 11 (250, see above).
5. **CHO 8**: two agency-action cells (rows 101 and 103) hold two actions on one line, separated by
   spaces and not bullets ("... is received  Referred to the MOD", "... receipt  Copy is filed").
   Not split.
6. **CHO 15**: the step says the client is billed "for payment at the treasurer's office"; there is
   no separate payment step. Likely `external_agency` (the Treasurer) when curated.
7. **CSWDO 1**: "Monitoring" takes "1 hour (Once a month)" and is counted once in the stated total
   (30 + 10 + 60 = 100 minutes). For Core 2 it is unclear whether monitoring is part of the
   service time or a recurring follow-up. Also the transaction type reads "Government of Citizen"
   (not "to") and the description has "asssitance"; both kept as written.
8. **BPLO 2 requirement 5, "Medical Certificate"**, is secured at the City Health Office. The CHO
   charter has "Issuance of Medial Certificates for employment" (CHO 15) and a fee of P30.00
   against the BPLO 2 fee "Medical Health P30.00". Whether they are the same service is for the LGU
   to say; not linked.

## Suggested `CLAUDE.md` decisions-log entry

For whoever next edits `CLAUDE.md` (not applied here):

> **2026-09-30 (session 2b, health and social-welfare parsers).** Parsers and splitter extended to
> `CYPCC_HEALTH.xlsx` (CHO 1 to 15) and `CYPCC_SOCIALWELFARE.xlsx` (CSWDO 1); 40 drafts, report and
> `docs/cross_office_links.md` regenerate with `python -m citizengraph.parsing`. Notes in
> `docs/parsing_notes.md`. Choices: weeks are their own time axis (never days); decimals such as
> `1.15 min` are `ambiguous`, kept raw and make that time check `not comparable`; a fixed typo
> table reads `dsys` as days and records it; a bare `250` is an amount flagged as having no peso
> sign; `N/A` checklists are no requirements; bullets become `agency_action_items`; wrapped rows
> are glued and flagged; a split step is flagged, not merged; cross-office links are suggestions
> at office level only, no service is guessed. The 24 BPLO/LCRO drafts stay byte-identical
> (`tests/test_parsing_regression.py`). Result: 14 of 40 services have a mismatch (3 fee, 12 time).
