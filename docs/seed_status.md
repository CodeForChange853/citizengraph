# Seed status

What is in `graph/seed/`, what is not, and what must happen before citizens see any of it. Companion to `docs/seed_review.md` (the per-service checklist to review against the spreadsheets) and `graph/seed/draft/validation_report.md` (why some services were held back).

## Scope rule

Only services whose stated TOTAL agrees with the parsed steps (no fee or time mismatch in `validation_report.md`) were curated. 13 of 24 services are in; 11 are out. Nothing was auto-corrected, and nothing in the seed was guessed: blanks are `null` with a review flag. Every record is `review_status: needs_review`.

Totals: 2 offices, 13 services, 67 requirements, 95 steps, 35 fees, 15 variants, 151 review flags on services, requirements, steps and fees (the offices carry 2 more).

## Included (13)

| Charter ref | Seed id | Fees | Notes before citizens see it |
|---|---|---|---|
| BPLO-01 | `business_permit` | 4 | Second "Corporation:" heading (CDA) is not linked to any variant (see below). Requirement 4 is one merged cell, not split. Steps 3 and 4 are done by CTO staff but not marked external. Step 10 is nearly empty. |
| BPLO-02 | `occupational_permit` | 5 | Occupational Tax by `taxpayer` (company ₱120, individual ₱215). |
| BPLO-04 | `product_promotion_peddlers` | 2 | Who may avail is blank. The ₱200 fee has no label in the charter (note "fixed"). |
| BPLO-05 | `cockfight_permit` | 6 | Fees by `cockfight_category` (MD, Derby per cock; 2C to 5C flat). "MD" and "Derby" are not expanded. |
| BPLO-07 | `fishing_permit` | 0 | The charter lists no fees (assessed by the City Agriculture Office). Who may avail is blank. Steps 1 and 2 belong to the City Agriculture Office. |
| LCRO-01 | `birth_registration_timely` | 0 | **The checklist has one conditional item (AUSF) and no unconditional document.** Confirm it is complete. |
| LCRO-02 | `birth_registration_delayed` | 0 | 10-day posting step: calendar vs working days unknown; RA 11032 interaction is open. Split lines E, H, K, L into groups. |
| LCRO-04 | `marriage_registration_timely` | 0 | Description gives two periods (15 days with license, 30 days Article 34); not modelled. |
| LCRO-06 | `death_registration_timely` | 0 | **Requirements are the delayed marriage checklist copied word for word; step 2.1 says "marriage certificate".** Do not show to citizens until real requirements arrive. |
| LCRO-09 | `certified_transcription` | 3 | Fees have no label of their own; citizen step 1 reads like LCRO-08's ("electronic endorsement"). |
| LCRO-11 | `court_order_registration` | 13 | 4 core fees (₱220 total) plus 9 local-tax-code fees curated from a text cell, marked conditional and outside the stated total. |
| LCRO-13 | `ausf_registration` | 1 | Step 2.1 reads "Prepare documents for Legitimation" (LCRO-12's wording). PSA mailing to Tacloban. |
| LCRO-14 | `legal_instrument_other` | 1 | PSA mailing to Tacloban. |

## Excluded (11)

Left out because the charter's stated total disagrees with its own steps. They stay as drafts in `graph/seed/draft/`. Each needs an LGU answer (or an explicit decision to load it with the mismatch flagged) first.

| Charter ref | Service | Why excluded |
|---|---|---|
| BPLO-03 | Special Mayor’s Permit (Streamers & Tarpaulins) | **Fee mismatch.** Stated ₱215 (company) / ₱310 (individual), identical to the Occupational Permit, but the only fee step says "As determined by the CSWMO" (no amount). Likely copy-paste. Time matches (13 min). |
| BPLO-06 | Indigency Certification | **Time mismatch.** Stated 16 min, steps add up to 13 (step 1 has no time). Fee matches (₱25). |
| LCRO-03 | Application for Marriage License | **Time mismatch.** Stated 66 min, steps add up to 243. The 3-hour POPCOM/CHO/CSWDO seminar step is included; without it the steps total 63 (unverified). Steps 4 and 5.3 have no time. |
| LCRO-05 | Registration of Marriage Certificate (Delayed) | **Time mismatch.** Stated 10 days + 28 min, steps 10 days + 22 min (steps 1.6, 1.7 and 2 have no time). |
| LCRO-07 | Registration of Death Certificate (Delayed) | **Time mismatch.** Stated 10 days + 38 min, steps 10 days + 43 min. Its checklist also looks copied from delayed marriage registration. |
| LCRO-08 | Electronic Endorsement of Birth, Death and Marriage Certificate to PSA | **Time mismatch.** Stated 36 min, steps add up to 64. |
| LCRO-10 | Filing of Supplemental Report | **Time mismatch.** Stated 1371 min (22 h 51 min), steps add up to 169 min. |
| LCRO-12 | Registration of Legal Instruments: Legitimation | **Time mismatch.** Stated 59 min, steps add up to 64. |
| LCRO-15 | Petition for Change of First Name or Correction of Clerical Error (RA 9048 / 10172) | **Fee mismatch.** Stated ₱1,000 to ₱3,000, steps add up to ₱4,000 because the two alternative fees are drafted as sequential steps. Time matches. |
| LCRO-16 | Facilitate Requests/Queries from other CROs, PSA and agencies | **Time mismatch.** Stated 59 min, steps add up to 89. |
| LCRO-17 | BREQS Processing (PSA) | **Fee and time mismatch.** Stated ₱255 to ₱295, steps add up to ₱450 (alternatives drafted as steps); stated 10 days + 26 min, steps 10 days + 21 min. |

## Modelling decisions worth a second look

1. **Variants only where the charter is explicit.** Linked: business type (BPLO-01), "for new business" (BPLO-01), company vs individual (BPLO-02), cockfight categories (BPLO-05), marital vs non-marital child (LCRO-01, LCRO-02), foreign parent (LCRO-02). Everything else (out-of-town registration, "if deceased", "if married", court-order type, RA 9255, birth before 3 Aug 1988) is `condition_text` with `condition_structured: false` and a flag.
2. **No "cooperative" variant.** The second "Corporation:" heading above the CDA certificate in BPLO-01 is probably Cooperative (`charter_data.md`), but the sheet does not say so. It is kept as text with a flag, so a corporation applicant is currently shown the CDA line as "conditional, unresolved".
3. **"Timely" vs "delayed" is not a variant.** They are separate charter services (LCRO-01 vs 02, and so on), so no within-service condition exists.
4. **Interpreted wording** (flagged `variant_interpretation`): "illegitimate" (LCRO-01) and "marital minors" (LCRO-02) are linked to `birth_status`.
5. **Roles only from charter role titles**, e.g. "BPLO Chief", "Registration Officer", "Any authorized CTO collector". Cells with names only have `role: null` (32 steps; one more step has no person at all). The three ways the charter writes the treasurer's collector stay three separate roles; they are not merged.
6. **Agency names** that differ only in spelling or case were unified (2 cases, flagged `where_to_secure_normalized`), because Agency ids come from names.
7. **Fee rows have no link from a Fee to its Step in the graph**, and 10 fees have a null label (the fee cell is unlabeled). The YAML keeps `step_id`; the graph does not (docs/specs.md section 1 has no such relationship). Before fees are shown to citizens, decide whether to add a `Fee`→`Step` link or a label.
8. **Shared time cells** (BPLO-02 steps 5 to 7, LCRO-11 steps 2 to 6): the value sits on the first step, the others have no duration and `duration_shared_from`. The graph does not carry that pointer either, so Core 2 must read it from the seed until the schema says how.

## Verification done in this session

- `pytest`: seed loads with 0 cross-reference errors; the step times equal the charter's stated total for all 13 services, and the fees equal it for every service that has fee rows (tests recompute both from the seed).
- `graph/load.py` is tested through a recording fake driver (statements, batching, idempotent `MERGE`, no staff names, no inlined values) and a dry run.
- **Not run:** the integration tests (`-m integration`) and a real load into Neo4j; this environment has no Neo4j or Docker daemon. Run them against an empty throwaway database before relying on the loader (`tests/test_graph_load_integration.py` documents the variables).

## Next steps

1. Human review of each service against the spreadsheet with `docs/seed_review.md`; set `review_status: reviewed` per record, regenerate the checklist.
2. LGU answers for the excluded services and for the flags marked `suspected_copy_paste`, `heading_maybe_cooperative` and `day_type_unknown`.
3. Decide the Fee→Step and shared-duration representation in the graph schema (needs an edit to `docs/specs.md` and the guardrail schema, outside this session's scope).
