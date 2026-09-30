# Training notes: Core 1 (Text-to-Cypher)

Session 5 (branch `session5-training-data`). Code: `src/citizengraph/core1/` (`slots.py`,
`templates.py`, `prompt.py`), `training/`, tests `tests/test_core1_*.py` and
`tests/test_training_*.py`. The generated overview with counts is `training/DATASET_CARD.md`;
a reviewable sample is `training/sample/`.

Rules this work follows: no LLM or API wrote any example (templates, rules and noise only);
`eval/heldout/` was never read (a test watches the generator's file access and checks that no
code spells the folder); examples hold questions and Cypher only, no charter answer text; only
the 26 curated services are used (not the 14 drafts); the guardrail was not loosened.

## 1. What is where

| Piece | File | Role |
|---|---|---|
| Slots | `core1/slots.py` | `Slots(service_id, intent, variants, phrase, language)`, the shared vocabulary; `known_variants()` reads `graph/seed/variants.yaml` |
| Templates | `core1/templates.py` | ONE source of canonical read-only Cypher: gold completion, fallback, templates-only baseline |
| Prompt | `core1/prompt.py` | `build_prompt(slots, schema_slice)`: the model input, same format in training and inference |
| Phrases | `training/phrasebook.yaml` | question templates (EN / FIL / Taglish), service and variant wording |
| Noise | `training/noise.py` | typos, dropped vowels, doubled letters, c/k, ph/f, SMS, casing at 0 / 10 / 30 % |
| Generator | `training/generate_dataset.py` | `python -m training.generate_dataset --seed 0` |
| Training | `training/qlora_kaggle.py` | QLoRA notebook cells for a free Kaggle GPU (**untested on a GPU**) |
| Scoring | `training/eval_generate.py` | guardrail-valid rate and exact match against gold |
| Pins | `training/requirements-train.txt` | training-only dependencies (never in `pyproject.toml`) |

## 2. Query shapes (`core1/templates.py`)

The shape is chosen from the citizen's wording; the intent stays one of the seven.

| Intent | Shapes | Variant filter |
|---|---|---|
| requirements | `list`, `count` (leaf requirements, `group = false`) | yes |
| fees | `list`, `per_step` (Step-[:CHARGES]->Fee) | yes |
| steps | `list`, `count` | no (steps carry no variant links) |
| processing_time | `list` (stated total plus one row per step) | no |
| where_to_secure | `list` (requirement + Agency), `go_first` (cross-office: `SATISFIED_BY` to the Service and its Office, and `SECURED_AT` to the Agency and `IS_OFFICE`) | yes |
| who_may_avail | `list` | no |
| office | `list` | no |

`status` is not a Core 1 intent (Core 2); `select_template` raises `NotCore1Intent`. With variants
in the slots, an intent that has no filtered template uses the plain one (the model learns this:
the gold depends on the slots, not on whether the phrase mentions a variant). 11 plain and 6
filtered templates: `TEMPLATES[(intent, shape, filtered)]`.

### Parameter contract

Ids are never in the query text, so the model never reproduces them.

* `$sid`: `Service.id`, e.g. `"business_permit"`. Every template uses it.
* `$variant_ids`: list of `Variant.id` strings `dimension:value` (as in `graph/seed/variants.yaml`),
  e.g. `["business_type:corporation", "applicant_type:new"]`. Only the filtered templates use it
  (at least one id). `Slots.variant_ids` builds it, sorted. `build_query(slots, shape)` returns
  the text and the parameter dict.

### The variant filter

A record is kept unless it links a variant in a dimension the citizen gave (some id of
`$variant_ids` has that dimension) and none of its links in that dimension was asked for. Same
meaning as `InMemoryGraph.requirements/fees`: values in one dimension are alternatives, different
dimensions all must hold, an unknown dimension filters nothing, unlinked records are always kept
(so text-only conditions come back with their `condition_text`). It is a `NOT EXISTS { ... }` with
two nested `EXISTS { MATCH ... WHERE ... }`.

### Guardrail and query-shape decisions

Every template passes `validate_cypher` with the default config (a test enforces it). No shape
was over-rejected, so nothing was changed in the guardrail. Choices made because of its rules:

* every node has a label and every relationship a type; the bare `(r)` is used only after
  `(r:Requirement)` earlier in scope;
* the `EXISTS {}` bodies use `MATCH ... WHERE` with property comparisons only; a bare
  `WHERE x:Label` inside a subquery is avoided (the guardrail over-rejects it);
* `go_first` filters its optional matches with `WITH r, d, o1, a, o2 WHERE ...`; a `WHERE` right
  after `OPTIONAL MATCH` would only filter the optional part;
* row limits: `LIMIT 50` for lists (the configured maximum; a test checks that every seed service
  fits), `LIMIT 1` for counts, who-may-avail and office;
* no `UNION`, `CALL`, parameters in `LIMIT`, `properties()` or subscripts.

Limits of the templates, for the composer and Core 1 code to respect:

* counts count leaf requirements (`group = false`). Groups such as "any two of" (`min_required`)
  and conditions the seed could not structure make the number an upper bound: say so.
* `fees` returns rows only. No total is summed in Cypher (exact sums are a plain-code tool), and
  the stated `total_fee_text` is not returned; `processing_time` does return `total_time_text`
  (null for CHO-10, whose stated total conflicts with its steps: answer from step times).
