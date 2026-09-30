# Seed status

What is in `graph/seed/`, what is not, and what must happen before citizens see any of it. Companion to `docs/seed_review.md` (the per-service checklist to review against the spreadsheets) and `graph/seed/draft/validation_report.md` (why some services were held back).

## Scope rule

Session 3 curated the 13 BPLO and LCRO services whose stated TOTAL agrees with the parsed steps (no fee or time mismatch in `validation_report.md`); 11 were left out. Session 3b added the City Health Office and CSWDO: CSWDO-01 and 12 of the 15 CHO services, including CHO-10 (Sanitary Permit) although its total conflicts with its steps (see below). CHO-04, 05 and 06 stay drafts. In all, 26 of 40 services are in and 14 are out. Nothing was auto-corrected, and nothing in the seed was guessed: blanks are `null` with a review flag. Every record is `review_status: needs_review`.

Totals: 4 offices, 26 services, 74 requirements, 133 steps, 37 fees, 15 variants, 9 cross-office links, 201 review flags on services, requirements, steps and fees (offices and links carry more).

## Included (26)

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
| CSWDO-01 | `cswdo_referrals` | 0 | Classified Complex (confirm). Four referral destinations sit in one cell, kept as written. "1 week" has no day type. Monthly monitoring step kept as the charter states it. Requirement 3 asks BPLO for a certification no BPLO service issues. Requirements 4 and 5 have no place to secure them. |
| CHO-01 | `cho_routine_immunization` | 0 | N/A checklist (no requirement rows). Total fee not stated. |
| CHO-02 | `cho_prenatal_consultation` | 0 | N/A checklist. Total fee not stated. |
| CHO-03 | `cho_family_planning` | 0 | N/A checklist. Total fee not stated. |
| CHO-07 | `cho_pharmacy_services` | 0 | N/A checklist. Total fee not stated. |
| CHO-08 | `cho_death_certificate` | 0 | N/A checklist. Step 1 starts from a certificate issued by the LCR (LCRO-06/07); not linked (step text, not a checklist). Two cells hold two actions on one line. |
| CHO-09 | `cho_cadaver_transfer_permit` | 0 | "Who may avail" is the Sanitary Permit text, a copy-paste error; kept and flagged. |
| CHO-10 | `cho_sanitary_permit` | 0 | **Stated total (20 min) conflicts with the steps (5 min + 3 days + 5 min); the stated total is not stored** (`total_time_text` is null) and must not be used to answer "how long". The only checklist item, "Application Form", has no place to secure it. Target of the suggested BPLO-01 link. |
| CHO-11 | `cho_dental_services` | 1 | The fee "250" has no peso sign and no unit, and the TOTAL row states no fee. |
| CHO-12 | `cho_animal_bite_center` | 0 | N/A checklist. Total fee not stated. |
| CHO-13 | `cho_post_mortem_examination` | 0 | One requirement: a request from the Philippine National Police. |
| CHO-14 | `cho_medico_legal_consultation` | 0 | "Report made and signed." (row 180) is glued to step 2; it may be a separate step. |
| CHO-15 | `cho_medical_certificate` | 1 | Fee ₱30 matches the total. Billing is "at the treasurer’s office" inside step 1; no separate payment step, so `external_agency` is left null. Name reads "Medial" (kept). Target of the suggested BPLO-02 link. |

## Excluded (14)

Left out because the charter's stated total disagrees with its own steps, or its times are ambiguous. They stay as drafts in `graph/seed/draft/`. Each needs an LGU answer (or an explicit decision to load it with the problem flagged) first.

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
| CHO-04 | TB/HPN/Filariasis/Schstosomiasis/Leprosy treatment | **Ambiguous time.** Step 2 is written "1.15  min", which could be 1 h 15 min or 1.15 minutes; nothing is converted. The stated total is 1 hour 30 min against a 10-minute step 1. Awaiting the LGU. |
| CHO-05 | Nutrition Center Services | **Time mismatch.** Stated 35 min, steps add up to 34 (2 + 30 + 2). Also "who may avail" reads "Clients requiring blood transfusion", which looks wrong. |
| CHO-06 | Laboratory Services | **Conflicting and typo'd time.** The total is typed "3 dsys" (read as 3 days by the parser), the steps add up to 3 days + 7 min, step 1 has no time and step 2 has no person (the step looks split over rows 73 and 74). Awaiting the LGU. |

## Modelling decisions worth a second look

