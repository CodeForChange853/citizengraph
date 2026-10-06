# Seed status

What is in `graph/seed/`, what is not, and what must happen before citizens see any of it. Companion to `docs/seed_review.md` (the per-service checklist to review against the spreadsheets) and `graph/seed/draft/validation_report.md` (why some services were held back).

## Scope rule

Session 3 curated the 13 BPLO and LCRO services whose stated TOTAL agrees with the parsed steps (no fee or time mismatch in `validation_report.md`); 11 were left out. Session 3b added the City Health Office and CSWDO: CSWDO-01 and 12 of the 15 CHO services, including CHO-10 (Sanitary Permit) although its total conflicts with its steps (see below). CHO-04, 05 and 06 stay drafts. In all, 26 of 40 services are in and 14 are out. Nothing was auto-corrected, and nothing in the seed was guessed: blanks are `null` with a review flag. Every record is `review_status: needs_review`.

Totals: 4 offices, 26 services, 74 requirements, 133 steps, 37 fees, 15 variants, 9 cross-office links, 201 review flags on services, requirements, steps and fees (offices and links carry more). By default the loader holds back 5 of the 74 requirements and one "who may avail" text (see "Held back by default").

## Included (26)

| Charter ref | Seed id | Fees | Notes before citizens see it |
|---|---|---|---|
| BPLO-01 | `business_permit` | 4 | Second "Corporation:" heading and its CDA line are not linked to any variant and are **held back by default** (see "Held back by default"). Requirement 4 is one merged cell, not split. Steps 3 and 4 are done by CTO staff but not marked external. The text of step F.4 is cut off in the source (see "Open questions for the LGU"). Step 10 is nearly empty. |
| BPLO-02 | `occupational_permit` | 5 | Occupational Tax by `taxpayer` (company ₱120, individual ₱215). |
| BPLO-04 | `product_promotion_peddlers` | 2 | Who may avail is blank. The ₱200 fee has no label in the charter (note "fixed"). |
| BPLO-05 | `cockfight_permit` | 6 | Fees by `cockfight_category` (MD, Derby per cock; 2C to 5C flat). "MD" and "Derby" are not expanded. |
| BPLO-07 | `fishing_permit` | 0 | The charter lists no fees (assessed by the City Agriculture Office). Who may avail is blank. Steps 1 and 2 belong to the City Agriculture Office. |
| LCRO-01 | `birth_registration_timely` | 0 | **The checklist has one conditional item (AUSF) and no unconditional document.** Confirm it is complete. **The whole checklist is held back by default.** |
| LCRO-02 | `birth_registration_delayed` | 0 | 10-day posting step: calendar vs working days unknown; RA 11032 interaction is open. Split lines E, H, K, L into groups. |
| LCRO-04 | `marriage_registration_timely` | 0 | Description gives two periods (15 days with license, 30 days Article 34); not modelled. |
| LCRO-06 | `death_registration_timely` | 0 | **Requirements are the delayed marriage checklist copied word for word; step 2.1 says "marriage certificate".** Do not show to citizens until real requirements arrive. **Both requirement rows are held back by default; step 2.1 is not held back.** |
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
| CHO-09 | `cho_cadaver_transfer_permit` | 0 | N/A checklist. "Who may avail" is the Sanitary Permit text, a copy-paste error; kept and flagged in the seed, and **held back by default** (loaded as null). |
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

## Held back by default

Added 2026-10-05. Some curated records are in the seed but are probably wrong or incomplete in the source charter. They are marked in the seed data (`suspect` and `suspect_reason` on a requirement; `held_back` on a service, with field `requirements` or `who_may_avail`). The existing flags are kept. `graph/load.py` does not write these records unless `--include-suspect-records` is given. Rules: `docs/specs.md` sections 1 and 4.

| Charter ref | Seed id | What is held back | Why | Flag code |
|---|---|---|---|---|
| BPLO-01 | `business_permit` | Two requirement rows: `business_permit-R13` (the heading "Corporation:", row 31) and its child `business_permit-R14` ("CDA Certificate of Registration", row 32). The other 16 requirement rows are loaded. | The sheet repeats the heading "Corporation:" above the CDA certificate. The rows have no variant link, so they would show as applying to every applicant. Who needs the CDA certificate is not confirmed. | `heading_maybe_cooperative` |
| LCRO-01 | `birth_registration_timely` | The whole checklist: its single row `birth_registration_timely-R01` (the AUSF affidavit, row 29). | The checklist has one conditional item and no unconditional document. It may be incomplete. | `checklist_only_conditional` |
| LCRO-06 | `death_registration_timely` | Both requirement rows: `death_registration_timely-R01` (row 156) and `death_registration_timely-R02` (row 157). | The checklist is the delayed marriage registration checklist, word for word. The real death-registration requirements are not known. | `suspected_copy_paste` |
| CHO-09 | `cho_cadaver_transfer_permit` | The "who may avail" text. It is loaded as null (the property is absent). | The cell holds the Sanitary Permit text (business owners seeking business permits). | `who_may_avail_suspected_copy_paste` |

