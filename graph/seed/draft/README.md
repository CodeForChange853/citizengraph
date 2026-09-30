# Draft seed data (generated, not curated)

Rough per-service drafts produced from `data/raw/BPLO-CC.xlsx` and `data/raw/LCRO-CC.xlsx`.
They are a starting point for hand-curation into `graph/seed/*.yaml`, which stays the source of
truth. Nothing here was corrected, completed or inferred.

Regenerate everything (deterministic, no timestamps; do not hand-edit the generated files):

```
python -m citizengraph.parsing            # reads data/raw, writes graph/seed/draft
```

| File | What it is |
|---|---|
| `BPLO-01.yaml` .. `BPLO-07.yaml`, `LCRO-01.yaml` .. `LCRO-17.yaml` | One draft per service: name, office, classification, who may avail, requirements, steps, flat fee list, stated total. `draft_id` is `<office>-<service number in the sheet>`; it is not a final graph id. |
| `validation_report.md` | Stated TOTAL vs the sum of parsed step fees and times (max of ranges). Lists every mismatch; corrects nothing. |
| `parse_flags.md` | Every blank, merged or non-numeric cell the splitter met. |

Reading a draft:

- `time` and `fees` on each step hold the parsed value plus `raw`. `day_type` is always `unknown`.
- A cell merged over several steps keeps its value on the top-left step (`time_span` /
  `fees_span`); the other rows say `*_shared_from` and carry nothing, so it is counted once.
  A merged *where to secure* value is copied to each row and marked `where_shared_with`.
- `person_responsible_raw` holds the charter's staff names. It is a non-exposed property for
  curation into `Role`; it must never appear in citizen-facing text.
- Requirements are flat: `parent_ref` links `6.1` to `6` and bullets to their heading. `min_required`,
  `condition_text`, `Variant` links and `external_agency` are left for hand-curation.

## Findings from reading the sheets (not yet in `docs/charter_data.md` section 5)

Found while building the splitter. This session was scoped away from `docs/`, so they are
listed here for the next session to fold into section 5. All are for the LGU to confirm.

1. **BPLO 5 (Cockfight)** has "Who may avail" text ("Open to all cockfight enthusiasts").
   Section 3 says it is blank for BPLO 3 to 7; it is blank only for 3, 4, 6 and 7.
2. **LCRO 3, requirement 2 (Birth Certificate)** does have a "where to secure": its cell is
   merged with requirement 1 (`C83:E84`), so it reads "PSA/LCR Calbayog thru BREQS PSA or LCR
   Office". Section 5 says it has none. Requirement 6.3 likewise shares 6.2's merged cell.
   The drafts keep the value and flag it. Confirm whether the merge is intended.
3. **LCRO 6 and 7 (death registration)**: both requirement checklists are the delayed marriage
   registration checklist word for word ("Affidavit of Delayed Registration of Marriage
   certificate", "Marriage Certificate duly signed by the solemnizing officer"), and the
   archiving step in both (LCRO 6 step 2.1, LCRO 7 step 1.8) says "registered marriage
   certificate". Probably copy-paste; real death
   requirements are needed. Nothing was substituted.
4. **Other likely copy-paste text:** LCRO 9 citizen step 1 says "Personally request for
   electronic endorsement" (that is LCRO 8's step); LCRO 13 step 2.1 says "Prepare
   documents for Legitimation" (LCRO 12's step); LCRO 8 "Who may avail" is "Parents or attendant
   at birth" though it covers birth, death and marriage; LCRO 15 "Who may avail" is "Person who
   executed the Legal Instrument".
5. **PSA mailing destination differs between services:** Catbalogan (LCRO 8), Tacloban (LCRO 10,
   12, 13, 14), Manila (LCRO 11, 15, 16).
6. **Stated totals that do not equal the sum of their steps** (details in
   `validation_report.md`; 11 services): BPLO 3 (fee), BPLO 6 (16 vs 13 min), LCRO 3 (66 vs 243
   min), 5 (28 vs 22), 7 (38 vs 43), 8 (36 vs 64), 10 (22 h 51 min vs 169 min), 12 (59 vs 64),
   15 (fee range vs alternatives), 16 (59 vs 89), 17 (fee range; 26 vs 21 min).
   Two observations, unverified: the LCRO 3 sum includes the 3-hour POPCOM/CHO/CSWDO seminar
   (without it the steps total 63 min against the stated 66), and the stated LCRO 17 total of
   26 min is what you get by counting the merged 5-minute cell of step 3.1 twice.
7. **Alternatives drafted as steps.** LCRO 15 steps "2.1 Clerical Error" (P1,000) and "2.2
   Change of First Name" (P3,000), and LCRO 17 sub-items a/b/c (BREQS fee, CENOMAR P195,
   certificate P155), are fee alternatives, not sequential steps. The splitter emits one draft
   step per row, so step counts for these two services are inflated until curated.
8. **LCRO 11 step 2.5** (fees under the local tax code) keeps its long fee list as text in the
   agency-action field; its fee cell is "- - -" and the list is not part of the stated P220.
9. **LCRO 5 (delayed marriage)** has no processing time for steps 1.6, 1.7 and 2; **LCRO 3**
   has none for steps 4 and 5.3 (and no person responsible for 5.2), as already noted in
   section 5.
