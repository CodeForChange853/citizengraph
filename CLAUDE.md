# CLAUDE.md — CITIZEN GRAPH

Thesis system for Calbayog City (Samar) LGU. Read this at the start of every session. Detailed specs live in `docs/`; read the relevant file **only when your task needs it** (do not read them all).

## What it is

A dual-core neuro-symbolic system that fights the *pabalik-balik* (back-and-forth) problem in LGU frontline services:

- **Core 1, Pre-Screening Assistant:** a QLoRA-fine-tuned SLM acts only as a semantic parser: citizen question -> read-only Cypher -> Neo4j -> requirement checklist. Facts are retrieved, never generated.
- **Core 2, SLA Agent:** a ReAct agent with read-only tools that checks workflow timestamps against charter and statutory (RA 11032) timelines and drafts alerts.

Runs fully local/offline on modest LGU hardware. No cloud API at runtime.

## Non-negotiable rules

1. **Read-only.** Never mutate the official graph. Every Cypher goes through the guardrail, then a read transaction.
2. **Retrieved, not generated.** Fees, requirements, steps, offices and times shown to citizens come from graph rows. Surrounding sentences come from templates.
3. **Exact things are plain code.** Date/working-day math, fee totals and deadline checks are deterministic tools, never model output.
4. **No real citizen data.** Workflow data is simulated. Staff names in the charters are never shown to citizens (use roles).
5. **No LLM-generated training data.** Training data comes from our own code (templates, rules, noise injection). Do not call Claude or any LLM API to write examples (terms question unresolved).
6. **Held-out set is off limits.** The 150 real inquiries in `eval/heldout/` are never used to train, tune templates or write few-shot examples. Generators must not read that folder.
7. **Don't guess data.** If the charter is ambiguous, stop and log it in `docs/charter_data.md` (issues section). Never invent fees, requirements or times.
8. **Don't fake language.** Filipino wording is unverified until a native speaker reviews it; mark with `# NEEDS-NATIVE-REVIEW`. Waray is out of scope.
9. **Tests need no GPU, model file or network.** Use `FakeLLM` and an in-memory graph fixture. Mark real-Neo4j or real-model tests `@pytest.mark.integration`.

## Data status (see `docs/charter_data.md`)

| Domain in Chapter 1 | Source | Status |
|---|---|---|
| Business permits | `data/raw/BPLO-CC.xlsx` (BPLO, 7 services) | received |
| Birth and marriage certificates | `data/raw/LCRO-CC.xlsx` (Civil Registry, 17 services) | received |
| Healthcare eligibility | City Health Office (or the office the adviser confirms) | **pending; do not invent** |

Build the loader and schema office-agnostic so a new office is data, not code.

## Architecture (one screen)

```
message (EN/FIL/mixed) -> spam gate -> normalizer -> alias linker -> intent + splitter
  -> clarify? -> Core 1 (model -> guardrail -> Neo4j)  or  Core 2 (ReAct over read-only tools)
  -> composer (EN/FIL templates) -> reply
```

- The model never sees raw unbounded citizen text: it gets a short controlled prompt (instruction + schema slice for the linked service + 2 to 3 examples + slot-filled request), well under 1,000 tokens, context 2,048.
- Inference is stateless. Session state (resolved service, pending clarification) lives in code.
- Multi-request messages are split into sub-requests, answered one by one, merged, shared documents shown once.
- The EN/FIL toggle controls reply and UI language only; input may be EN, FIL or mixed.
- Only the deterministic front end and the tools are exact; the model handles phrasing variety (Core 1) and next-tool choice (Core 2).

Details: `docs/specs.md` (graph schema, Core 1, Core 2, guardrail, gateway, evaluation map).

## Repo layout

```
CLAUDE.md  README.md
data/raw/            source charters (do not edit)
docs/                charter_data.md, specs.md, behavior_spec.md, api_contract.md, frontend_stack.md
config/              sla.yaml, calendar.yaml, limits.yaml
graph/               schema.cypher, seed/*.yaml (curated), load.py
src/citizengraph/    gateway/ core1/ guardrail/ core2/ composer/ llm/ api/
training/            data generator, noise injection, QLoRA notebook
eval/                harness, baselines, test sets (heldout/ off limits)
benchmarks/  tests/  frontend/ (built later against the API only)
```

## Stack

