# Charter data notes

Read this when working on the parser, `graph/seed/*.yaml`, the loader, or anything that depends on charter content.

The source spreadsheets are human-formatted documents, not tables. Workflow: a parser produces a rough draft, then the team **hand-curates** `graph/seed/*.yaml`, which becomes the source of truth. Never edit `data/raw/`.

## 1. Sources

| File | Office | Sheet | Services | Source URL | Retrieved |
|---|---|---|---|---|---|
| `data/raw/BPLO-CC.xlsx` | Business Permits & Licensing Office (BPLO), Calbayog City | `BPLO` (~165 rows) | 7 | not recorded (calbayog.gov.ph; add the exact URL) | not recorded |
| `data/raw/LCRO-CC.xlsx` | Civil Registry Office (LCRO), Calbayog City | `CRO` (~421 rows) | 17 | not recorded (calbayog.gov.ph; add the exact URL) | not recorded |
| `data/raw/CYPCC_HEALTH.xlsx` | City Health Office (CHO), Calbayog City | `HEALTH` (195 rows) | 15 | https://calbayog.gov.ph/wp-content/uploads/2025/10/CYPCC_HEALTH.xlsx | 2026-09-30 |
| `data/raw/CYPCC_SOCIALWELFARE.xlsx` | City Social Welfare and Development Office (CSWDO), Calbayog City | `CSWDO` (38 rows) | 1 | https://calbayog.gov.ph/wp-content/uploads/2025/10/CYPCC_SOCIALWELFARE.xlsx | 2026-09-30 |

The BPLO and LCRO files were received before this table recorded URLs and dates; fill in the two "not recorded" cells rather than guessing. The site refused an automated fetch (HTTP 403), so the two new URLs are as given by the team and have not been re-checked by a script.

### Scope

Four offices, **40 services**: BPLO 7, Civil Registry (LCRO) 17, CSWDO 1, CHO 15. Row and service counts for CHO and CSWDO were counted from the files on 2026-09-30. The CSWDO sheet holds a single service ("Referrals"); its numbered lines 1 to 5 are the requirements checklist, not further services.

Each service block has: name, office, classification (SIMPLE/COMPLEX), transaction type, who may avail, a requirements checklist with "where to secure", a steps table (citizen step, agency action, fees, processing time, person responsible), and a stated TOTAL (fees and time).

## 2. Mapping to Chapter 1 domains

| Chapter 1 domain | Charter services |
|---|---|
| Business permit | BPLO 1 (Business Permit, new and renewal) |
| Birth certificate | LCRO 1 (timely registration), 2 (delayed registration), 9 (certified transcript), 17 (BREQS / PSA copies), 8 (endorsement to PSA) |
| Marriage certificate | LCRO 3 (marriage license), 4 (timely registration), 5 (delayed registration) |
| Healthcare eligibility | CHO charter received (15 services, listed below). Which of them count as "eligibility" for Chapter 1 is not decided; adviser to confirm. CSWDO 1 (Referrals) may also be relevant. |

Chapter 1 says "issuance"; the charters mostly describe *registration*, with issuance appearing in LCRO 9 and 17. Adviser to confirm. Recommendation: load all services from all four offices (cheap), and report metrics per domain.

### BPLO services (7)
1 Business Permit, 2 Occupational Permit, 3 Special Mayor's Permit (Streamers & Tarpaulins), 4 Product Promotion & Peddlers, 5 Cockfight Permit, 6 Indigency Certification, 7 Fishing Permits. All SIMPLE.

### LCRO services (17)
Classification and stated totals (fee / time), in charter order:

| # | Service | Class | Total fee | Total time |
|---|---|---|---|---|
| 1 | Birth registration (timely) | SIMPLE | none | 38 min |
| 2 | Birth registration (delayed) | COMPLEX | none | 10 days, 33 min |
| 3 | Marriage license application | SIMPLE | P300 | 1 h 6 min |
| 4 | Marriage registration (timely) | SIMPLE | none | 31 min |
| 5 | Marriage registration (delayed) | COMPLEX | none | 10 days, 28 min |
| 6 | Death registration (timely) | SIMPLE | none | 38 min |
| 7 | Death registration (delayed) | COMPLEX | none | 10 days, 38 min |
| 8 | Electronic endorsement to PSA | SIMPLE | P200 | 36 min |
| 9 | Certified transcript of civil registry documents | SIMPLE | P110 | 28 min |
| 10 | Supplemental report | SIMPLE | P300 | 22 h 51 min |
| 11 | Registration of court order | SIMPLE | P220 (plus local-tax-code fees) | 1 h 14 min |
| 12 | Legitimation | SIMPLE | P580 | 59 min |
| 13 | Affidavit to Use Surname of the Father (AUSF) | SIMPLE | P540 | 1 h 14 min |
| 14 | Other legal instruments | SIMPLE | P300 | 1 h 14 min |
| 15 | Petition for change of first name / clerical error (RA 9048 / 10172) | COMPLEX | P1,000 to P3,000 | 10 days, 1 h 54 min |
| 16 | Facilitate requests and queries | COMPLEX | none | 59 min |
| 17 | BREQS processing (PSA) | SIMPLE | P255 to P295 | 7-10 days, 26 min |

These totals are the charter's own claims. Services 6 to 17 have not been checked line by line yet; the loader must validate them (section 4).