In all: 4 services, 5 requirement rows and 1 "who may avail" text. The numbers come from `python graph/load.py --dry-run`, which also prints each held-back record with its reason.

What the loader does with them:

- A held-back requirement is not written. Its child requirements and every relationship that touches them are not written either. A group that loses one part is held back whole (the heading and all its parts).
- A held-back "who may avail" is written as null.
- Steps are never held back.
- Each service in the table gets `info_status = "pending_lgu"`. No other service gets the property.
- The markers and the reasons are never written to Neo4j.
- With `--include-suspect-records` nothing is held back and no service gets `info_status`. Use it only on a development database.

### Services that show `pending_lgu` by default

1. `business_permit` (BPLO-01)
2. `birth_registration_timely` (LCRO-01)
3. `death_registration_timely` (LCRO-06)
4. `cho_cadaver_transfer_permit` (CHO-09)

**This list includes `business_permit`.** Without the hold-back, every business-permit applicant would have been shown the CDA certificate line as if it applied to everyone (the only condition text is "Corporation:" and there is no variant link). Now no applicant sees the CDA line, and the service is marked as waiting for the LGU.

To decide (not decided here): the API contract says a `pending_lgu` service is sent with no checklist, no fees, no steps and no numbers (`docs/api_contract.md`). For `business_permit` that rule would also hide the 16 requirement rows that are not suspect. The team must choose between showing nothing and showing the partial list with a clear notice. See "Note for Session 7".

### Gateway `withheld_services`

`config/limits.yaml` still has `gateway.withheld_services: [death_registration_timely]`. It is kept as a second layer of defence. The rule goes one way only: every withheld service must also be held back by the loader. A held-back service does not have to be withheld (three of the four above are not).

### Caveat: the loader never deletes

`graph/load.py` only adds and updates. A database that was loaded earlier with the suspect records (before 2026-10-05, or with `--include-suspect-records`) still has those nodes after a new default load. Load into an empty database.

## Open questions for the LGU

These need an answer from the LGU. Until then the records in questions 1 to 4 stay held back, and the rest stay open.

1. **LCRO-06, death registration (timely).** What is the real requirements checklist? The charter shows the delayed marriage checklist (rows 156 to 157).
2. **LCRO-01, birth registration (timely).** Is the checklist complete? It lists only the AUSF affidavit, for a child "born illegitimate" (row 29).
3. **CHO-09, permit to transfer cadaver.** What is the correct "who may avail" text? The cell holds the Sanitary Permit text.
4. **BPLO-01, the second "Corporation:" heading above the CDA certificate (rows 31 to 32).** Does it mean Cooperative? Who must bring the CDA Certificate of Registration?
5. **BPLO-01, step F.4.** The text is cut off in the source: "F.4. Record and release approved Business/Mayor’s" (row 47). What is the full text? The seed record `business_permit-S09` holds the cut-off text and carries no flag for it. It is not held back.
6. **Three steps flagged `suspected_copy_paste`. They are not held back** (steps are never held back), so their text is in the loaded graph as written:
   - `death_registration_timely-S07` (LCRO-06, row 166): the agency action says "registered marriage certificate".
   - `certified_transcription-S01` (LCRO-09, row 221): the citizen step says "Personally request for electronic endorsement", which reads like LCRO-08.
   - `ausf_registration-S03` (LCRO-13, row 320): the agency action says "Prepare documents for Legitimation", which is the wording of LCRO-12.
7. **Ten CHO services flagged `no_requirements_listed`.** Their checklist is "N/A" in the charter, so the seed has no requirement rows for them. They carry the same risk as an emptied checklist: an empty list can read as "no requirements". The LGU should confirm that nothing is required. They are out of scope of the hold-back change, are not held back, and do not get `info_status` for this reason (`cho_cadaver_transfer_permit` has it only because of its "who may avail" text):
   `cho_routine_immunization`, `cho_prenatal_consultation`, `cho_family_planning`, `cho_pharmacy_services`, `cho_death_certificate`, `cho_cadaver_transfer_permit`, `cho_dental_services`, `cho_animal_bite_center`, `cho_medico_legal_consultation`, `cho_medical_certificate`.

