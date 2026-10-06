# Technical specs

Read the section you need; you rarely need all of it.

## 1. Graph schema (Neo4j)

Keep it small and stable: Cypher generation quality depends on it. Office-agnostic: every Service belongs to an Office.

Nodes:

- `Office {id, name}`
- `Service {id, name, classification, transaction_type, who_may_avail, total_fee_text, total_time_text, description, info_status}` (`info_status` is optional: it is present only with the value `"pending_lgu"`, on a service that has held-back items; see below)
- `Requirement {id, text, group, parent_id, min_required, condition_text}`
- `Agency {id, name}` (where a requirement is secured)
- `Step {id, order, citizen_action, agency_action, external_agency, dur_min, dur_max, dur_unit, minutes_min, minutes_max, day_type}`
- `Role {id, title}`
- `Fee {id, label, amount_min, amount_max, unit, note, condition_text}`
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
(Step)-[:CHARGES]->(Fee)
(Fee)-[:APPLIES_WHEN]->(Variant)
(Requirement)-[:SATISFIED_BY]->(Service)
(Agency)-[:IS_OFFICE]->(Office)
(Service|Requirement|Agency|Office)-[:KNOWN_AS]->(Alias)
```

`CHARGES` ties a fee row to the step where it is paid (`HAS_FEE` from the service stays, so both routes work). `SATISFIED_BY` says a requirement is obtained by using another charter service (for example a business-permit requirement that is the output of the Sanitary Permit service); `IS_OFFICE` marks an Agency whose name is exactly one of the four scoped offices (BPLO, LCRO, CHO, CSWDO). Both are cross-office links that start as suggestions in the seed (`links.yaml`, flag `link_suggested`); the loader writes them only once a person has marked them `reviewed` (or with an explicit switch), so unreviewed suggestions never reach the graph Core 1 reads.

**Suspect records are held back too (2026-10-05).** Some curated records can be loaded but are probably wrong or incomplete in the source charter (for example a checklist copied from another service). The seed marks them as data, not code: `suspect` with a `suspect_reason` on a requirement, and `held_back` entries on a service (field `requirements` for a whole checklist that is untrusted or incomplete, or field `who_may_avail`). By default the loader:

- does not write a held-back requirement, its child requirements, or any relationship that touches them. A group that loses one part is held back whole (the heading and its other parts), so a "any N of" rule never counts a missing part;
- writes a held-back `who_may_avail` as null (the property is absent);
- sets `info_status = "pending_lgu"` on every service that has such an item. No other service has the property, so after a default load into an empty database a missing `info_status` means nothing was held back for that service.

Steps are never held back. The markers and their reasons stay in the seed and are never written to Neo4j; `info_status` is the only trace in the graph. The switch `--include-suspect-records` writes everything and sets no `info_status` (for development databases). The current list of held-back records is in `docs/seed_status.md` ("Held back by default"). The loader only adds and updates, it never deletes: a database that was loaded with these records earlier (before this rule, or with the switch) keeps them, so load into an empty database.

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
- has a node pattern without a label (the one exception is a bare variable already bound with a label earlier in scope, e.g. `(f)` after `(f:Fee)`), or a relationship pattern without a type (`[r]`, `[]`, `--`, `-->`, `<--`), or a negated label or type (`:!X`), anywhere, including inside `WHERE`, `EXISTS` and `COUNT`. This keeps queries such as `MATCH (n) RETURN n` and `MATCH ()-[r]->() RETURN r` inside the official charter graph;
- is longer than `core1.cypher_max_chars` in `config/limits.yaml` (2000);
- hides keywords via case changes, comments (`//`, `/* */`), string concatenation, Unicode homoglyphs, or backtick-quoted identifiers;
- contains a backslash-u escape (`\uXXXX`, `\UXXXXXXXX`) anywhere, including inside a string or a comment. A parser that expands such escapes before it tokenizes would see an escaped quote end a string, or an escaped newline end a comment, where the guardrail saw only data;
- lets a node, relationship or path leave the query whole, or uses one as a value: `RETURN s`, `RETURN *`, `collect(s)`, `RETURN p`, `[s]`, `{k: s}`, `nodes(p)`, `toString(s)`, a pattern as a value (`RETURN (s)-[:T]->(:X)`). A whole entity carries every stored property, the bookkeeping ones included, so the property allow-list would not hold. A pattern variable, or an alias of one (`WITH s AS t`), may appear only before `.property`, as the variable of a pattern, in `count(s)` or `count(DISTINCT s)`, before `IS NULL` / `IS NOT NULL`, in a label test `s:Label`, before a map projection `s {.name}`, and as a whole `WITH` item. `WITH *` is allowed; it only passes variables on;
- uses a name that is not bound (not a pattern variable, an alias, or the variable of a list comprehension, a quantifier or `reduce`);
- names a variable or an alias like a keyword (any case: `by`, `limit`, `in`, `as`, `where`, `unwind`, ...) or like a schema label, relationship type or property (exact case: `name`, `id`, `text`, `Service`). The guardrail reads such a word as syntax or as a map key while the database reads a variable (`by['review_status']`, `WHERE info_status:Application` inside `EXISTS { }`);
- uses `IS` with anything but `NULL` or `NOT NULL` (`x IS Label`, `(x IS %)`, `IS :: TYPE`, `IS NORMALIZED`);
- has a relationship that is not one hop written `-[:TYPE]->`, `<-[:TYPE]-` or `-[:TYPE]-` (a variable, alternatives `A|B` and a property map are fine): variable length (`[:T*]`, `[:T*1..3]`), quantifiers (`->+`, `->*`, `->{1,3}`, `((a)-[:T]->(b))+`), an inline `WHERE`, a parenthesized path pattern, or a link without a bracket (`(a)-(b)`, `(a)->(b)`);
- puts anything in a `MATCH` clause other than node and relationship patterns, commas and `name = (...)`: path selectors and match modes (`ANY SHORTEST`, `REPEATABLE ELEMENTS`), `shortestPath(...)`;
- uses a pattern outside `MATCH` and subqueries other than as a predicate (after `WHERE`, `AND`, `OR`, `XOR`, `NOT`) or as the source of a pattern comprehension, or introduces a variable in such a predicate.