Python 3.11+, FastAPI, Pydantic v2, `neo4j` driver, `rapidfuzz`, `pytest`, `ruff`, type hints everywhere. Inference via llama.cpp or Ollama behind an `LLMClient` interface (GGUF Q4_K_M). Config in YAML; no secrets in the repo.

**Training does not happen here.** QLoRA runs on a free notebook GPU (Kaggle/Colab); the team's machines have no CUDA. This repo holds only the dataset generator and the notebook. Use fp16. Primary base model: Llama-3-8B-Instruct (as approved); a 3B to 4B fallback may be added after adviser approval. Benchmarks target CPU/integrated graphics, 16 GB RAM; report exact hardware.

## How to work

- Read or write the test cases before the module. Done = named tests pass, `ruff` clean, docs updated if a decision changed.
- One module per session. Plan first for anything bigger than one file and show the plan.
- Keep `docs/api_contract.md` and the mock `/chat` endpoint current so the frontend is never blocked.
- Commit early. Never commit real data, weights or `.env`.
- Behavior-test categories: clear request (EN/FIL/mixed), misspelled, multi-request, ambiguous, out-of-scope, mutation/injection, status question, long noisy message with buried request, gibberish, repeated spam.

## Open questions (update when resolved)

1. Healthcare-eligibility charter: which office, and who collects it?
2. Chapter 1 says birth/marriage "issuance"; the charter has registration services plus certified-copy and PSA services. Confirm which count as the thesis services (mapping in `docs/charter_data.md`).
3. RA 11032 statutory limits: verify tiers, and how they interact with legally required posting periods (e.g. the 10-day posting step in COMPLEX services).
4. Anthropic terms on fine-tuning with Claude-derived data (avoided by rule 5).
5. Native-speaker reviewer for Filipino templates; final base model and licence check.
6. Source-data errors to confirm with the LGU (list in `docs/charter_data.md`).

## Decisions log

- **2026-09-30 (session 2, parsers).** Code in `src/citizengraph/parsing/`; run `python -m citizengraph.parsing` to regenerate `graph/seed/draft/` (24 drafts, `validation_report.md`, `parse_flags.md`, `README.md` with new data findings). Design choices:
  - **Durations.** Parsed per component `{value_min, value_max, unit}` with status `stated | not_stated | unparsed`; blank or `- - -` is `not_stated`; anything not understood is `unparsed` and kept raw, never guessed. `day_type` is always `unknown`. The derived `minutes_min/max` counts a day as 1,440 min and is for benchmarking only; validation compares days and clock minutes on separate axes and never converts days.
  - **Fees.** Statuses `none | not_stated | amounts | text_only`. Ranges, `per copy` / `/ cock` units, labelled multi-item cells and `(company)`-style qualifiers become fee items; `/ fixed` becomes a note. `*ALL FEES MUST BE SETTLED AT THE CTO*` is a note, not a fee. Text with no amount ("As determined by the CSWMO") stays `text_only`, never a number.
  - **Merged cells.** A cell merged over several rows holds its value on the top-left step only, so shared times and fees are counted once (this reproduces the charters' own totals, e.g. Occupational Permit 13 min). Non-summable merged values (person responsible, where to secure) are copied to each row and flagged.
  - **Drafts.** One YAML per service, `draft_id = <office>-<sheet service number>` (not a final graph id). Blocks are found by header anchors, not row numbers. Requirements stay flat (`parent_ref` for `6.1` under `6` and bullets under headings); `min_required`, `condition_text`, `Variant` and `external_agency` are left for hand-curation. Staff names are kept only as `person_responsible_raw` (non-exposed; curate into `Role`).
  - **Validation.** Report only, nothing auto-corrected. Compares the max of each range against the stated total's max. A total with labelled tiers (cockfight) is compared item by item; a total with qualifiers (company/individual) is compared per qualifier; a per-unit fee counts as one unit. When a stated range is reachable as a subset sum of the step fees, a hint (not a verdict change) says the steps may list alternatives. Result: 11 of 24 services have a mismatch (3 fee, 9 time); BPLO 7 fee is not comparable (nothing stated).
  - **Where ambiguities are logged.** This session was scoped away from `docs/`, so new data issues are in `graph/seed/draft/README.md` and `parse_flags.md`. Next session: fold them into `docs/charter_data.md` section 5. Two claims there need correcting: BPLO 5 has a "who may avail" text, and LCRO 3 requirement 2 shares a merged "where to secure" cell.