### Found by the audit, not held back (to decide)

These are observations for the LGU, not confirmed errors. Each was checked against `graph/seed/services.yaml` on 2026-10-05. None has a flag in the seed, and none is held back. The team should decide whether to flag them, hold them back, or leave them.

- **`cho_medico_legal_consultation` (CHO-14).** Its "who may avail" text is word for word the same as the text of `cho_post_mortem_examination` (CHO-13). Observation only: one of the two may be a copy.
- **`cho_routine_immunization` (CHO-01).** Its "who may avail" text describes the service ("Vaccination against TB, hepatitis, tetanus, deptheria, measles, flu and pneumonia"), not who may avail. Observation only.
- **`cho_family_planning` (CHO-03).** Its "who may avail" text ends in the middle of a sentence: "This service caters to women of reproductive age who wishes to plan". Observation only: the cell may be cut off.
- **`ausf_registration` (LCRO-13) and `legal_instrument_other` (LCRO-14).** Both say "Person who executed the Legal Instrument mentioned above." The seed record has nothing above this text that it can point to, so a citizen who reads it alone cannot tell which instrument is meant. Observation only: what the sheet means by "above" was not checked against the spreadsheet in this change.

### Coverage: do not claim all 40 services

Only the curated services can be described as covered: 26 of 40 at the last check (2026-10-05). The other 14 are drafts and are not in the graph. Four of the 26 are `pending_lgu` by default. Public text (landing page, slides, thesis abstract) must not say that the system covers all 40 services.

## Note for Session 7 (real composer)

1. The real composer must use `info_status = pending_lgu`, as the mock API already does. In the mock (`src/citizengraph/api/main.py`, `docs/api_contract.md`): a pending service is never introduced with "Here is what you need for ..."; it gets its own lead-in ("This checklist is still being checked with the office."); and the API sends no numbers for it (null summary values, empty checklist, fees and steps).
2. The mock marks only `birth_registration_timely` and `death_registration_timely` as `pending_lgu`. It still marks `business_permit` as `confirmed`, and it has no entry for `cho_cadaver_transfer_permit`. The loader now marks four services. The mock and the contract need a decision for `business_permit` (see "To decide" above) and for a service where only "who may avail" is held back.
3. Reading `info_status` from the graph needs one of two things: a fixed server-side query (plain code, outside the model), or a change to the Core 1 templates. No template reads it today. A template change alters the golden file (`tests/golden/core1_cypher.json`, on branch `chore/claude-setup`) and the training prompt.
4. An empty requirement list must never be shown as "nothing is required" when the service is `pending_lgu`.

## Modelling decisions worth a second look

1. **Variants only where the charter is explicit.** Linked: business type (BPLO-01), "for new business" (BPLO-01), company vs individual (BPLO-02), cockfight categories (BPLO-05), marital vs non-marital child (LCRO-01, LCRO-02), foreign parent (LCRO-02). Everything else (out-of-town registration, "if deceased", "if married", court-order type, RA 9255, birth before 3 Aug 1988) is `condition_text` with `condition_structured: false` and a flag.
2. **No "cooperative" variant.** The second "Corporation:" heading above the CDA certificate in BPLO-01 is probably Cooperative (`charter_data.md`), but the sheet does not say so. It is kept as text with a flag in the seed. Since 2026-10-05 the heading and the CDA line are marked suspect and held back by default, so no applicant is shown the CDA line until the LGU confirms who needs it (see "Held back by default"). Before that, every applicant would have been shown it as "conditional, unresolved".
3. **"Timely" vs "delayed" is not a variant.** They are separate charter services (LCRO-01 vs 02, and so on), so no within-service condition exists.
4. **Interpreted wording** (flagged `variant_interpretation`): "illegitimate" (LCRO-01) and "marital minors" (LCRO-02) are linked to `birth_status`.
5. **Roles only from charter role titles**, e.g. "BPLO Chief", "Registration Officer", "Any authorized CTO collector". Cells with names only have `role: null` (32 steps; one more step has no person at all). The three ways the charter writes the treasurer's collector stay three separate roles; they are not merged.
6. **Agency names** that differ only in spelling or case were unified (2 cases, flagged `where_to_secure_normalized`), because Agency ids come from names.
7. **Fees are now tied to their step** by a `Step`-`CHARGES`->`Fee` relationship (session 3b), so an unlabeled fee can be read together with its step. 12 fees still have a null label because the fee cell has none.
8. **Shared time cells** (BPLO-02 steps 5 to 7, LCRO-11 steps 2 to 6): the value sits on the first step, the others have no duration and `duration_shared_from`. The graph does not carry that pointer, so Core 2 must read it from the seed until the schema says how. Still open.
9. **Health and social-welfare sheets.** "N/A" checklists are no requirement rows (flag `no_requirements_listed`). Person cells are all role titles and are kept as spelled ("Personnel incharge", "Personel in charge / Emergency Welfare Program implementer"); nothing is merged. Agency-action bullets stay in the text with their "•" and line breaks. Typos are kept and flagged. "None" step fees are no fee rows, and 11 services state no total fee (`total_fee_not_stated`; CHO-11 has its own flag), so "free" is never inferred.
10. **CHO-10's stated total is not stored.** Flag `total_time_conflict` carries the stated "20 min" and the conflict; the answer to "how long" must come from the step times (5 min, 3 days, 5 min on separate axes; the 3 days have no day type).
11. **Cross-office links** (`links.yaml`, 9 records, all `needs_review`): three `requirement_satisfied_by` suggestions (BPLO-01 requirement 7 to CHO-10, BPLO-01 requirement 8 to BPLO-02, BPLO-02 requirement 5 to CHO-15, flag `link_suggested`) and six `agency_is_office` links for agencies whose name is exactly one of the four offices (`BPLO`, `Business Permits and Licensing Office (BPLO)`, `Business Permits & Licensing Office (main office)`, `City Health Office (CHO)`, `City Health Office`, `Civil Registry Office`). The `BPLO` one (`link-04`) comes from CSWDO-01 requirement 3 and is flagged `link_suggested` and `no_bplo_service_issues_this`, so four links carry `link_suggested`, not three. Compound or qualified names ("Civil Registry Office / or Notary Public", "Civil Registry Office - Civil Registrar", "One Stop Shop of the BPLO") are not linked. **The loader holds unreviewed links back**; nothing cross-office is in a database until a person sets `review_status: reviewed` (or `--include-suggested-links` is used on a development database). The hold-back of suspect records (2026-10-05) does not change this: none of the nine links names a held-back requirement.