1. **Variants only where the charter is explicit.** Linked: business type (BPLO-01), "for new business" (BPLO-01), company vs individual (BPLO-02), cockfight categories (BPLO-05), marital vs non-marital child (LCRO-01, LCRO-02), foreign parent (LCRO-02). Everything else (out-of-town registration, "if deceased", "if married", court-order type, RA 9255, birth before 3 Aug 1988) is `condition_text` with `condition_structured: false` and a flag.
2. **No "cooperative" variant.** The second "Corporation:" heading above the CDA certificate in BPLO-01 is probably Cooperative (`charter_data.md`), but the sheet does not say so. It is kept as text with a flag, so a corporation applicant is currently shown the CDA line as "conditional, unresolved".
3. **"Timely" vs "delayed" is not a variant.** They are separate charter services (LCRO-01 vs 02, and so on), so no within-service condition exists.
4. **Interpreted wording** (flagged `variant_interpretation`): "illegitimate" (LCRO-01) and "marital minors" (LCRO-02) are linked to `birth_status`.
5. **Roles only from charter role titles**, e.g. "BPLO Chief", "Registration Officer", "Any authorized CTO collector". Cells with names only have `role: null` (32 steps; one more step has no person at all). The three ways the charter writes the treasurer's collector stay three separate roles; they are not merged.
6. **Agency names** that differ only in spelling or case were unified (2 cases, flagged `where_to_secure_normalized`), because Agency ids come from names.
7. **Fees are now tied to their step** by a `Step`-`CHARGES`->`Fee` relationship (session 3b), so an unlabeled fee can be read together with its step. 12 fees still have a null label because the fee cell has none.
8. **Shared time cells** (BPLO-02 steps 5 to 7, LCRO-11 steps 2 to 6): the value sits on the first step, the others have no duration and `duration_shared_from`. The graph does not carry that pointer, so Core 2 must read it from the seed until the schema says how. Still open.
9. **Health and social-welfare sheets.** "N/A" checklists are no requirement rows (flag `no_requirements_listed`). Person cells are all role titles and are kept as spelled ("Personnel incharge", "Personel in charge / Emergency Welfare Program implementer"); nothing is merged. Agency-action bullets stay in the text with their "•" and line breaks. Typos are kept and flagged. "None" step fees are no fee rows, and 11 services state no total fee (`total_fee_not_stated`; CHO-11 has its own flag), so "free" is never inferred.
10. **CHO-10's stated total is not stored.** Flag `total_time_conflict` carries the stated "20 min" and the conflict; the answer to "how long" must come from the step times (5 min, 3 days, 5 min on separate axes; the 3 days have no day type).
11. **Cross-office links** (`links.yaml`, 9 records, all `needs_review`): three `requirement_satisfied_by` suggestions (BPLO-01 requirement 7 to CHO-10, BPLO-01 requirement 8 to BPLO-02, BPLO-02 requirement 5 to CHO-15, flag `link_suggested`) and six `agency_is_office` links for agencies whose name is exactly one of the four offices (`BPLO`, `Business Permits and Licensing Office (BPLO)`, `Business Permits & Licensing Office (main office)`, `City Health Office (CHO)`, `City Health Office`, `Civil Registry Office`). The `BPLO` one comes from CSWDO-01 requirement 3 and is flagged `no_bplo_service_issues_this`. Compound or qualified names ("Civil Registry Office / or Notary Public", "Civil Registry Office - Civil Registrar", "One Stop Shop of the BPLO") are not linked. **The loader holds unreviewed links back**; nothing cross-office is in a database until a person sets `review_status: reviewed` (or `--include-suggested-links` is used on a development database).

## Verification done in this session

- `pytest`: seed loads with 0 cross-reference errors; the step times equal the charter's stated total for all 25 services that have a trustworthy total (CHO-10 is the exception, see above), and the fees equal it for every service that has fee rows (tests recompute both from the seed).
- `graph/load.py` is tested through a recording fake driver (statements, batching, idempotent `MERGE`, no staff names, no inlined values) and a dry run.
- **Not run:** the integration tests (`-m integration`) and a real load into Neo4j; this environment has no Neo4j or Docker daemon. Run them against an empty throwaway database before relying on the loader (`tests/test_graph_load_integration.py` documents the variables).

## Next steps

1. Human review of each service against the spreadsheet with `docs/seed_review.md`; set `review_status: reviewed` per record, regenerate the checklist.
2. LGU answers for the excluded services and for the flags marked `suspected_copy_paste`, `heading_maybe_cooperative` and `day_type_unknown`.
3. Decide how shared time cells are represented in the graph schema (`docs/specs.md` and the guardrail schema).
4. Review the nine cross-office links; mark the good ones `reviewed` so the loader writes them.
5. LGU answers for CHO-04, 05 and 06, and the CHO-10 total.
6. Compare `BPLO-CC.xlsx` with the city site's `CYPCC_BPLO.xlsx` (the BPLO data may be outdated, `docs/charter_data.md` section 1).