* `per_step` returns only fees that have a `CHARGES` link (every current fee has one).
* `go_first` needs the cross-office links, which the loader writes only when reviewed (or with
  `--include-suggested-links`); on a database without them it returns nothing.

### The schema is read at runtime

The templates' RETURN columns, the prompt's schema slice and the generator all take the allowed
labels, relationship types and properties from `guardrail/schema.py` at runtime: a property that
disappears from the allow-list disappears from the queries and prompts. A property that is ADDED
needs one edit: say which label owns it in `NODE_PROPERTIES` (`core1/templates.py`; a test fails
with that instruction). Then add it to a template's column list if Core 1 should return it, and
regenerate the dataset (the card shows the schema fingerprint, so a change is visible).

## 3. Prompt (`core1/prompt.py`)

System message: a six-line fixed instruction plus a schema slice that lists only the labels,
properties and relationships the intent's templates use (read from the template text with the
guardrail tokenizer). User message: `service`, `intent`, `variants` (or `none`), `language` and
`request` as one JSON-quoted line, so text inside the phrase cannot fake a slot. There are no
few-shot examples (the model is fine-tuned on this exact format; examples would only spend
context). The phrase is cut at `gateway.max_chars` (500) and further if the prompt would pass the
ceiling.

Token budget: `prompt.max_prompt_tokens` (1,000) in `config/limits.yaml` is a ceiling.
`estimate_tokens` is `ceil(characters / 3)`, never below one per word: no tokenizer or model file
needed, conservative (Llama-3 averages about 4 characters per token in English and about 3 in
Filipino text and Cypher). Measured on the dataset: maximum 345, mean 239 (a test requires under
half the ceiling).

## 4. Dataset design

One example = (service x intent/shape x variant combination) x language x noise level.

* **Cells.** Every curated service x every shape x every combination of the variant values its
  requirements and fees link (one value or none per dimension; 457 cells). List shapes for every
  service; derived shapes only where data exists: `count` for services with a leaf requirement,
  `per_step` for services with a step-linked fee, `go_first` for services whose requirements have
  a `SATISFIED_BY` link or an agency that is one of the offices.
* **Phrases.** `phrasebook.yaml`: 174 families of paraphrases (6 per (intent, list shape,
  language), 4 per derived shape), service names (colloquial names plus the official name from
  `services.yaml`, 15 % of the time), variant wording attached with frames such as "base (variant)"
  (85 % of the time a variant combination is also said in the phrase; otherwise it reaches the
  model only through the slots). `graph/seed/aliases.yaml` is used when that file exists (see
  limits). Language labels: `en`; `fil` (predominantly Filipino; nativized loanwords such as
  "permit" or "requirements" are fine); `mixed` (Taglish).
* **Noise.** 0, 10 and 30 percent of words perturbed (one random operation each: keyboard-adjacent
  typo, dropped vowel(s), doubled letter, c/k swap, ph/f swap, SMS spelling), plus a casing change
  for the whole message with the same probability. Words with digits and ids are left alone.
* **Gold.** The canonical template for the shape the wording asks for, ids as parameters.
* **Size.** Seed 0: 6,987 train, 1,077 validation, 1,130 test_synthetic; generated in about 3 s.
* **Determinism.** All randomness comes from `random.Random` seeded with a string of the example's
  coordinates; same seed, same bytes (a test compares files byte for byte; `\n` newlines on every
  platform).
* **Output.** `training/out/<split>.jsonl` in chat format `{"messages": [system, user, assistant]}`
  and a parallel `<split>.meta.jsonl` (same line order: id, shape, noise, family, clean phrase,
  parameters). `training/out/` is gitignored; `training/sample/` (63 examples) and
  `training/DATASET_CARD.md` are committed and regenerated with the same command.

### Splits

By phrase-template family: in every (intent, shape, language) group one family is in
`test_synthetic`, one in `validation`, the rest in `train`; no family appears in two splits and no
prompt is identical across splits (tests). In addition, some variant combinations (about a third
of the non-empty combinations of services that have at least three) are withheld from train and
appear only in validation and test; the card lists them. Because those cells are always kept,
validation and test contain more variant-bearing examples (about 70 %) than train (about 40 %).

## 5. Known limits

* Filipino and Taglish wording is unreviewed. Waray is out of scope.
* Phrases are short single questions: no multi-request messages, no buried requests, no gibberish,
  no out-of-scope or mutation requests (the front end handles those before the model).
* The wording-to-shape mapping (list vs count vs per_step vs go_first) is what the model must learn;
  it is decided only by our own phrase families, so real citizens will phrase things differently.
  This is what `eval/heldout` will measure; it is not used here.
* Service names in phrases do not change the gold (the query never contains a name or id); they are
  there so the model ignores them.
* The alias file format was not fixed when this was written; `load_aliases` accepts a list or an
  `aliases:` list of records with `text`, `lang` (en|fil) and the service id under `service_id`,
  `target_id`, `target` or `for`, and ignores anything else. When that file appears, the dataset,
  sample and card change: regenerate and re-check the format.
* The sample and card are generated files: regenerate (`python -m training.generate_dataset`) after
  a change to the seed, the schema, the templates or the phrasebook.
* Noise is character-level English/Tagalog-ish; no real misspelling data was used (none may be).

## 6. Verification done