## Verification done in this session

- `pytest`: seed loads with 0 cross-reference errors; the step times equal the charter's stated total for all 25 services that have a trustworthy total (CHO-10 is the exception, see above), and the fees equal it for every service that has fee rows (tests recompute both from the seed).
- `graph/load.py` is tested through a recording fake driver (statements, batching, idempotent `MERGE`, no staff names, no inlined values) and a dry run.
- **Not run:** the integration tests (`-m integration`) and a real load into Neo4j; this environment has no Neo4j or Docker daemon. Run them against an empty throwaway database before relying on the loader (`tests/test_graph_load_integration.py` documents the variables).

### Hold-back change (2026-10-05)

- `python graph/load.py --dry-run` reports: the seed is valid (4 offices, 26 services, 74 requirements, 133 steps, 37 fees, 15 variants), 9 suggested links held back, 5 suspect requirements held back in 4 services, 4 services marked `pending_lgu`.
- After the documentation update, the three test files that read these docs passed: `tests/test_graph_schema_alignment.py`, `tests/test_graph_seed_data.py`, `tests/test_guardrail_fails_closed.py`.
- **Not verified:** the loader, with or without the hold-back, has not been run against a real Neo4j. The integration tests are still not run in this environment. Nobody has yet checked in a real database that the held-back nodes are absent and that `info_status` is set.

## Next steps

1. Human review of each service against the spreadsheet with `docs/seed_review.md`; set `review_status: reviewed` per record, regenerate the checklist.
2. LGU answers for the excluded services, for the flags marked `suspected_copy_paste`, `heading_maybe_cooperative` and `day_type_unknown`, and for the list in "Open questions for the LGU". When the LGU confirms a held-back record, correct the seed record and remove its marker (`suspect` or `held_back`); the loader then writes it, and the service loses `pending_lgu` once no held-back item is left.
3. Decide how shared time cells are represented in the graph schema (`docs/specs.md` and the guardrail schema).
4. Review the nine cross-office links; mark the good ones `reviewed` so the loader writes them.
5. LGU answers for CHO-04, 05 and 06, and the CHO-10 total.
6. Compare `BPLO-CC.xlsx` with the city site's `CYPCC_BPLO.xlsx` (the BPLO data may be outdated, `docs/charter_data.md` section 1).
7. Run the loader and the integration tests against an empty throwaway Neo4j, and check that the held-back records are absent and the four services have `info_status`. Do not reuse a database that was loaded before 2026-10-05.
8. Decide the items in "Found by the audit, not held back (to decide)" and how a `pending_lgu` service with a partly good checklist (`business_permit`) is shown.
9. Session 7: make the real composer use `info_status` (see "Note for Session 7").
