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
53. office name [bplo]: BPLO
54. office name [bplo]: opisina ng business permits
55. office name [bplo]: tanggapan ng business permits at licensing
56. office name [cho]: CHO
57. office name [cho]: city health office
58. office name [cho]: opisina ng kalusugan ng lungsod
59. office name [cswdo]: CSWDO
60. office name [cswdo]: social welfare office
61. office name [cswdo]: tanggapan ng social welfare
62. office name [lcro]: LCRO
63. office name [lcro]: civil registry
64. office name [lcro]: tanggapan ng civil registry
65. agency name [bureau-of-fire-protection-bfp]: BFP
66. agency name [bureau-of-fire-protection-bfp]: Bureau of Fire Protection
67. agency name [city-health-office-cho]: City Health Office
68. agency name [city-health-office-cho]: CHO
69. agency name [city-treasurers-office]: city treasurer's office
70. agency name [city-treasurers-office]: opisina ng city treasurer
71. agency name [civil-registry-office]: civil registry office
72. agency name [civil-registry-office]: opisina ng civil registry
73. agency name [civil-registry-office-or-notary-public]: civil registry office o notary public
74. agency name [civil-registry-office-or-notary-public]: civil registry o notaryo
75. agency name [department-of-trade-and-industry-dti]: DTI
76. agency name [department-of-trade-and-industry-dti]: Kagawaran ng Kalakalan at Industriya
77. agency name [philippine-statistics-authority-lcr-calbayog-thru-breqs]: PSA
78. agency name [philippine-statistics-authority-lcr-calbayog-thru-breqs]: Philippine Statistics Authority
79. agency name [security-and-exchange-commission-sec]: SEC
80. agency name [security-and-exchange-commission-sec]: ang SEC
81. document name [affidavit]: affidavit
82. document name [affidavit]: salaysay na may panunumpa
83. document name [application form]: application form
84. document name [application form]: porma ng aplikasyon
85. document name [barangay clearance]: barangay clearance
86. document name [barangay clearance]: klirans mula sa barangay
87. document name [birth certificate]: birth certificate
88. document name [birth certificate]: sertipiko ng kapanganakan
89. document name [cedula]: cedula
90. document name [cedula]: sedula
91. document name [death certificate]: death certificate
92. document name [death certificate]: sertipiko ng pagkamatay
93. document name [marriage certificate]: marriage certificate
94. document name [marriage certificate]: sertipiko ng kasal
95. document name [medical certificate]: medical certificate
96. document name [medical certificate]: sertipikong medikal
97. document name [official receipt]: official receipt
98. document name [official receipt]: opisyal na resibo
99. document name [police clearance]: police clearance
100. document name [police clearance]: klirans mula sa pulis
101. document name [proof of payment]: patunay ng bayad
102. document name [proof of payment]: resibo ng bayad
103. variant phrase [applicant_type:new]: bagong negosyo
104. variant phrase [applicant_type:new]: bagong aplikasyon
105. variant phrase [birth_status:marital]: magulang na kasal
106. variant phrase [birth_status:marital]: anak ng mag-asawang kasal
107. variant phrase [birth_status:non_marital]: magulang na hindi kasal
108. variant phrase [birth_status:non_marital]: anak ng magulang na hindi kasal
109. variant phrase [business_type:association]: asosasyon
110. variant phrase [business_type:association]: association
111. variant phrase [business_type:corporation]: korporasyon
112. variant phrase [business_type:corporation]: corporation
113. variant phrase [business_type:single_proprietor]: single proprietor
114. variant phrase [business_type:single_proprietor]: sole proprietor
115. variant phrase [cockfight_category:2C]: kategoryang 2C
116. variant phrase [cockfight_category:2C]: 2C
117. variant phrase [cockfight_category:3C]: kategoryang 3C
118. variant phrase [cockfight_category:3C]: 3C
119. variant phrase [cockfight_category:4C]: kategoryang 4C
120. variant phrase [cockfight_category:4C]: 4C
121. variant phrase [cockfight_category:5C]: kategoryang 5C
122. variant phrase [cockfight_category:5C]: 5C
123. variant phrase [cockfight_category:Derby]: kategoryang Derby
124. variant phrase [cockfight_category:Derby]: derby
125. variant phrase [cockfight_category:MD]: kategoryang MD
126. variant phrase [cockfight_category:MD]: MD
127. variant phrase [foreign_parent:yes]: magulang na dayuhan
128. variant phrase [foreign_parent:yes]: may magulang na dayuhan
129. variant phrase [taxpayer:company]: kompanya
130. variant phrase [taxpayer:company]: company
131. variant phrase [taxpayer:individual]: indibidwal
132. variant phrase [taxpayer:individual]: individual
133. variant frame [fil]: {base} ({variant})
134. variant frame [fil]: {base} - {variant}
135. variant frame [fil]: {variant}: {base}
136. variant frame [fil]: {base}, para sa {variant}
137. variant joiner [fil]: ' at '
138. variant joiner [fil]: ', '
139. variant frame [mixed]: {base} ({variant})
140. variant frame [mixed]: {base} - {variant}
141. variant frame [mixed]: {variant}: {base}
142. variant frame [mixed]: {base}, for {variant}
143. variant joiner [mixed]: ' and '
144. variant joiner [mixed]: ' at '
145. variant joiner [mixed]: ', '
146. family fees.cheapest.fil.1: Anong mga serbisyo ng {office} ang pinakamura?
147. family fees.cheapest.fil.1: Ano ang pinakamurang serbisyo sa {office}?
148. family fees.cheapest.fil.2: Anong serbisyo ng {office} ang pinakamababa ang bayad?
149. family fees.cheapest.fil.2: Aling serbisyo ng {office} ang pinakakaunti ang babayaran?
150. family fees.cheapest.fil.3: Pinakamurang serbisyo sa {office}
151. family fees.cheapest.fil.3: Pinakamababang bayad sa {office}
152. family fees.cheapest.fil.4: Saan sa {office} ako pinakakaunti ang magbabayad?
153. family fees.cheapest.fil.4: Anong serbisyo sa {office} ang pinakaabot-kaya?
154. family fees.cheapest.mixed.1: Which services ng {office} ang pinakamura?
155. family fees.cheapest.mixed.1: Ano ang cheapest service sa {office}?
156. family fees.cheapest.mixed.2: Anong service ng {office} ang lowest ang fee?
157. family fees.cheapest.mixed.2: Which service ng {office} ang pinakakaunti ang bayad?
158. family fees.cheapest.mixed.3: Cheapest services sa {office}
159. family fees.cheapest.mixed.3: Lowest fees sa {office}
160. family fees.cheapest.mixed.4: Saan sa {office} ako pinakakaunti magbabayad?
161. family fees.cheapest.mixed.4: Which service sa {office} ang pinaka-affordable?
162. family fees.compare_fees.fil.1: Alin ang mas mura, {service} o {service2}?
163. family fees.compare_fees.fil.1: Mas mura ba ang {service} kaysa sa {service2}?
164. family fees.compare_fees.fil.2: Ihambing ang bayad ng {service} at {service2}
165. family fees.compare_fees.fil.2: Bayad ng {service} kumpara sa {service2}
166. family fees.compare_fees.fil.3: Paano nagkakaiba ang bayad sa {service} at {service2}?
167. family fees.compare_fees.fil.3: Alin ang mas mahal, {service} o {service2}?
168. family fees.compare_fees.fil.4: {service} o {service2}: alin ang mas mababa ang bayad?
169. family fees.compare_fees.fil.4: Magkano ang agwat ng presyo ng {service} at {service2}?
170. family fees.compare_fees.mixed.1: Alin ang mas cheap, {service} or {service2}?
171. family fees.compare_fees.mixed.1: Mas mura ba ang {service} than {service2}?
172. family fees.compare_fees.mixed.2: I-compare ang fees ng {service} at {service2}
173. family fees.compare_fees.mixed.2: Fees ng {service} vs {service2}
174. family fees.compare_fees.mixed.3: Paano nagkakaiba ang fees ng {service} at {service2}?
175. family fees.compare_fees.mixed.3: Alin ang mas mahal, {service} or {service2}?
176. family fees.compare_fees.mixed.4: {service} or {service2}: alin ang lower ang fee?
177. family fees.compare_fees.mixed.4: Magkano ang price difference ng {service} at {service2}?
178. family fees.fee_time.fil.1: Magkano at gaano katagal ang {service}?
179. family fees.fee_time.fil.1: Magkano ang bayad at gaano katagal ang {service}?
180. family fees.fee_time.fil.2: Bayad at tagal ng proseso ng {service}
181. family fees.fee_time.fil.2: Gastos at oras para sa {service}
182. family fees.fee_time.fil.3: Sa bawat hakbang ng {service}, magkano at gaano katagal?
183. family fees.fee_time.fil.3: Ano ang babayaran at ilang araw sa bawat hakbang ng {service}?
184. family fees.fee_time.fil.4: Gaano katagal ang {service} at magkano ang babayaran?
185. family fees.fee_time.fil.4: Sabihin ang presyo at tagal ng paghihintay sa {service}
186. family fees.fee_time.mixed.1: Magkano at how long ang {service}?
187. family fees.fee_time.mixed.1: Magkano ang fee at gaano katagal ang {service}?
188. family fees.fee_time.mixed.2: Fee at processing time ng {service}
189. family fees.fee_time.mixed.2: Cost at time ng {service}, magkano at ilang days?
190. family fees.fee_time.mixed.3: Sa bawat step ng {service}, magkano at gaano katagal?
191. family fees.fee_time.mixed.3: Ano ang bayad at ilang days sa bawat step ng {service}?
192. family fees.fee_time.mixed.4: How long ang {service} at magkano ang babayaran?
193. family fees.fee_time.mixed.4: Pakisabi ang price at waiting time ng {service}
194. family fees.fees_total.fil.1: Magkano ang kabuuang bayad sa {service}?
195. family fees.fees_total.fil.1: Magkano lahat ang babayaran sa {service}?
196. family fees.fees_total.fil.2: Magkano ang total ng babayaran para sa {service}?
197. family fees.fees_total.fil.2: Magkano ang buong halaga ng {service}?
198. family fees.fees_total.fil.3: Kabuuang bayad sa {service}
199. family fees.fees_total.fil.3: Kabuuang babayaran para sa {service}
200. family fees.fees_total.fil.4: Pagsama-samahin ang lahat ng bayad sa {service}
201. family fees.fees_total.fil.4: Magkano ang grand total ng {service}?
202. family fees.fees_total.mixed.1: Magkano ang total fee ng {service}?
203. family fees.fees_total.mixed.1: Magkano ang total amount na babayaran sa {service}?
204. family fees.fees_total.mixed.2: Magkano lahat ang babayaran ko for {service}?
205. family fees.fees_total.mixed.2: How much lahat-lahat ang {service}?
206. family fees.fees_total.mixed.3: Total payment po ng {service}
207. family fees.fees_total.mixed.3: Total fees ng {service}
208. family fees.fees_total.mixed.4: I-add up ang lahat ng fees ng {service}
209. family fees.fees_total.mixed.4: Ano ang grand total ng {service}?
210. family fees.list.fil.1: Magkano ang bayad sa {service}?
211. family fees.list.fil.1: Magkano ang bayad para sa {service}?
212. family fees.list.fil.2: Magkano po ang babayaran para sa {service}?
213. family fees.list.fil.2: Magkano po ang babayaran sa {service}?
214. family fees.list.fil.3: Ano ang bayarin sa {service}?
215. family fees.list.fil.3: Ano ang mga bayarin para sa {service}?
216. family fees.list.fil.4: Magkano ang kailangan kong bayaran sa {service}?
217. family fees.list.fil.4: Magkano ang dapat kong bayaran para sa {service}?
218. family fees.list.fil.5: Magkano ang singil sa {service}?
219. family fees.list.fil.5: Magkano ang singil para sa {service}?
220. family fees.list.fil.6: May bayad ba ang {service}, magkano?
221. family fees.list.fil.6: May babayaran ba sa {service}, magkano po?
222. family fees.list.mixed.1: Magkano ang fee for {service}?
223. family fees.list.mixed.1: Magkano po ang fee ng {service}?
224. family fees.list.mixed.2: How much ang babayaran ko sa {service}?
225. family fees.list.mixed.2: How much ang bayad sa {service}?
226. family fees.list.mixed.3: Ano ang fees ng {service}?
227. family fees.list.mixed.3: Ano po ang mga fees for {service}?
228. family fees.list.mixed.4: Magkano po ang payment for {service}?
229. family fees.list.mixed.4: Magkano ang payment sa {service}?
230. family fees.list.mixed.5: May fee ba ang {service}? how much?
231. family fees.list.mixed.5: May fee ba sa {service}, how much po?
232. family fees.list.mixed.6: {service} fee po, magkano?
233. family fees.list.mixed.6: {service} fee, magkano ang babayaran?
234. family fees.no_fee_rows.fil.1: Anong mga serbisyo ng {office} ang walang nakalistang bayad?
235. family fees.no_fee_rows.fil.1: Aling mga serbisyo ng {office} ang walang bayad na nakasulat?
236. family fees.no_fee_rows.fil.2: May mga serbisyo ba sa {office} na walang bayad?
237. family fees.no_fee_rows.fil.2: Anong mga serbisyo ng {office} ang libre?
238. family fees.no_fee_rows.fil.3: Ilista ang mga serbisyo ng {office} na walang bayad
239. family fees.no_fee_rows.fil.3: Mga serbisyo ng {office} na hindi nagkakahalaga
240. family fees.no_fee_rows.fil.4: Anong mga serbisyo sa {office} ang hindi naniningil?
241. family fees.no_fee_rows.fil.4: Saan sa {office} ako makakakuha nang hindi nagbabayad?
242. family fees.no_fee_rows.mixed.1: Which services ng {office} ang walang fee na nakalista?
243. family fees.no_fee_rows.mixed.1: Anong services ng {office} ang no fee listed?
244. family fees.no_fee_rows.mixed.2: May services ba sa {office} na walang fee?
245. family fees.no_fee_rows.mixed.2: Anong services ng {office} ang libre?
246. family fees.no_fee_rows.mixed.3: List ng services ng {office} na walang fee
247. family fees.no_fee_rows.mixed.3: Services ng {office} na walang binabayaran
248. family fees.no_fee_rows.mixed.4: Anong services sa {office} ang hindi nagcha-charge?
249. family fees.no_fee_rows.mixed.4: Saan sa {office} ako pwedeng mag-avail nang walang bayad?
250. family fees.per_step.fil.1: Magkano ang babayaran sa bawat hakbang ng {service}?
251. family fees.per_step.fil.1: Magkano ang bayad sa bawat hakbang ng {service}?
252. family fees.per_step.fil.2: Sa aling hakbang ako magbabayad sa {service}, at magkano?
253. family fees.per_step.fil.2: Sa anong hakbang ang bayad sa {service}, at magkano?
254. family fees.per_step.fil.3: Ilang bayad ang mayroon sa bawat hakbang ng {service}?
255. family fees.per_step.fil.3: Mga bayad sa bawat hakbang ng {service}
256. family fees.per_step.fil.4: Ano ang binabayaran sa bawat hakbang ng {service}?
257. family fees.per_step.fil.4: Ano ang mga bayad sa bawat hakbang sa {service}?
258. family fees.per_step.mixed.1: Magkano ang payment sa bawat step ng {service}?
259. family fees.per_step.mixed.1: Magkano ang babayaran sa bawat step ng {service}?
260. family fees.per_step.mixed.2: Saang step ako magbabayad sa {service}, at magkano?
261. family fees.per_step.mixed.2: Sa anong step ang payment ng {service}, magkano?
262. family fees.per_step.mixed.3: May fee ba per step ng {service}? magkano each?
263. family fees.per_step.mixed.3: Fee per step ng {service}, magkano po?
264. family fees.per_step.mixed.4: Ano ang fees sa bawat step ng {service}?
265. family fees.per_step.mixed.4: Ano ang bayad per step sa {service}?
266. family office.list.fil.1: Saang opisina ang {service}?
267. family office.list.fil.1: Saang opisina po ang {service}?
268. family office.list.fil.2: Saan ako pupunta para sa {service}?
269. family office.list.fil.2: Saan po ako pupunta para sa {service}?
270. family office.list.fil.3: Anong opisina ang humahawak ng {service}?
271. family office.list.fil.3: Anong opisina ang nag-aasikaso ng {service}?
272. family office.list.fil.4: Saan po nag-aasikaso ng {service}?
273. family office.list.fil.4: Saan nag-aasikaso ng {service}?
274. family office.list.fil.5: Saan ako mag-aapply ng {service}?
275. family office.list.fil.5: Saan ako pwedeng mag-apply ng {service}?
276. family office.list.fil.6: Anong tanggapan ang may hawak ng {service}?
277. family office.list.fil.6: Anong tanggapan ang nag-aasikaso ng {service}?
278. family office.list.mixed.1: Saang office ang {service}?
279. family office.list.mixed.1: Saang office po ang {service}?
280. family office.list.mixed.2: Which office ang nag-aasikaso ng {service}?
281. family office.list.mixed.2: Which office po ang nag-aasikaso ng {service}?
282. family office.list.mixed.3: Saan ako mag-apply for {service}?
283. family office.list.mixed.3: Saan po ako mag-apply for {service}?
284. family office.list.mixed.4: Anong office ang handle ng {service}?
285. family office.list.mixed.4: Anong office po ang handle ng {service}?
286. family office.list.mixed.5: Saan po ang office para sa {service}?
287. family office.list.mixed.5: Saan ang office para sa {service}?
288. family office.list.mixed.6: Saang department ang {service}?
289. family office.list.mixed.6: Saang department po ang {service}?
290. family office.office_count.fil.1: Ilang serbisyo ang mayroon ang {office}?
291. family office.office_count.fil.1: Ilang serbisyo ang inaalok ng {office}?
292. family office.office_count.fil.2: Ilan ang serbisyo ng {office}?
293. family office.office_count.fil.2: Ilan ang mga serbisyo sa {office}?
294. family office.office_count.fil.3: Ilang serbisyo ang makukuha ko sa {office}?
295. family office.office_count.fil.3: Ilang serbisyo ang hawak ng {office}?
296. family office.office_count.fil.4: Ano ang kabuuang bilang ng serbisyo ng {office}?
297. family office.office_count.fil.4: Bilangin ang mga serbisyo ng {office}
298. family office.office_count.mixed.1: Ilang services ang meron ang {office}?
299. family office.office_count.mixed.1: Ilang services ang offer ng {office}?
300. family office.office_count.mixed.2: Ilan ang services ng {office}?
301. family office.office_count.mixed.2: Ilan ang mga services sa {office}?
302. family office.office_count.mixed.3: How many services ang makukuha ko sa {office}?
303. family office.office_count.mixed.3: How many services ang handle ng {office}?
304. family office.office_count.mixed.4: Total number ng services ng {office}?
305. family office.office_count.mixed.4: Count ng services ng {office}
306. family office.office_services.fil.1: Anong mga serbisyo ang inaalok ng {office}?
307. family office.office_services.fil.1: Anong mga serbisyo ang hawak ng {office}?
308. family office.office_services.fil.2: Ilista ang mga serbisyo ng {office}
309. family office.office_services.fil.2: Mga serbisyo ng {office}
310. family office.office_services.fil.3: Ano ang puwede kong i-apply sa {office}?
311. family office.office_services.fil.3: Ano ang makukuha ko sa {office}?
312. family office.office_services.fil.4: Ano-anong serbisyo ang mayroon ang {office}?
313. family office.office_services.fil.4: Ano ang ginagawa ng {office} para sa mga mamamayan?
314. family office.office_services.mixed.1: Anong services ang offer ng {office}?
315. family office.office_services.mixed.1: Anong services ang handle ng {office}?
316. family office.office_services.mixed.2: List ng services ng {office}
317. family office.office_services.mixed.2: Services ng {office}, ano-ano?
318. family office.office_services.mixed.3: Ano ang pwede ko ma-avail sa {office}?
319. family office.office_services.mixed.3: Ano ang makukuha ko from {office}?
320. family office.office_services.mixed.4: Ano-ano ang services ng {office}?
321. family office.office_services.mixed.4: Anong services ang meron ang {office}?
322. family processing_time.compare_time.fil.1: Alin ang mas matagal, {service} o {service2}?
323. family processing_time.compare_time.fil.1: Mas mabilis ba ang {service} kaysa sa {service2}?
324. family processing_time.compare_time.fil.2: Ihambing ang tagal ng proseso ng {service} at {service2}
325. family processing_time.compare_time.fil.2: Gaano katagal ang {service} kumpara sa {service2}?
326. family processing_time.compare_time.fil.3: {service} o {service2}: alin ang mas mabilis?
327. family processing_time.compare_time.fil.3: Ilang araw ang agwat ng {service} at {service2}?
328. family processing_time.compare_time.mixed.1: Alin ang mas matagal, {service} or {service2}?
329. family processing_time.compare_time.mixed.1: Mas fast ba ang {service} than {service2}?
330. family processing_time.compare_time.mixed.2: I-compare ang processing time ng {service} at {service2}
331. family processing_time.compare_time.mixed.2: How long ang {service} compared sa {service2}?
332. family processing_time.compare_time.mixed.3: {service} or {service2}: alin ang mas quick?
333. family processing_time.compare_time.mixed.3: Ilang days ang difference ng {service} at {service2}?
334. family processing_time.list.fil.1: Gaano katagal ang {service}?
335. family processing_time.list.fil.1: Gaano po katagal ang {service}?
336. family processing_time.list.fil.2: Ilang araw bago makuha ang {service}?
337. family processing_time.list.fil.2: Ilang araw bago matapos ang {service}?
338. family processing_time.list.fil.3: Gaano katagal ang proseso ng {service}?
339. family processing_time.list.fil.3: Gaano katagal ang proseso sa {service}?
340. family processing_time.list.fil.4: Kailan matatapos ang {service}?
341. family processing_time.list.fil.4: Kailan makukuha ang {service}?
342. family processing_time.list.fil.5: Gaano katagal maghihintay para sa {service}?
343. family processing_time.list.fil.5: Gaano katagal ang paghihintay sa {service}?
344. family processing_time.list.fil.6: Isang araw lang ba o matagal ang {service}?
345. family processing_time.list.fil.6: Mabilis ba o matagal ang {service}?
346. family processing_time.list.mixed.1: How long ang process ng {service}?
347. family processing_time.list.mixed.1: How long po ang process ng {service}?
348. family processing_time.list.mixed.2: Gaano katagal ang processing time ng {service}?
349. family processing_time.list.mixed.2: Gaano katagal ang processing time for {service}?
350. family processing_time.list.mixed.3: Ilang days bago makuha ang {service}?
351. family processing_time.list.mixed.3: Ilang days bago matapos ang {service}?
352. family processing_time.list.mixed.4: Kailan ba ready ang {service}?
353. family processing_time.list.mixed.4: Kailan po ready ang {service}?
354. family processing_time.list.mixed.5: Processing time po ng {service}, gaano katagal?
355. family processing_time.list.mixed.5: Processing time ng {service}, gaano ba katagal?
356. family processing_time.list.mixed.6: Matagal ba ang {service}, how many days?
357. family processing_time.list.mixed.6: Mabilis ba ang {service}, how many days?
358. family processing_time.longest_step.fil.1: Aling hakbang ng {service} ang pinakamatagal?
359. family processing_time.longest_step.fil.1: Ano ang pinakamatagal na hakbang sa {service}?
360. family processing_time.longest_step.fil.2: Ano ang pinakamabagal na hakbang ng {service}?
361. family processing_time.longest_step.fil.2: Saan pinakamatagal ang {service}?
362. family processing_time.longest_step.fil.3: Pinakamatagal na hakbang sa {service}
363. family processing_time.longest_step.fil.3: Pinakamabagal na hakbang ng {service}
364. family processing_time.longest_step.fil.4: Aling bahagi ng {service} ang pinakamatagal?
365. family processing_time.longest_step.fil.4: Saan ako pinakamatagal maghihintay sa {service}?
366. family processing_time.longest_step.mixed.1: Which step ng {service} ang pinakamatagal?
367. family processing_time.longest_step.mixed.1: Ano ang longest step sa {service}?
368. family processing_time.longest_step.mixed.2: Ano ang slowest step ng {service}?
369. family processing_time.longest_step.mixed.2: Saan pinakamatagal ang process ng {service}?
370. family processing_time.longest_step.mixed.3: Longest step sa {service}
371. family processing_time.longest_step.mixed.3: Slowest step ng {service}
372. family processing_time.longest_step.mixed.4: Anong part ng {service} ang pinakamatagal?
373. family processing_time.longest_step.mixed.4: Saan ako longest maghintay sa {service}?
374. family requirements.compare_requirements.fil.1: Alin ang mas maraming dokumento, {service} o {service2}?
375. family requirements.compare_requirements.fil.1: Alin ang mas maraming requirements, {service} o {service2}?
376. family requirements.compare_requirements.fil.2: Ihambing ang requirements ng {service} at {service2}
377. family requirements.compare_requirements.fil.2: Requirements ng {service} kumpara sa {service2}
378. family requirements.compare_requirements.fil.3: Mas marami ba ang requirements ng {service} kaysa sa {service2}?
379. family requirements.compare_requirements.fil.3: Alin ang mas simple, {service} o {service2}?
380. family requirements.compare_requirements.fil.4: Ilang dokumento ang {service} kumpara sa {service2}?
381. family requirements.compare_requirements.fil.4: Mas madali ba ang {service} kaysa sa {service2}, sa requirements at hakbang?
382. family requirements.compare_requirements.mixed.1: Alin ang mas maraming documents, {service} or {service2}?
383. family requirements.compare_requirements.mixed.1: Which has more requirements, {service} o {service2}?
384. family requirements.compare_requirements.mixed.2: I-compare ang requirements ng {service} at {service2}
385. family requirements.compare_requirements.mixed.2: Requirements ng {service} vs {service2}
386. family requirements.compare_requirements.mixed.3: Mas marami ba ang requirements ng {service} than {service2}?
387. family requirements.compare_requirements.mixed.3: Alin ang mas simple, {service} or {service2}?
388. family requirements.compare_requirements.mixed.4: Ilang documents ang {service} compared sa {service2}?
389. family requirements.compare_requirements.mixed.4: Mas easy ba ang {service} kaysa sa {service2}, sa requirements at steps?
390. family requirements.count.fil.1: Ilan ang mga kailangan para sa {service}?
391. family requirements.count.fil.1: Ilan ang mga kailangan sa {service}?
392. family requirements.count.fil.2: Ilang dokumento ang kailangan sa {service}?
393. family requirements.count.fil.2: Ilang dokumento ang kailangan para sa {service}?
394. family requirements.count.fil.3: Ilang papeles ang dadalhin ko para sa {service}?
395. family requirements.count.fil.3: Ilang papeles ang kailangan sa {service}?
396. family requirements.count.fil.4: Ilang requirements ang kailangan sa {service}?
397. family requirements.count.fil.4: Ilang requirements po ang {service}?
398. family requirements.count.mixed.1: Ilan ang requirements for {service}?
399. family requirements.count.mixed.1: Ilan po ang requirements ng {service}?
400. family requirements.count.mixed.2: How many documents ang kailangan sa {service}?
401. family requirements.count.mixed.2: How many papers ang kailangan for {service}?
402. family requirements.count.mixed.3: Ilang requirements po ang needed for {service}?
403. family requirements.count.mixed.3: Ilang documents po ang needed sa {service}?
404. family requirements.count.mixed.4: Ilan ang documents na dadalhin for {service}?
405. family requirements.count.mixed.4: Ilan ang papers na ihahanda for {service}?
406. family requirements.doc_in_service.fil.1: Kailangan ba ng {document} para sa {service}?
407. family requirements.doc_in_service.fil.1: Kailangan ko ba ng {document} sa {service}?
408. family requirements.doc_in_service.fil.2: Hinihingi ba ang {document} sa {service}?
409. family requirements.doc_in_service.fil.2: Humihingi ba ng {document} ang {service}?
410. family requirements.doc_in_service.fil.3: Kasama ba ang {document} sa mga requirements ng {service}?
411. family requirements.doc_in_service.fil.3: Kasali ba ang {document} sa {service}?
412. family requirements.doc_in_service.fil.4: Dapat ko bang dalhin ang {document} para sa {service}?
413. family requirements.doc_in_service.fil.4: {service}: kailangan bang magdala ng {document}?
414. family requirements.doc_in_service.mixed.1: Need ba ng {document} for {service}?
415. family requirements.doc_in_service.mixed.1: Required ba ang {document} sa {service}?
416. family requirements.doc_in_service.mixed.2: Hinihingi ba ang {document} for {service}?
417. family requirements.doc_in_service.mixed.2: Ask ba nila ang {document} sa {service}?
418. family requirements.doc_in_service.mixed.3: Kasama ba ang {document} sa requirements for {service}?
419. family requirements.doc_in_service.mixed.3: Is {document} kasama sa {service}?
420. family requirements.doc_in_service.mixed.4: Dapat ko bang i-bring ang {document} for {service}?
421. family requirements.doc_in_service.mixed.4: {service}: need bang i-bring ang {document}?
422. family requirements.doc_services.fil.1: Anong mga serbisyo ang nangangailangan ng {document}?
423. family requirements.doc_services.fil.1: Anong mga serbisyo ang humihingi ng {document}?
424. family requirements.doc_services.fil.2: Aling mga serbisyo ang kailangan ng {document}?
425. family requirements.doc_services.fil.2: Saang mga serbisyo kailangan ang {document}?
426. family requirements.doc_services.fil.3: Ilista ang mga serbisyo na nangangailangan ng {document}
427. family requirements.doc_services.fil.3: Mga serbisyong nangangailangan ng {document}
428. family requirements.doc_services.fil.4: May mga serbisyo bang humihingi ng {document}, alin?
429. family requirements.doc_services.fil.4: Para sa anong serbisyo kailangan ang {document}?
430. family requirements.doc_services.mixed.1: Which services ang nangangailangan ng {document}?
431. family requirements.doc_services.mixed.1: Anong services ang need ng {document}?
432. family requirements.doc_services.mixed.2: Saang services kailangan ang {document}?
433. family requirements.doc_services.mixed.2: Which services ang humihingi ng {document}?
434. family requirements.doc_services.mixed.3: List ng services na kailangan ang {document}
435. family requirements.doc_services.mixed.3: Services na may requirement na {document}
436. family requirements.doc_services.mixed.4: May services ba na nag-re-require ng {document}, which ones?
437. family requirements.doc_services.mixed.4: Para sa anong services need ang {document}?
438. family requirements.list.fil.1: Ano ang mga requirements para sa {service}?
439. family requirements.list.fil.1: Ano-ano ang mga requirements sa {service}?
440. family requirements.list.fil.2: Anong mga dokumento ang kailangan para sa {service}?
441. family requirements.list.fil.2: Anong dokumento ang kailangan sa {service}?
442. family requirements.list.fil.3: Ano ang dapat kong ihanda para sa {service}?
443. family requirements.list.fil.3: Ano ang dapat kong dalhin para sa {service}?
444. family requirements.list.fil.4: Ano ang mga papeles na kailangan sa {service}?
445. family requirements.list.fil.4: Ano ang mga papeles para sa {service}?
446. family requirements.list.fil.5: Pakisabi po kung ano ang kailangan sa {service}.
447. family requirements.list.fil.5: Pakisabi po ang mga kailangan para sa {service}.
448. family requirements.list.fil.6: Mga kailangan para sa {service}, ano po ba?
449. family requirements.list.fil.6: Mga requirements sa {service}, ano po?
450. family requirements.list.mixed.1: Ano ang requirements for {service}?
451. family requirements.list.mixed.1: Ano po ang requirements for {service}?
452. family requirements.list.mixed.2: What documents ang kailangan for {service}?
453. family requirements.list.mixed.2: What papers ang kailangan sa {service}?
454. family requirements.list.mixed.3: Pwede ba malaman ang requirements ng {service}?
455. family requirements.list.mixed.3: Pwede po bang malaman ang requirements sa {service}?
456. family requirements.list.mixed.4: May checklist ba kayo ng requirements for {service}?
457. family requirements.list.mixed.4: May list ba ng requirements for {service}?
458. family requirements.list.mixed.5: Anong documents ang dadalhin ko for {service}?
459. family requirements.list.mixed.5: Anong papers ang ihahanda ko for {service}?
460. family requirements.list.mixed.6: {service} requirements po, ano ang needed?
461. family requirements.list.mixed.6: {service}, ano ang mga needed documents?
462. family requirements.office_req_counts.fil.1: Ilang requirements ang bawat serbisyo ng {office}?
463. family requirements.office_req_counts.fil.1: Ilang requirements kada serbisyo sa {office}?
464. family requirements.office_req_counts.fil.2: Anong serbisyo ng {office} ang may pinakamaraming requirements?
465. family requirements.office_req_counts.fil.2: Aling serbisyo ng {office} ang pinakamaraming dokumento?
466. family requirements.office_req_counts.fil.3: Bilang ng requirements ng bawat serbisyo ng {office}
467. family requirements.office_req_counts.fil.3: Bilangin ang requirements ng bawat serbisyo sa {office}
468. family requirements.office_req_counts.fil.4: Ayusin ang mga serbisyo ng {office} ayon sa dami ng dokumento
469. family requirements.office_req_counts.fil.4: Anong mga serbisyo ng {office} ang pinakakaunti ang dokumento?
470. family requirements.office_req_counts.mixed.1: Ilang requirements ang bawat service ng {office}?
471. family requirements.office_req_counts.mixed.1: Ilang requirements per service sa {office}?
472. family requirements.office_req_counts.mixed.2: Which service ng {office} ang pinakamaraming requirements?
473. family requirements.office_req_counts.mixed.2: Anong service ng {office} ang most documents?
474. family requirements.office_req_counts.mixed.3: Count ng requirements ng bawat service sa {office}
475. family requirements.office_req_counts.mixed.3: Bilang ng requirements per service ng {office}
476. family requirements.office_req_counts.mixed.4: I-rank ang services ng {office} by number of documents
477. family requirements.office_req_counts.mixed.4: Which services ng {office} ang pinakakaunti ang documents?
478. family steps.count.fil.1: Ilan ang hakbang sa {service}?
479. family steps.count.fil.1: Ilan ang mga hakbang sa {service}?
480. family steps.count.fil.2: Ilang hakbang ang {service}?
481. family steps.count.fil.2: Ilang hakbang po ang {service}?
482. family steps.count.fil.3: Ilang proseso ang dadaanan sa {service}?
483. family steps.count.fil.3: Ilang proseso ang pagdadaanan sa {service}?
484. family steps.count.fil.4: Ilang hakbang ang kailangang gawin para sa {service}?
485. family steps.count.fil.4: Ilang hakbang ang gagawin ko sa {service}?
486. family steps.count.mixed.1: Ilan ang steps sa {service}?
487. family steps.count.mixed.1: Ilan po ang steps ng {service}?
488. family steps.count.mixed.2: How many steps ang {service}?
489. family steps.count.mixed.2: How many steps po ang {service}?
490. family steps.count.mixed.3: Ilang steps bago makakuha ng {service}?
491. family steps.count.mixed.3: Ilang steps bago matapos ang {service}?
492. family steps.count.mixed.4: Ilan ba ang process steps ng {service}?
493. family steps.count.mixed.4: Ilan ang mga process steps for {service}?
494. family steps.external_steps.fil.1: Anong mga hakbang ng {service} ang ginagawa ng ibang ahensya?
495. family steps.external_steps.fil.1: Aling mga hakbang ng {service} ang sa ibang opisina?
496. family steps.external_steps.fil.2: May mga hakbang ba ng {service} na hawak ng ibang ahensya?
497. family steps.external_steps.fil.2: Anong mga hakbang ng {service} ang nakadepende sa ibang ahensya?
498. family steps.external_steps.fil.3: Mga hakbang ng {service} na ginagawa ng ibang ahensya
499. family steps.external_steps.fil.3: Panlabas na mga hakbang sa {service}
500. family steps.external_steps.fil.4: Kailangan ko bang pumunta sa ibang ahensya sa {service}, at sa anong hakbang?
501. family steps.external_steps.fil.4: Sa anong hakbang ng {service} ako pupunta sa ibang opisina?
502. family steps.external_steps.mixed.1: Which steps ng {service} ang ginagawa ng ibang agency?
503. family steps.external_steps.mixed.1: Anong steps ng {service} ang sa another office?
504. family steps.external_steps.mixed.2: May steps ba ng {service} na handled ng ibang agency?
505. family steps.external_steps.mixed.2: Which steps ng {service} ang depende sa ibang agency?
506. family steps.external_steps.mixed.3: Steps ng {service} na ginagawa ng ibang agencies
507. family steps.external_steps.mixed.3: External steps sa {service}
508. family steps.external_steps.mixed.4: Kailangan ko bang pumunta sa ibang agency sa {service}, at sa anong step?
509. family steps.external_steps.mixed.4: Sa anong step ng {service} ako pupunta sa ibang office?
510. family steps.list.fil.1: Ano ang mga hakbang sa {service}?
511. family steps.list.fil.1: Ano ang mga hakbang para sa {service}?
512. family steps.list.fil.2: Paano ang proseso ng {service}?
513. family steps.list.fil.2: Paano po ang proseso sa {service}?
514. family steps.list.fil.3: Paano kumuha ng {service}?
515. family steps.list.fil.3: Paano po kumuha ng {service}?
516. family steps.list.fil.4: Ano ang mga dapat gawin sa {service}, isa-isa?
517. family steps.list.fil.4: Ano ang mga gagawin ko sa {service}, isa-isa?
518. family steps.list.fil.5: Pakipaliwanag po ang proseso ng {service}.
519. family steps.list.fil.5: Pakipaliwanag ang mga hakbang sa {service}.
520. family steps.list.fil.6: Ano ang una kong gagawin sa {service}, at ano ang susunod?
521. family steps.list.fil.6: Ano ang una at susunod na gagawin sa {service}?
522. family steps.list.mixed.1: Ano ang steps for {service}?
523. family steps.list.mixed.1: Ano po ang mga steps sa {service}?
524. family steps.list.mixed.2: Paano ang process ng {service}?
525. family steps.list.mixed.2: Paano po ang process sa {service}?
526. family steps.list.mixed.3: Pa-explain naman ng process for {service}
527. family steps.list.mixed.3: Pa-explain po ng steps sa {service}
528. family steps.list.mixed.4: What are the steps para makakuha ng {service}?
529. family steps.list.mixed.4: What are the steps para sa {service}?
530. family steps.list.mixed.5: Step by step ng {service}, paano?
531. family steps.list.mixed.5: Step by step po ng {service}, paano ba?
532. family steps.list.mixed.6: Ano ang procedure sa {service}?
533. family steps.list.mixed.6: Ano po ang procedure for {service}?
534. family where_to_secure.agency_services.fil.1: Anong mga serbisyo ang may kailangan mula sa {agency}?
535. family where_to_secure.agency_services.fil.1: Aling mga serbisyo ang may kinalaman sa {agency}?
536. family where_to_secure.agency_services.fil.2: Anong mga serbisyo ang nangangailangan ng papeles mula sa {agency}?
537. family where_to_secure.agency_services.fil.2: Anong mga serbisyo ang magpapapunta sa akin sa {agency}?
538. family where_to_secure.agency_services.fil.3: Ilista ang mga serbisyo na kailangang kumuha sa {agency}
539. family where_to_secure.agency_services.fil.3: Mga serbisyong kailangan ng papeles galing sa {agency}
540. family where_to_secure.agency_services.fil.4: Para sa anong mga serbisyo ako pupunta sa {agency}?
541. family where_to_secure.agency_services.fil.4: Anong mga serbisyo ang may requirement na galing sa {agency}?
542. family where_to_secure.agency_services.mixed.1: Which services ang may kailangan from {agency}?
543. family where_to_secure.agency_services.mixed.1: Anong services ang involve ang {agency}?
544. family where_to_secure.agency_services.mixed.2: Anong services ang nangangailangan ng papers from {agency}?
545. family where_to_secure.agency_services.mixed.2: Which services ang pupunta ako sa {agency}?
546. family where_to_secure.agency_services.mixed.3: List ng services na kailangan ng papers galing sa {agency}
547. family where_to_secure.agency_services.mixed.3: Services na kukuha ng requirement sa {agency}
548. family where_to_secure.agency_services.mixed.4: Para sa anong services ako pupunta sa {agency}?
549. family where_to_secure.agency_services.mixed.4: Anong services ang may requirement from {agency}?
550. family where_to_secure.doc_where.fil.1: Saan ako makakakuha ng {document}?
551. family where_to_secure.doc_where.fil.1: Saan kukuha ng {document}?
552. family where_to_secure.doc_where.fil.2: Saan puwedeng kumuha ng {document}?
553. family where_to_secure.doc_where.fil.2: Saang opisina nakukuha ang {document}?
554. family where_to_secure.doc_where.fil.3: Saan ko makukuha ang {document}?
555. family where_to_secure.doc_where.fil.3: Saan nag-iisyu ng {document}?
556. family where_to_secure.doc_where.fil.4: Sino ang nagbibigay ng {document}?
557. family where_to_secure.doc_where.fil.4: Saan ako pupunta para makakuha ng {document}?
558. family where_to_secure.doc_where.mixed.1: Saan ako kukuha ng {document}?
559. family where_to_secure.doc_where.mixed.1: Where ako kukuha ng {document}?
560. family where_to_secure.doc_where.mixed.2: Saan pwede ma-secure ang {document}?
561. family where_to_secure.doc_where.mixed.2: Which office ang nag-iisyu ng {document}?
562. family where_to_secure.doc_where.mixed.3: Saan po makakakuha ng {document}?
563. family where_to_secure.doc_where.mixed.3: Where po nakukuha ang {document}?
564. family where_to_secure.doc_where.mixed.4: Sino ang nag-iisyu ng {document}?
565. family where_to_secure.doc_where.mixed.4: Saan ako mag-apply for {document}?
566. family where_to_secure.go_first.fil.1: Saang opisina ako dapat pumunta muna bago ang {service}?
567. family where_to_secure.go_first.fil.1: Saang opisina ako unang pupunta bago ang {service}?
568. family where_to_secure.go_first.fil.2: May kailangan ba akong kunin sa ibang opisina bago ang {service}?
569. family where_to_secure.go_first.fil.2: May kailangan ba akong kunin muna sa ibang opisina para sa {service}?
570. family where_to_secure.go_first.fil.3: Saan ako unang pupunta para sa {service}?
571. family where_to_secure.go_first.fil.3: Saan ako dapat unang pumunta para sa {service}?
572. family where_to_secure.go_first.fil.4: Mayroon bang dapat kunin muna sa ibang opisina para sa {service}?
573. family where_to_secure.go_first.fil.4: Kailangan ko bang pumunta muna sa ibang opisina para sa {service}?
574. family where_to_secure.go_first.mixed.1: Saan ako pupunta first for {service}?
575. family where_to_secure.go_first.mixed.1: Saan po ako pupunta first para sa {service}?
576. family where_to_secure.go_first.mixed.2: May kailangan ba akong kunin sa ibang office before {service}?
577. family where_to_secure.go_first.mixed.2: May kailangan ba akong kunin from another office before {service}?
578. family where_to_secure.go_first.mixed.3: Which office muna ang pupuntahan ko bago ang {service}?
579. family where_to_secure.go_first.mixed.3: Anong office muna ang pupuntahan ko before {service}?
580. family where_to_secure.go_first.mixed.4: May requirement ba from another office para sa {service}?
581. family where_to_secure.go_first.mixed.4: May requirement ba galing sa ibang office para sa {service}?
582. family where_to_secure.list.fil.1: Saan kukunin ang mga requirements para sa {service}?
583. family where_to_secure.list.fil.1: Saan kukunin ang mga requirements sa {service}?
584. family where_to_secure.list.fil.2: Saan ako kukuha ng mga dokumento para sa {service}?
585. family where_to_secure.list.fil.2: Saan ako kukuha ng dokumento sa {service}?
586. family where_to_secure.list.fil.3: Saan makakakuha ng mga papeles para sa {service}?
587. family where_to_secure.list.fil.3: Saan makakakuha ng mga papeles sa {service}?
588. family where_to_secure.list.fil.4: Saan ko makukuha ang mga kailangan sa {service}?
589. family where_to_secure.list.fil.4: Saan ko makukuha ang mga kailangan para sa {service}?
590. family where_to_secure.list.fil.5: Saan po nakukuha ang requirements ng {service}?
591. family where_to_secure.list.fil.5: Saan po nakukuha ang mga dokumento ng {service}?
592. family where_to_secure.list.fil.6: Saang opisina ako kukuha ng dokumento para sa {service}?
593. family where_to_secure.list.fil.6: Saang opisina ako kukuha ng requirements sa {service}?
594. family where_to_secure.list.mixed.1: Saan ko kukunin ang requirements for {service}?
595. family where_to_secure.list.mixed.1: Saan ko kukunin ang documents for {service}?
596. family where_to_secure.list.mixed.2: Where kukuha ng documents for {service}?
597. family where_to_secure.list.mixed.2: Where ako kukuha ng requirements for {service}?
598. family where_to_secure.list.mixed.3: Saan pwede makuha ang requirements ng {service}?
599. family where_to_secure.list.mixed.3: Saan pwede makuha ang documents ng {service}?
600. family where_to_secure.list.mixed.4: Saan ko ma-secure ang documents for {service}?
601. family where_to_secure.list.mixed.4: Saan ko ma-secure ang requirements ng {service}?
602. family where_to_secure.list.mixed.5: Where po makakakuha ng papers para sa {service}?
603. family where_to_secure.list.mixed.5: Where po makukuha ang requirements ng {service}?
604. family where_to_secure.list.mixed.6: Saan nagmumula ang mga documents for {service}?
605. family where_to_secure.list.mixed.6: Saan galing ang mga requirements ng {service}?
606. family where_to_secure.office_prereqs.fil.1: Anong mga serbisyo ng {office} ang nangangailangan muna ng kailangan mula sa ibang opisina?
607. family where_to_secure.office_prereqs.fil.1: Aling mga serbisyo ng {office} ang may kailangang papeles mula sa ibang opisina?
608. family where_to_secure.office_prereqs.fil.2: Ano ang kailangan kong kunin sa ibang opisina bago gumamit ng serbisyo ng {office}?
609. family where_to_secure.office_prereqs.fil.2: Anong mga paunang kailangan mula sa ibang opisina ang may serbisyo ng {office}?
610. family where_to_secure.office_prereqs.fil.3: Ilista ang mga serbisyo ng {office} na magpapapunta sa ibang opisina
611. family where_to_secure.office_prereqs.fil.3: Anong mga serbisyo ng {office} ang nakadepende sa ibang opisina?
612. family where_to_secure.office_prereqs.fil.4: May mga serbisyo ba ng {office} na kailangan ng dokumento mula sa ibang opisina?
613. family where_to_secure.office_prereqs.fil.4: Ano ang kailangan ko mula sa ibang opisina para sa {office}?
614. family where_to_secure.office_prereqs.mixed.1: Anong services ng {office} ang need muna ng papers from ibang office?
615. family where_to_secure.office_prereqs.mixed.1: Which services ng {office} ang kailangan ng papers from another office?
616. family where_to_secure.office_prereqs.mixed.2: Ano ang dapat kong kunin sa ibang office bago mag-avail sa {office}?
617. family where_to_secure.office_prereqs.mixed.2: Anong prerequisites from other offices ang services ng {office}?
618. family where_to_secure.office_prereqs.mixed.3: List ng services ng {office} na magpapapunta sa ibang office
619. family where_to_secure.office_prereqs.mixed.3: Which services ng {office} ang depende sa ibang office?
620. family where_to_secure.office_prereqs.mixed.4: May services ba ng {office} na need ng document from different office?
621. family where_to_secure.office_prereqs.mixed.4: Ano ang need ko from other offices for {office}?
622. family who_may_avail.list.fil.1: Sino ang maaaring mag-apply sa {service}?
623. family who_may_avail.list.fil.1: Sino ang maaaring kumuha ng {service}?
624. family who_may_avail.list.fil.2: Sino ang puwedeng kumuha ng {service}?
625. family who_may_avail.list.fil.2: Sino ang puwedeng humingi ng {service}?
626. family who_may_avail.list.fil.3: Sino ang kwalipikado para sa {service}?
627. family who_may_avail.list.fil.3: Sino ang kwalipikado sa {service}?
628. family who_may_avail.list.fil.4: Para kanino ang {service}?
629. family who_may_avail.list.fil.4: Para kanino po ang {service}?
630. family who_may_avail.list.fil.5: Sino ang maaaring humiling ng {service}?
631. family who_may_avail.list.fil.5: Sino ang pinapayagang humiling ng {service}?
632. family who_may_avail.list.fil.6: Maaari ba akong kumuha ng {service}?
633. family who_may_avail.list.fil.6: Puwede ba akong kumuha ng {service}?
634. family who_may_avail.list.mixed.1: Who can avail ng {service}?
635. family who_may_avail.list.mixed.1: Who can avail po ng {service}?
636. family who_may_avail.list.mixed.2: Sino ang eligible sa {service}?
637. family who_may_avail.list.mixed.2: Sino po ang eligible sa {service}?
638. family who_may_avail.list.mixed.3: Pwede ba akong mag-apply for {service}?
639. family who_may_avail.list.mixed.3: Pwede po ba akong mag-apply sa {service}?
640. family who_may_avail.list.mixed.4: Sino ba ang qualified for {service}?
641. family who_may_avail.list.mixed.4: Sino po ang qualified sa {service}?
642. family who_may_avail.list.mixed.5: Open ba sa lahat ang {service}?
643. family who_may_avail.list.mixed.5: Open po ba sa lahat ang {service}?
644. family who_may_avail.list.mixed.6: Sino ang allowed mag-request ng {service}?
645. family who_may_avail.list.mixed.6: Sino ang allowed mag-apply sa {service}?
646. family who_may_avail.office_who.fil.1: Sino ang maaaring mag-avail ng mga serbisyo ng {office}?
647. family who_may_avail.office_who.fil.1: Sino ang puwedeng kumuha ng serbisyo ng {office}?
648. family who_may_avail.office_who.fil.2: Sino ang kwalipikado sa bawat serbisyo ng {office}?
649. family who_may_avail.office_who.fil.2: Sino ang maaaring mag-apply sa mga serbisyo ng {office}?
650. family who_may_avail.office_who.fil.3: Sino ang pinapayagang humiling ng serbisyo sa {office}?
651. family who_may_avail.office_who.fil.3: Bukas ba sa lahat ang mga serbisyo ng {office}?
652. family who_may_avail.office_who.mixed.1: Who can avail ng services ng {office}?
653. family who_may_avail.office_who.mixed.1: Sino ang pwedeng mag-avail ng services ng {office}?
654. family who_may_avail.office_who.mixed.2: Sino ang eligible sa bawat service ng {office}?
655. family who_may_avail.office_who.mixed.2: Sino ang qualified sa services ng {office}?
656. family who_may_avail.office_who.mixed.3: Sino ang allowed mag-request ng services from {office}?
657. family who_may_avail.office_who.mixed.3: Open ba sa lahat ang services ng {office}?
658. sms spelling: ano -> anu
659. sms spelling: ba -> b
660. sms spelling: bayad -> byad
661. sms spelling: hindi -> di
662. sms spelling: kailangan -> kelangan
663. sms spelling: kasi -> ksi
664. sms spelling: lang -> lng
665. sms spelling: magkano -> mgkano
666. sms spelling: naman -> nmn
667. sms spelling: nasaan -> nasan
668. sms spelling: paano -> pano
669. sms spelling: para -> pra
670. sms spelling: po -> p
671. sms spelling: pwede -> pwd
672. sms spelling: saan -> san
673. sms spelling: yung -> yng

<!-- END REVIEW LIST -->