* Unit tests (no GPU, model, network or Neo4j): templates pass the guardrail; parameters are exactly
  `$sid` / `$variant_ids`; the filter's logic restated in Python agrees with `InMemoryGraph` on
  every combination of every dimension for every service; prompts under budget; the full dataset's
  gold passes the guardrail; determinism; splits; no answer text or held-out inquiry inside examples.
* **Real Neo4j (once, here).** `tests/test_core1_templates_integration.py` (marked `integration`)
  passed 9 of 9 against an embedded Neo4j 5.26.12 Community started from the Maven Central jars,
  with the seed loaded through `graph/load.py` (suggested links included): every template
  `EXPLAIN`s, and every template's rows equal the in-memory helpers for every service and every
  variant combination. A naive variant filter made three of the tests fail, so they do detect
  differences. Not run against the Docker image or a server install; rerun on your machine (below).
* Not verified: anything on a GPU (`qlora_kaggle.py`, `eval_generate.py` against a real model).

Side finding (not changed, outside this session's paths): running the existing
`tests/test_graph_load_integration.py` against the same embedded Neo4j gave 4 passed and 1 failed:
`test_no_staff_name_is_stored_anywhere` fails with `CypherTypeError ... toString() ... LongArray`
because the test calls `toString` on a list property (`source_rows`); the loader itself wrote and
reloaded the seed fine.

### Reproducing the real-Neo4j run

```bash
# once: fetch the embedded Neo4j jars (needs Maven and Java 17+)
mvn -q dependency:copy-dependencies -DoutputDirectory=lib   # pom: org.neo4j:neo4j:5.26.12
# a 20-line Serve.java starts DatabaseManagementServiceBuilder with BoltConnector.enabled=true,
# listen_address 127.0.0.1:7687 and GraphDatabaseSettings.auth_enabled=false, on an EMPTY folder
NEO4J_TEST_URI=bolt://127.0.0.1:7687 NEO4J_TEST_USER=neo4j NEO4J_TEST_PASSWORD=x \
  pytest -m integration tests/test_core1_templates_integration.py
```

With the Docker image: `docker compose up -d`, then the same command with your password. The
database must be empty (the test loads the seed, with the suggested links, and only reads).

## 7. Kaggle run instructions

Read the header of `training/qlora_kaggle.py` first: it lists what the first run must check.

1. Locally: `python -m training.generate_dataset --seed 0`; upload `training/out/train.jsonl` and
   `validation.jsonl` (only those two) as a Kaggle Dataset. Never upload `eval/heldout/`.
2. New Kaggle notebook: Accelerator **GPU T4** (a P100 is below Unsloth's minimum compute
   capability; the notebook stops on it), Internet **on**, attach the dataset, add the repo (or
   paste `training/requirements-train.txt` and `training/qlora_kaggle.py`).
3. Model: the default is Unsloth's public 4-bit mirror of Llama-3-8B-Instruct. The original
   `meta-llama/Meta-Llama-3-8B-Instruct` is gated: accept the licence on the model page, add
   `HF_TOKEN` to Kaggle Secrets and change `MODEL_NAME`. Licence review for thesis use is an open
   question (CLAUDE.md, open question 5).
4. Run the cells in order. fp16 only (no bf16 on T4/P100). LoRA r=16 on all seven linear
   projections, training on the assistant answer only, checkpoints and validation loss every 100
   steps into `/kaggle/working/checkpoints`, adapter into `core1-lora/`.
5. Cell 7 (masking check) must show only the Cypher and `<|eot_id|>`. Cell 10 prints exact match
   and guardrail-valid rate on 100 validation examples.
6. Merge (16-bit, into `/tmp`) and GGUF Q4_K_M are separate cells; the GGUF cell needs a 16 GB
   temporary file (the `/kaggle/working` limit is about 20 GB): if it runs out of disk, download
   `core1-lora/` and convert elsewhere.
7. Score offline: `python -m training.eval_generate --data training/out/test_synthetic.jsonl
   --meta training/out/test_synthetic.meta.jsonl --endpoint http://localhost:8080/v1` (llama.cpp
   server or Ollama), or `--outputs outputs.jsonl`.
8. Benchmarks target CPU/integrated graphics with 16 GB RAM: report the exact hardware there.

The pins in `requirements-train.txt` follow the constraints declared by `unsloth==2026.9.12`
(trl <= 0.24.0, transformers <= 5.5.0, datasets < 4.4, peft >= 0.18) and were only checked with
`pip install --dry-run` (they resolve together). torch, xformers and triton are deliberately not
pinned: Kaggle's image carries a matching set.

## 8. Suggested decisions-log entry (CLAUDE.md was not edited, as instructed)

> **Session 5, Core 1 slots, templates, prompt and training data (branch `session5-training-data`).**
> `core1/templates.py` is the single source of canonical read-only Cypher (gold, fallback,
> templates-only baseline); ids are parameters (`$sid`, `$variant_ids`); the variant filter equals
> `InMemoryGraph` semantics and was checked against a real embedded Neo4j 5.26. Shapes: list, count,
> per_step, go_first; steps, times, offices and who-may-avail have no filtered template. The schema is
> read from `guardrail/schema.py` at runtime. `core1/prompt.py` fixes the model input (no few-shot);
> `training/generate_dataset.py` builds 9.2k examples (seed 0) from our own templates, split by
> phrase family with withheld variant combinations. The QLoRA script and `eval_generate` model path
> are untested on a GPU. Filipino wording awaits native review (list in `docs/training_notes.md`).

## 9. Filipino and Taglish strings needing native review (NEEDS-NATIVE-REVIEW)

Every string below is unverified Filipino or Taglish and must be reviewed by a native speaker
before any data trained on it is relied on (CLAUDE.md rule 8). This list is generated; the test
suite fails if it is out of date (`python -m training.generate_dataset --write-review-list
docs/training_notes.md` refreshes it).

<!-- BEGIN REVIEW LIST (generated: python -m training.generate_dataset --write-review-list) -->

1. service name [ausf_registration]: pagpaparehistro ng AUSF
2. service name [ausf_registration]: affidavit para gamitin ang apelyido ng ama
3. service name [birth_registration_delayed]: naantalang pagpaparehistro ng kapanganakan
4. service name [birth_registration_delayed]: late na pagpaparehistro ng birth
5. service name [birth_registration_timely]: pagpaparehistro ng kapanganakan
6. service name [birth_registration_timely]: pagpaparehistro ng birth certificate
7. service name [business_permit]: permit sa negosyo
8. service name [business_permit]: business permit
9. service name [certified_transcription]: certified copy ng dokumento sa civil registry
10. service name [certified_transcription]: sertipikadong kopya ng civil registry
11. service name [cho_animal_bite_center]: serbisyo ng animal bite center
12. service name [cho_animal_bite_center]: gamutan sa kagat ng hayop
13. service name [cho_cadaver_transfer_permit]: permit para ilipat ang bangkay
14. service name [cho_cadaver_transfer_permit]: permit sa paglilipat ng bangkay
15. service name [cho_death_certificate]: death certificate mula sa health office
16. service name [cho_death_certificate]: pagkuha ng death certificate
17. service name [cho_dental_services]: serbisyong dental
18. service name [cho_dental_services]: pagpapagamot ng ngipin
19. service name [cho_family_planning]: family planning
20. service name [cho_family_planning]: pagpaplano ng pamilya
21. service name [cho_medical_certificate]: medical certificate para sa trabaho
22. service name [cho_medical_certificate]: medical certificate para sa pagtatrabaho
23. service name [cho_medico_legal_consultation]: medico-legal na konsultasyon
24. service name [cho_medico_legal_consultation]: medico-legal consultation
25. service name [cho_pharmacy_services]: serbisyo ng botika
26. service name [cho_pharmacy_services]: gamot mula sa botika ng health office
27. service name [cho_post_mortem_examination]: post-mortem examination
28. service name [cho_post_mortem_examination]: pagsusuri sa bangkay
29. service name [cho_prenatal_consultation]: prenatal na konsultasyon
30. service name [cho_prenatal_consultation]: pagpapatingin para sa buntis
31. service name [cho_routine_immunization]: regular na bakuna
32. service name [cho_routine_immunization]: bakuna para sa bata
33. service name [cho_sanitary_permit]: sanitary permit
34. service name [cho_sanitary_permit]: permit pang-sanitasyon
35. service name [cockfight_permit]: permit sa sabong
36. service name [cockfight_permit]: permit para sa sabong
37. service name [court_order_registration]: pagpaparehistro ng court order
38. service name [court_order_registration]: pagpaparehistro ng utos ng korte
39. service name [cswdo_referrals]: referral ng social welfare
40. service name [cswdo_referrals]: referral sa social welfare
41. service name [death_registration_timely]: pagpaparehistro ng pagkamatay
42. service name [death_registration_timely]: pagpaparehistro ng death certificate
43. service name [fishing_permit]: permit sa pangingisda
44. service name [fishing_permit]: fishing permit
45. service name [legal_instrument_other]: pagpaparehistro ng legal instrument
46. service name [legal_instrument_other]: pagpaparehistro ng legal na dokumento
47. service name [marriage_registration_timely]: pagpaparehistro ng kasal
48. service name [marriage_registration_timely]: pagpaparehistro ng marriage certificate
49. service name [occupational_permit]: permit sa pagtatrabaho
50. service name [occupational_permit]: occupational permit
51. service name [product_promotion_peddlers]: permit para sa mga peddler
52. service name [product_promotion_peddlers]: permit sa promosyon ng produkto
53. variant phrase [applicant_type:new]: bagong negosyo
54. variant phrase [applicant_type:new]: bagong aplikasyon
55. variant phrase [birth_status:marital]: magulang na kasal
56. variant phrase [birth_status:marital]: anak ng mag-asawang kasal
57. variant phrase [birth_status:non_marital]: magulang na hindi kasal
58. variant phrase [birth_status:non_marital]: anak ng magulang na hindi kasal
59. variant phrase [business_type:association]: asosasyon
60. variant phrase [business_type:association]: association
61. variant phrase [business_type:corporation]: korporasyon
62. variant phrase [business_type:corporation]: corporation
63. variant phrase [business_type:single_proprietor]: single proprietor
64. variant phrase [business_type:single_proprietor]: sole proprietor
65. variant phrase [cockfight_category:2C]: kategoryang 2C
66. variant phrase [cockfight_category:2C]: 2C
67. variant phrase [cockfight_category:3C]: kategoryang 3C
68. variant phrase [cockfight_category:3C]: 3C
69. variant phrase [cockfight_category:4C]: kategoryang 4C
70. variant phrase [cockfight_category:4C]: 4C
71. variant phrase [cockfight_category:5C]: kategoryang 5C
72. variant phrase [cockfight_category:5C]: 5C
73. variant phrase [cockfight_category:Derby]: kategoryang Derby
74. variant phrase [cockfight_category:Derby]: derby
75. variant phrase [cockfight_category:MD]: kategoryang MD
76. variant phrase [cockfight_category:MD]: MD
77. variant phrase [foreign_parent:yes]: magulang na dayuhan
78. variant phrase [foreign_parent:yes]: may magulang na dayuhan
79. variant phrase [taxpayer:company]: kompanya
80. variant phrase [taxpayer:company]: company
81. variant phrase [taxpayer:individual]: indibidwal
82. variant phrase [taxpayer:individual]: individual
83. variant frame [fil]: {base} ({variant})
84. variant frame [fil]: {base} - {variant}
85. variant frame [fil]: {variant}: {base}
86. variant frame [fil]: {base}, para sa {variant}
87. variant joiner [fil]: ' at '
88. variant joiner [fil]: ', '
89. variant frame [mixed]: {base} ({variant})
90. variant frame [mixed]: {base} - {variant}
91. variant frame [mixed]: {variant}: {base}
92. variant frame [mixed]: {base}, for {variant}
93. variant joiner [mixed]: ' and '
94. variant joiner [mixed]: ' at '
95. variant joiner [mixed]: ', '
96. family fees.list.fil.1: Magkano ang bayad sa {service}?
97. family fees.list.fil.1: Magkano ang bayad para sa {service}?
98. family fees.list.fil.2: Magkano po ang babayaran para sa {service}?
99. family fees.list.fil.2: Magkano po ang babayaran sa {service}?
100. family fees.list.fil.3: Ano ang bayarin sa {service}?
101. family fees.list.fil.3: Ano ang mga bayarin para sa {service}?
102. family fees.list.fil.4: Magkano ang kailangan kong bayaran sa {service}?
103. family fees.list.fil.4: Magkano ang dapat kong bayaran para sa {service}?
104. family fees.list.fil.5: Magkano ang singil sa {service}?
105. family fees.list.fil.5: Magkano ang singil para sa {service}?
106. family fees.list.fil.6: May bayad ba ang {service}, magkano?
107. family fees.list.fil.6: May babayaran ba sa {service}, magkano po?
108. family fees.list.mixed.1: Magkano ang fee for {service}?
109. family fees.list.mixed.1: Magkano po ang fee ng {service}?
110. family fees.list.mixed.2: How much ang babayaran ko sa {service}?
111. family fees.list.mixed.2: How much ang bayad sa {service}?
112. family fees.list.mixed.3: Ano ang fees ng {service}?
113. family fees.list.mixed.3: Ano po ang mga fees for {service}?
114. family fees.list.mixed.4: Magkano po ang payment for {service}?
115. family fees.list.mixed.4: Magkano ang payment sa {service}?
116. family fees.list.mixed.5: May fee ba ang {service}? how much?
117. family fees.list.mixed.5: May fee ba sa {service}, how much po?
118. family fees.list.mixed.6: {service} fee po, magkano?
119. family fees.list.mixed.6: {service} fee, magkano ang babayaran?
120. family fees.per_step.fil.1: Magkano ang babayaran sa bawat hakbang ng {service}?
121. family fees.per_step.fil.1: Magkano ang bayad sa bawat hakbang ng {service}?
122. family fees.per_step.fil.2: Sa aling hakbang ako magbabayad sa {service}, at magkano?
123. family fees.per_step.fil.2: Sa anong hakbang ang bayad sa {service}, at magkano?
124. family fees.per_step.fil.3: Ilang bayad ang mayroon sa bawat hakbang ng {service}?
125. family fees.per_step.fil.3: Mga bayad sa bawat hakbang ng {service}
126. family fees.per_step.fil.4: Ano ang binabayaran sa bawat hakbang ng {service}?
127. family fees.per_step.fil.4: Ano ang mga bayad sa bawat hakbang sa {service}?
128. family fees.per_step.mixed.1: Magkano ang payment sa bawat step ng {service}?
129. family fees.per_step.mixed.1: Magkano ang babayaran sa bawat step ng {service}?
130. family fees.per_step.mixed.2: Saang step ako magbabayad sa {service}, at magkano?
131. family fees.per_step.mixed.2: Sa anong step ang payment ng {service}, magkano?
132. family fees.per_step.mixed.3: May fee ba per step ng {service}? magkano each?
133. family fees.per_step.mixed.3: Fee per step ng {service}, magkano po?
134. family fees.per_step.mixed.4: Ano ang fees sa bawat step ng {service}?
135. family fees.per_step.mixed.4: Ano ang bayad per step sa {service}?
136. family office.list.fil.1: Saang opisina ang {service}?
137. family office.list.fil.1: Saang opisina po ang {service}?
138. family office.list.fil.2: Saan ako pupunta para sa {service}?
139. family office.list.fil.2: Saan po ako pupunta para sa {service}?
140. family office.list.fil.3: Anong opisina ang humahawak ng {service}?
141. family office.list.fil.3: Anong opisina ang nag-aasikaso ng {service}?
142. family office.list.fil.4: Saan po nag-aasikaso ng {service}?
143. family office.list.fil.4: Saan nag-aasikaso ng {service}?
144. family office.list.fil.5: Saan ako mag-aapply ng {service}?
145. family office.list.fil.5: Saan ako pwedeng mag-apply ng {service}?
146. family office.list.fil.6: Anong tanggapan ang may hawak ng {service}?
147. family office.list.fil.6: Anong tanggapan ang nag-aasikaso ng {service}?
148. family office.list.mixed.1: Saang office ang {service}?
149. family office.list.mixed.1: Saang office po ang {service}?
150. family office.list.mixed.2: Which office ang nag-aasikaso ng {service}?
151. family office.list.mixed.2: Which office po ang nag-aasikaso ng {service}?
152. family office.list.mixed.3: Saan ako mag-apply for {service}?
153. family office.list.mixed.3: Saan po ako mag-apply for {service}?
154. family office.list.mixed.4: Anong office ang handle ng {service}?
155. family office.list.mixed.4: Anong office po ang handle ng {service}?
156. family office.list.mixed.5: Saan po ang office para sa {service}?
157. family office.list.mixed.5: Saan ang office para sa {service}?
158. family office.list.mixed.6: Saang department ang {service}?
159. family office.list.mixed.6: Saang department po ang {service}?
160. family processing_time.list.fil.1: Gaano katagal ang {service}?
161. family processing_time.list.fil.1: Gaano po katagal ang {service}?
162. family processing_time.list.fil.2: Ilang araw bago makuha ang {service}?
163. family processing_time.list.fil.2: Ilang araw bago matapos ang {service}?
164. family processing_time.list.fil.3: Gaano katagal ang proseso ng {service}?
165. family processing_time.list.fil.3: Gaano katagal ang proseso sa {service}?
166. family processing_time.list.fil.4: Kailan matatapos ang {service}?
167. family processing_time.list.fil.4: Kailan makukuha ang {service}?
168. family processing_time.list.fil.5: Gaano katagal maghihintay para sa {service}?
169. family processing_time.list.fil.5: Gaano katagal ang paghihintay sa {service}?
170. family processing_time.list.fil.6: Isang araw lang ba o matagal ang {service}?
171. family processing_time.list.fil.6: Mabilis ba o matagal ang {service}?
172. family processing_time.list.mixed.1: How long ang process ng {service}?
173. family processing_time.list.mixed.1: How long po ang process ng {service}?
174. family processing_time.list.mixed.2: Gaano katagal ang processing time ng {service}?
175. family processing_time.list.mixed.2: Gaano katagal ang processing time for {service}?
176. family processing_time.list.mixed.3: Ilang days bago makuha ang {service}?
177. family processing_time.list.mixed.3: Ilang days bago matapos ang {service}?
178. family processing_time.list.mixed.4: Kailan ba ready ang {service}?
179. family processing_time.list.mixed.4: Kailan po ready ang {service}?
180. family processing_time.list.mixed.5: Processing time po ng {service}, gaano katagal?
181. family processing_time.list.mixed.5: Processing time ng {service}, gaano ba katagal?
182. family processing_time.list.mixed.6: Matagal ba ang {service}, how many days?
183. family processing_time.list.mixed.6: Mabilis ba ang {service}, how many days?
184. family requirements.count.fil.1: Ilan ang mga kailangan para sa {service}?
185. family requirements.count.fil.1: Ilan ang mga kailangan sa {service}?
186. family requirements.count.fil.2: Ilang dokumento ang kailangan sa {service}?
187. family requirements.count.fil.2: Ilang dokumento ang kailangan para sa {service}?
188. family requirements.count.fil.3: Ilang papeles ang dadalhin ko para sa {service}?
189. family requirements.count.fil.3: Ilang papeles ang kailangan sa {service}?
190. family requirements.count.fil.4: Ilang requirements ang kailangan sa {service}?
191. family requirements.count.fil.4: Ilang requirements po ang {service}?
192. family requirements.count.mixed.1: Ilan ang requirements for {service}?
193. family requirements.count.mixed.1: Ilan po ang requirements ng {service}?
194. family requirements.count.mixed.2: How many documents ang kailangan sa {service}?
195. family requirements.count.mixed.2: How many papers ang kailangan for {service}?
196. family requirements.count.mixed.3: Ilang requirements po ang needed for {service}?
197. family requirements.count.mixed.3: Ilang documents po ang needed sa {service}?
198. family requirements.count.mixed.4: Ilan ang documents na dadalhin for {service}?
199. family requirements.count.mixed.4: Ilan ang papers na ihahanda for {service}?
200. family requirements.list.fil.1: Ano ang mga requirements para sa {service}?
201. family requirements.list.fil.1: Ano-ano ang mga requirements sa {service}?
202. family requirements.list.fil.2: Anong mga dokumento ang kailangan para sa {service}?
203. family requirements.list.fil.2: Anong dokumento ang kailangan sa {service}?
204. family requirements.list.fil.3: Ano ang dapat kong ihanda para sa {service}?
205. family requirements.list.fil.3: Ano ang dapat kong dalhin para sa {service}?
206. family requirements.list.fil.4: Ano ang mga papeles na kailangan sa {service}?
207. family requirements.list.fil.4: Ano ang mga papeles para sa {service}?
208. family requirements.list.fil.5: Pakisabi po kung ano ang kailangan sa {service}.
209. family requirements.list.fil.5: Pakisabi po ang mga kailangan para sa {service}.
210. family requirements.list.fil.6: Mga kailangan para sa {service}, ano po ba?
211. family requirements.list.fil.6: Mga requirements sa {service}, ano po?
212. family requirements.list.mixed.1: Ano ang requirements for {service}?
213. family requirements.list.mixed.1: Ano po ang requirements for {service}?
214. family requirements.list.mixed.2: What documents ang kailangan for {service}?
215. family requirements.list.mixed.2: What papers ang kailangan sa {service}?
216. family requirements.list.mixed.3: Pwede ba malaman ang requirements ng {service}?
217. family requirements.list.mixed.3: Pwede po bang malaman ang requirements sa {service}?
218. family requirements.list.mixed.4: May checklist ba kayo ng requirements for {service}?
219. family requirements.list.mixed.4: May list ba ng requirements for {service}?
220. family requirements.list.mixed.5: Anong documents ang dadalhin ko for {service}?
221. family requirements.list.mixed.5: Anong papers ang ihahanda ko for {service}?
222. family requirements.list.mixed.6: {service} requirements po, ano ang needed?
223. family requirements.list.mixed.6: {service}, ano ang mga needed documents?
224. family steps.count.fil.1: Ilan ang hakbang sa {service}?
225. family steps.count.fil.1: Ilan ang mga hakbang sa {service}?
226. family steps.count.fil.2: Ilang hakbang ang {service}?
227. family steps.count.fil.2: Ilang hakbang po ang {service}?
228. family steps.count.fil.3: Ilang proseso ang dadaanan sa {service}?
229. family steps.count.fil.3: Ilang proseso ang pagdadaanan sa {service}?
230. family steps.count.fil.4: Ilang hakbang ang kailangang gawin para sa {service}?
231. family steps.count.fil.4: Ilang hakbang ang gagawin ko sa {service}?
232. family steps.count.mixed.1: Ilan ang steps sa {service}?
233. family steps.count.mixed.1: Ilan po ang steps ng {service}?
234. family steps.count.mixed.2: How many steps ang {service}?
235. family steps.count.mixed.2: How many steps po ang {service}?
236. family steps.count.mixed.3: Ilang steps bago makakuha ng {service}?
237. family steps.count.mixed.3: Ilang steps bago matapos ang {service}?
238. family steps.count.mixed.4: Ilan ba ang process steps ng {service}?
239. family steps.count.mixed.4: Ilan ang mga process steps for {service}?
240. family steps.list.fil.1: Ano ang mga hakbang sa {service}?
241. family steps.list.fil.1: Ano ang mga hakbang para sa {service}?
242. family steps.list.fil.2: Paano ang proseso ng {service}?
243. family steps.list.fil.2: Paano po ang proseso sa {service}?
244. family steps.list.fil.3: Paano kumuha ng {service}?
245. family steps.list.fil.3: Paano po kumuha ng {service}?
246. family steps.list.fil.4: Ano ang mga dapat gawin sa {service}, isa-isa?
247. family steps.list.fil.4: Ano ang mga gagawin ko sa {service}, isa-isa?
248. family steps.list.fil.5: Pakipaliwanag po ang proseso ng {service}.
249. family steps.list.fil.5: Pakipaliwanag ang mga hakbang sa {service}.
250. family steps.list.fil.6: Ano ang una kong gagawin sa {service}, at ano ang susunod?
251. family steps.list.fil.6: Ano ang una at susunod na gagawin sa {service}?
252. family steps.list.mixed.1: Ano ang steps for {service}?
253. family steps.list.mixed.1: Ano po ang mga steps sa {service}?
254. family steps.list.mixed.2: Paano ang process ng {service}?
255. family steps.list.mixed.2: Paano po ang process sa {service}?
256. family steps.list.mixed.3: Pa-explain naman ng process for {service}
257. family steps.list.mixed.3: Pa-explain po ng steps sa {service}
258. family steps.list.mixed.4: What are the steps para makakuha ng {service}?
259. family steps.list.mixed.4: What are the steps para sa {service}?
260. family steps.list.mixed.5: Step by step ng {service}, paano?
261. family steps.list.mixed.5: Step by step po ng {service}, paano ba?
262. family steps.list.mixed.6: Ano ang procedure sa {service}?
263. family steps.list.mixed.6: Ano po ang procedure for {service}?
264. family where_to_secure.go_first.fil.1: Saang opisina ako dapat pumunta muna bago ang {service}?
265. family where_to_secure.go_first.fil.1: Saang opisina ako unang pupunta bago ang {service}?
266. family where_to_secure.go_first.fil.2: May kailangan ba akong kunin sa ibang opisina bago ang {service}?
267. family where_to_secure.go_first.fil.2: May kailangan ba akong kunin muna sa ibang opisina para sa {service}?
268. family where_to_secure.go_first.fil.3: Saan ako unang pupunta para sa {service}?
269. family where_to_secure.go_first.fil.3: Saan ako dapat unang pumunta para sa {service}?
270. family where_to_secure.go_first.fil.4: Mayroon bang dapat kunin muna sa ibang opisina para sa {service}?
271. family where_to_secure.go_first.fil.4: Kailangan ko bang pumunta muna sa ibang opisina para sa {service}?
272. family where_to_secure.go_first.mixed.1: Saan ako pupunta first for {service}?
273. family where_to_secure.go_first.mixed.1: Saan po ako pupunta first para sa {service}?
274. family where_to_secure.go_first.mixed.2: May kailangan ba akong kunin sa ibang office before {service}?
275. family where_to_secure.go_first.mixed.2: May kailangan ba akong kunin from another office before {service}?
276. family where_to_secure.go_first.mixed.3: Which office muna ang pupuntahan ko bago ang {service}?
277. family where_to_secure.go_first.mixed.3: Anong office muna ang pupuntahan ko before {service}?
278. family where_to_secure.go_first.mixed.4: May requirement ba from another office para sa {service}?
279. family where_to_secure.go_first.mixed.4: May requirement ba galing sa ibang office para sa {service}?
280. family where_to_secure.list.fil.1: Saan kukunin ang mga requirements para sa {service}?
281. family where_to_secure.list.fil.1: Saan kukunin ang mga requirements sa {service}?
282. family where_to_secure.list.fil.2: Saan ako kukuha ng mga dokumento para sa {service}?
283. family where_to_secure.list.fil.2: Saan ako kukuha ng dokumento sa {service}?
284. family where_to_secure.list.fil.3: Saan makakakuha ng mga papeles para sa {service}?
285. family where_to_secure.list.fil.3: Saan makakakuha ng mga papeles sa {service}?
286. family where_to_secure.list.fil.4: Saan ko makukuha ang mga kailangan sa {service}?
287. family where_to_secure.list.fil.4: Saan ko makukuha ang mga kailangan para sa {service}?
288. family where_to_secure.list.fil.5: Saan po nakukuha ang requirements ng {service}?
289. family where_to_secure.list.fil.5: Saan po nakukuha ang mga dokumento ng {service}?
290. family where_to_secure.list.fil.6: Saang opisina ako kukuha ng dokumento para sa {service}?
291. family where_to_secure.list.fil.6: Saang opisina ako kukuha ng requirements sa {service}?
292. family where_to_secure.list.mixed.1: Saan ko kukunin ang requirements for {service}?
293. family where_to_secure.list.mixed.1: Saan ko kukunin ang documents for {service}?
294. family where_to_secure.list.mixed.2: Where kukuha ng documents for {service}?
295. family where_to_secure.list.mixed.2: Where ako kukuha ng requirements for {service}?
296. family where_to_secure.list.mixed.3: Saan pwede makuha ang requirements ng {service}?
297. family where_to_secure.list.mixed.3: Saan pwede makuha ang documents ng {service}?
298. family where_to_secure.list.mixed.4: Saan ko ma-secure ang documents for {service}?
299. family where_to_secure.list.mixed.4: Saan ko ma-secure ang requirements ng {service}?
300. family where_to_secure.list.mixed.5: Where po makakakuha ng papers para sa {service}?
301. family where_to_secure.list.mixed.5: Where po makukuha ang requirements ng {service}?
302. family where_to_secure.list.mixed.6: Saan nagmumula ang mga documents for {service}?
303. family where_to_secure.list.mixed.6: Saan galing ang mga requirements ng {service}?
304. family who_may_avail.list.fil.1: Sino ang maaaring mag-apply sa {service}?
305. family who_may_avail.list.fil.1: Sino ang maaaring kumuha ng {service}?
306. family who_may_avail.list.fil.2: Sino ang puwedeng kumuha ng {service}?
307. family who_may_avail.list.fil.2: Sino ang puwedeng humingi ng {service}?
308. family who_may_avail.list.fil.3: Sino ang kwalipikado para sa {service}?
309. family who_may_avail.list.fil.3: Sino ang kwalipikado sa {service}?
310. family who_may_avail.list.fil.4: Para kanino ang {service}?
311. family who_may_avail.list.fil.4: Para kanino po ang {service}?
312. family who_may_avail.list.fil.5: Sino ang maaaring humiling ng {service}?
313. family who_may_avail.list.fil.5: Sino ang pinapayagang humiling ng {service}?
314. family who_may_avail.list.fil.6: Maaari ba akong kumuha ng {service}?
315. family who_may_avail.list.fil.6: Puwede ba akong kumuha ng {service}?
316. family who_may_avail.list.mixed.1: Who can avail ng {service}?
317. family who_may_avail.list.mixed.1: Who can avail po ng {service}?
318. family who_may_avail.list.mixed.2: Sino ang eligible sa {service}?
319. family who_may_avail.list.mixed.2: Sino po ang eligible sa {service}?
320. family who_may_avail.list.mixed.3: Pwede ba akong mag-apply for {service}?
321. family who_may_avail.list.mixed.3: Pwede po ba akong mag-apply sa {service}?
322. family who_may_avail.list.mixed.4: Sino ba ang qualified for {service}?
323. family who_may_avail.list.mixed.4: Sino po ang qualified sa {service}?
324. family who_may_avail.list.mixed.5: Open ba sa lahat ang {service}?
325. family who_may_avail.list.mixed.5: Open po ba sa lahat ang {service}?
326. family who_may_avail.list.mixed.6: Sino ang allowed mag-request ng {service}?
327. family who_may_avail.list.mixed.6: Sino ang allowed mag-apply sa {service}?
328. sms spelling: ano -> anu
329. sms spelling: ba -> b
330. sms spelling: bayad -> byad
331. sms spelling: hindi -> di
332. sms spelling: kailangan -> kelangan
333. sms spelling: kasi -> ksi
334. sms spelling: lang -> lng
335. sms spelling: magkano -> mgkano
336. sms spelling: naman -> nmn
337. sms spelling: nasaan -> nasan
338. sms spelling: paano -> pano
339. sms spelling: para -> pra
340. sms spelling: po -> p
341. sms spelling: pwede -> pwd
342. sms spelling: saan -> san
343. sms spelling: yung -> yng

<!-- END REVIEW LIST -->
