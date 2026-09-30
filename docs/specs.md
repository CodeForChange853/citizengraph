# Technical specs

Read the section you need; you rarely need all of it.

## 1. Graph schema (Neo4j)

Keep it small and stable: Cypher generation quality depends on it. Office-agnostic: every Service belongs to an Office.

Nodes:

- `Office {id, name}`
- `Service {id, name, classification, transaction_type, who_may_avail, total_fee_text, total_time_text, description}`
- `Requirement {id, text, group, parent_id, min_required, condition_text}`
- `Agency {id, name}` (where a requirement is secured)
- `Step {id, order, citizen_action, agency_action, external_agency, dur_min, dur_max, dur_unit, minutes_min, minutes_max, day_type}`
- `Role {id, title}`
- `Fee {id, label, amount_min, amount_max, unit, note}`
- `Variant {id, dimension, value}` (e.g. applicant_type new|renewal; business_type single_proprietor|corporation|association|cooperative; taxpayer company|individual; cockfight_category MD|Derby|2C..5C; birth_status marital|non_marital; foreign_parent yes|no; applicant_nationality filipino|foreigner)
- `Alias {text, lang}` (lang en|fil)

Relationships:

```
(Office)-[:OFFERS]->(Service)
(Service)-[:REQUIRES]->(Requirement)
(Requirement)-[:SECURED_AT]->(Agency)
(Requirement)-[:APPLIES_WHEN]->(Variant)
(Requirement)-[:PART_OF]->(Requirement)
(Service)-[:HAS_STEP]->(Step)
(Step)-[:NEXT]->(Step)
(Step)-[:PERFORMED_BY]->(Role)
(Service)-[:HAS_FEE]->(Fee)
(Fee)-[:APPLIES_WHEN]->(Variant)
(Service|Requirement|Agency|Office)-[:KNOWN_AS]->(Alias)
```

Simulated workflow data for Core 2 uses separate labels or a separate database, never mixed into the official charter graph:

```
(Application {id, service_id, submitted_at})-[:AT_STEP {entered_at, completed_at}]->(Step)
```

Alerts go to a **separate store** (SQLite or JSONL), not the official graph, so alerting never contradicts the read-only claim.

`day_type` is `working | calendar | unknown`. Default `unknown` until the LGU resolves it (see `docs/charter_data.md`).

## 2. Core 1: Pre-Screening Assistant

- Input: slot-filled request, e.g. `service=birth_registration_delayed, intent=requirements, variants={foreign_parent: yes}` plus the cleaned citizen phrase.
- Output: **one** read-only Cypher query, with grammar-constrained decoding (llama.cpp GBNF) where possible.
- Intents: `requirements`, `fees`, `steps`, `processing_time`, `where_to_secure`, `who_may_avail`, `office`.
- Retry: on guardrail or Neo4j error, send back only the failed query and the error text; maximum 2 to 3 attempts; then use a parameterized fallback template.
- Ambiguity (new vs renewal, timely vs delayed, marital vs non-marital) triggers a clarifying question from templates, not a model guess.
- Refuse out-of-scope requests and anything asking to modify records.
- Evaluate three configurations: model only, templates only, hybrid.

## 3. Core 2: SLA Agent

Tools (read-only, plain Python, typed, docstrings): `get_applications(ref)`, `get_workflow_state(app_id)`, `get_step_sla(service_id, step_id)`, `working_days_elapsed(start, end)`, `check_work_suspension(date)`, `get_step_roles(step_id)`, `list_overdue(office_id)`, `draft_alert(app_id, kind)`.

Agent loop:

- The **model chooses** the next tool, its arguments, and when to stop. Tool calls are schema-validated and grammar-constrained so the model cannot invent a tool or malformed arguments.
- Hard step cap (default 8); on cap, return a safe fallback ("please check with the office") and log the trace.
- Tool outputs are compact (limit rows, drop unused fields).
- Log every trajectory (thought, action, observation) as JSONL.

SLA logic uses two clocks:

1. **Charter step time**, normalized from minutes/hours/days.
2. **Statutory cap** in working days from receipt (RA 11032), from `config/sla.yaml`. **Verify against the text of RA 11032 before hardcoding.** SIMPLE and COMPLEX services have different caps; confirm the values and how legally required posting periods count.

Working days exclude weekends, holidays and declared work suspensions (`config/calendar.yaml`). Steps marked `external_agency` (Treasurer's payment, PSA issuance, POPCOM/CHO/CSWDO seminar) are reported as external waiting, not as LGU delay.

Good scenario sources: BPLO permit steps that wait on a signatory; LCRO 10-day posting period (delayed registrations, RA 9048/10172 petition); PSA 7 to 10 day issuance; missing timestamps; several applications for one citizen.

The "isn't this just if-else?" answer: exactness is delegated to tools; control flow is chosen by the model at runtime. Build a rule-based baseline agent and show where it breaks on messy cases (absent signatory + suspension + missing timestamp).

## 4. Guardrail (`src/citizengraph/guardrail/`)

Reject any generated Cypher that:

- contains mutating or unsafe clauses: `CREATE, MERGE, SET, DELETE, DETACH, REMOVE, DROP, FOREACH, LOAD CSV, CALL` (deny all `CALL`, including `apoc.*`, unless explicitly allow-listed), or `;`;
- uses a clause outside the allow-list: `MATCH, OPTIONAL MATCH, WHERE, WITH, RETURN, ORDER BY, LIMIT, SKIP, UNWIND`;
- lacks `LIMIT` or exceeds the maximum;
- references labels, relationship types or properties outside the schema;
- hides keywords via case changes, comments (`//`, `/* */`), string concatenation, Unicode homoglyphs, or backtick-quoted identifiers.

Use a real tokenizer that handles string literals and comments, not a regex on raw text. Validate with `EXPLAIN` when Neo4j is available. Always execute with read transactions (`session.execute_read`). Where the edition supports roles, also use a read-only user (Neo4j Community has no RBAC, so guardrail plus read transactions are the defense). This module gets the largest test suite in the repo.

## 5. Gateway and language handling

- **Spam gate:** hard length cap (start at 500 chars, tune), per-session rate limit, gibberish score (low lexicon-match ratio, character repetition, repeated identical messages). Suspicious text never reaches the model.
- **Normalizer:** lowercase, collapse repeated letters, expand SMS shortcuts, fuzzy-match tokens to the lexicon (`rapidfuzz` plus a phonetic-variant table).
- **Alias linker:** scans the whole capped text, so a real request buried at the end of a noisy message is still found. For long or noisy input, echo the understood service for confirmation before answering.
- **Splitter:** one sub-request per (service, intent); answers merged, shared documents shown once.
- **Alias table** (`graph/seed/aliases.yaml`): EN and FIL names for every service, document and office; editable by LGU staff without retraining.
- **Composer:** `composer/templates/en.yaml` and `fil.yaml`; short sentences, numbered lists, plain vocabulary (elementary to high-school reading level); slots filled from graph rows only.
- **Context budget:** count tokens before each model call; trim in order: examples, extra schema, then truncate the citizen phrase.

## 6. Evaluation map

| Research question | Measure |
|---|---|
| RQ1 hallucination vs vector-RAG | Exact-match accuracy vs charter on the 150 held-out inquiries; vector-RAG baseline |
| RQ2 Cypher validity | Syntactic validity and execution success before/after guardrail and retry; model-only vs templates-only vs hybrid |
| RQ3 Core 2 accuracy | Tool-selection accuracy, argument correctness, trajectory success, steps to completion, false/missed alert rate; vs rule-based baseline |
| RQ4 footprint | Per-stage latency (ms), peak RAM (GB), latency vs input length, max prompt tokens, on LGU-class hardware |

Also report: accuracy by language condition (EN, FIL, mixed) and by domain/office; accuracy at noise levels (clean, 10%, 30%); multi-request success; adversarial-set rejection and false-rejection rates.

## 7. Out of scope / future work

Waray input and replies (the alias-table design extends to it); writing to official records; payments; live citizen data.