### CHO services (15)
Sheet `HEALTH`, office "City Health Office". All are classified Simple in the sheet. Names are as written there (typos included):
1 Routine Immunization, 2 Pre-Natal Consultation, 3 Family Planning, 4 TB/HPN/Filariasis/Schstosomiasis/Leprosy treatment, 5 Nutrition Center Services, 6 Laboratory Services, 7 Pharmacy Services, 8 Issuance of Death Certificate, 9 Issuance of permit to transfer cadaver, 10 Issuance of Sanitary Permit, 11 Dental Services, 12 The Out-Patient/Animal Bite Center services, 13 Post-Mortem examination, 14 Medico-Legal Consultation, 15 Issuance of Medial Certificates for employment.

### CSWDO services (1)
Sheet `CSWDO`, office "City Social Welfare Development Office". 1 Referrals: classified Complex, who may avail "General Public", stated total "1 week, 1 hour, 40 minutes". Requirements: Barangay certification as to residence (Brgy Hall), certification from the City Assessor's Office that the client owns no real property, certification from BPLO that the client has no existing business, medical abstract, death certificate.

## 3. Parsing rules

- **Durations** appear as minutes, hours, days, ranges and combinations: `10 minutes`, `3 hours`, `10 days`, `7 - 10 days`, `1 hour and 6 minutes`, `1 hours, 14 minutes` (grammar varies), `10 days, 33 minutes`. `- - -` or blank means not stated. Parse to `{value_min, value_max, unit}` per component and also a derived `minutes_min/minutes_max` (for benchmarking only). Day-based durations have `day_type` = unknown by default (see open issue below).
- **Fees** appear as `none`, `- - -`, single amounts, ranges, `per copy`, per-cock or per-category tiers, and multi-item lists inside one cell. Model as fee rows with `amount_min/amount_max`, `unit`, `label` and optional variant conditions. Fee lines can exist without a time.
- **Requirements** are lettered (A to L) or numbered with sub-items (6.1, 6.2, 6.3). Some say "any 2 documents" or "any two documentary evidence": store `min_required` on the group. Many are conditional ("if the child was born illegitimate", "if a parent is a foreigner", "for foreigners", "if applicable", "for marital minors"). Store structured conditions as `Variant` links, and keep the original condition text in `condition_text` for anything not yet structured. Hand-curate all of these.
- **Where to secure** can be missing (LCRO 3, requirement 2 "Birth Certificate") or shared across lines. Store null; do not guess.
- **Who may avail** is blank for BPLO 3 to 7. Store null.
- **Steps** can have multiple agency actions (1.1, 1.2 ...) inside one citizen step, and some steps belong to another agency (Treasurer's Office payment, POPCOM/CHO/CSWDO seminar, PSA issuance). Mark such steps `external_agency` so Core 2 does not blame the LGU for them.
- **Staff names** ("person responsible") are stored as `Role` (e.g. "City Civil Registrar", "BPLO Chief", "authorized CTO collector"). Names may be kept in a non-exposed property and must never appear in citizen-facing text.
- **Currency** uses the peso sign; store numbers, not strings.

## 4. Loader validation (required)

The loader must, for every service, compare the stated TOTAL against the sum of the parsed step fees and times (taking the max of ranges) and write every mismatch to `docs/charter_data.md` section 5 (or a generated report). Do not auto-correct.

## 5. Known data issues (confirm with the LGU; do not silently fix)

BPLO:
- Streamers & Tarpaulins states a total of P215/P310, identical to the Occupational Permit, while the fee step says "as determined by the CSWMO". Likely copy-paste.
- Indigency Certification states 16 minutes but its steps sum to 13.
- Fishing Permits list no fees (assessed by the City Agriculture Office); total time 25 min matches the upper bounds.
- Business Permit requirements 4 and 5 are merged-cell text; "Corporation: CDA" almost certainly means Cooperative.
- Fee variants: Occupational tax P120 (company) vs P215 (individual); cockfight fees by category (MD P1,000/cock, Derby P1,500/cock, 2C P3,000, 3C P4,500, 4C P6,000, 5C P7,500).

LCRO:
- Posting steps of "10 days" (delayed birth, marriage and death registration; petition under RA 9048/10172) and PSA issuance of "7 - 10 days" are not specified as calendar or working days.
- The 10-day posting step exceeds the usual working-day limits, even for services classed COMPLEX. Ask how the statutory cap treats legally required posting periods.
- Marriage license: step 5.3 "Posting of Notice of Marriage" has no time; step 5.2 has no responsible person; the seminar step (3 hours) belongs to POPCOM/CHO/CSWDO.
- Requirement 2 (Birth Certificate) in the marriage license checklist has no "where to secure"; requirement 6 has nested sub-items 6.1 to 6.3 with different applicant conditions (Filipino vs foreigner).
- Service 11 has a long free-text list of local-tax-code fees (annulment P500, adoption P500, judicial correction P200, guardianship/custody P200, and more); hand-curate from the spreadsheet, since the list is long.
- Service 15 has two fee variants (clerical error P1,000; change of first name P3,000) but a single range total.
- Grammar in durations ("1 hours") is inconsistent; the parser must tolerate it.

Add a dated line under each issue when the LGU or adviser resolves it.