Core 1 must write queries accordingly: return properties (`RETURN s.id, s.name`), never the node; give aliases names that are neither keywords nor schema words (`AS sid`, not `AS id`); use `EXISTS { MATCH ... }` when a predicate needs a new variable. The 38 canonical queries and the training gold queries already do (`tests/test_core1_golden.py`, `tests/test_guardrail_entities_and_names.py`).

The `{` of `EXISTS`, `COUNT` and `COLLECT` is a subquery, not a map: a label test inside it is checked as a label. Inside a real map a `:` must follow a key, and a key must follow `{` or `,`. A `[` directly after `)`, `]`, `}` or a name is a subscript and is rejected; after `BY` it is a list only in `ORDER BY`.

The property allow-list is the union of the node properties in section 1 and nothing else. The loader also stores bookkeeping properties (`review_status`, `source_sheet`, `source_row`, `source_rows`, `charter_ref`, `key`, `condition_structured`); they are **deliberately not on the allow-list**, so Core 1 cannot read them. It does not need them: it can read `condition_text` (on requirements and fees) and follow `APPLIES_WHEN` to the variant links, and a condition that could not be structured comes back as its `condition_text` and is shown as written. `tests/test_graph_schema_alignment.py` fails if this section, the allow-list, the loader and the seed drift apart.

**`info_status` is readable (decision, 2026-10-05).** `info_status` on `Service` is the one property added to the allow-list for the hold-back of suspect records (section 1). Reason: when a requirement or a `who_may_avail` text is held back, a query returns fewer rows, or none. That must not be read as "nothing is required". Core 1, or a fixed server-side query, must be able to tell an incomplete answer from an empty one, so the status has to be readable. Its only value is `"pending_lgu"`. The suspect markers themselves (`suspect`, `suspect_reason`, `held_back`) are not bookkeeping properties: they are not stored in Neo4j at all, so they are not on the allow-list and cannot be read. No Core 1 template reads `info_status` yet, so the prompts and the canonical Cypher are unchanged; only the schema fingerprint line in `training/DATASET_CARD.md` changed.

Use a real tokenizer that handles string literals and comments, not a regex on raw text. Validate with `EXPLAIN` when Neo4j is available. **Not verified against a database (no Neo4j in the test environment):** whether Neo4j expands backslash-u escapes before parsing, which keywords it accepts as variable names, and that it refuses the forms the guardrail leaves to it (for example a map projection on a path). The rules above do not depend on the answers: they reject on the guardrail's side. Always execute with read transactions (`session.execute_read`). Where the edition supports roles, also use a read-only user (Neo4j Community has no RBAC, so guardrail plus read transactions are the defense). This module gets the largest test suite in the repo.

**The guardrail does not stop expensive but read-only queries.** Examples: `UNWIND range(...)` range bombs, `reduce()`, cartesian products (several disconnected `MATCH` patterns) and regex backtracking. Neo4j must therefore run with a transaction timeout and a per-transaction memory limit (Neo4j 5 settings `db.transaction.timeout` and `db.memory.transaction.max`; confirm the names against the installed version), and the driver call in the future executor must pass its own timeout (in the Python driver, decorate the transaction function passed to `session.execute_read` with `neo4j.unit_of_work(timeout=...)`), so a query that slips through is cut off on both sides. Variable-length and quantified paths are rejected (above), so they are no longer on this list. The `cypher_max_chars` cap limits how large a query can be, not how much work it does.

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
