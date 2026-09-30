# Gateway notes (session 4)

The deterministic front end: `src/citizengraph/gateway/`, `graph/seed/aliases.yaml`, the
`gateway:` section of `config/limits.yaml`, tests in `tests/test_gateway*.py`. **No model, no
network, no Neo4j anywhere in it** (`tests/test_gateway_boundary.py` checks the imports). It reads
the graph only through `citizengraph.graph` (read-only) and does not touch `graph/load.py`.

```
process(message, session, now=None) -> GatewayResult
spam (rate, repeats, caps, injection/mutation/code) -> normalize -> gibberish score
  -> link -> intents + variant cues -> split -> clarify / echo / ok
```

Same message and same session state in, same result out (`timings_ms` aside). `now` is a
`datetime` or epoch seconds; it only feeds the rate limit, so tests inject it.

## What the caller gets

| `status` | Meaning | Fields to use |
|---|---|---|
| `ok` | answer these | `sub_requests` (Core 1; Core 2 when `intent == "status"`) |
| `clarify` | ask the citizen | `clarify_options`, `clarify_kind` (`service` or `intent`) |
| `echo_confirm` | read back before answering | `echo`, `clarify_options` (`confirm:yes` / `confirm:no`), `sub_requests` |
| `refuse` | mutation, injection, code-like text, over the hard cap | `reasons` (codes only); nothing echoed, no other stage ran |
| `fallback` | no usable request (gibberish, greeting, empty, "fees" with no service, list of services) | `reasons`; show the service menu |
| `rate_limited` | too many or repeated messages | `reasons`, `retry_after_s` |
| `out_of_scope` | not a charter service, or a service the graph cannot answer yet | `unavailable` (service id, name, `office_id`, `office_name`) or `reasons` (`other_service`, `no_service_match`) |

`SubRequest` = `service_id`, `intent`, `variants`, `phrase`, `language`, plus `office_id`.
`intent` is one of `requirements fees steps processing_time where_to_secure who_may_avail office
status`. `service_id` is `None` only for `status` questions that name no single service (Core 2
works from the application reference). `variants` only ever holds dimension/value pairs that exist
in `graph/seed/variants.yaml` **and** are used by that service's requirements or fees.
`phrase` is the only citizen-derived text that leaves the gateway: lowercase ASCII words, no
punctuation, at most `max_phrase_chars` (160), cut to the part of the message about that service;
for noisy input unknown words are dropped from it too.

Replies to a question: the UI sends the tapped option's `id` back as the next message
(`service:<id>`, `intent:<name>`, `confirm:yes`, `confirm:no`). Typed answers work as well
("delayed", "how much", "oo po"). A message that does not answer the pending question drops it
(`pending_dropped`) and is processed as new. Refused, rate-limited and empty messages leave the
pending question in place. `SessionState` holds the pending question, the last resolved service,
variants and intent (for follow-ups such as "and the fees?"), message digests (never text) and the
rate window. It is plain in-memory state: one object per session, not shared between processes.

## Design decisions

- **Ask, do not guess.** A service named with no question ("business permit") gets a clarifying
  question with the seven intents; so does an ambiguous service ("birth certificate" lists timely,
  delayed and certified transcription). `default_intent` in `limits.yaml` (null) can switch on an
  assumed intent per deployment. **This departs from behavior_spec rows 5 and 11**, whose example
  inputs carry no question; with a question in the text ("requirements for business permit and
  occupational permit") they are answered straight away.
- **Nothing is invented.** `renewal` is not a variant in the graph (`applicant_type` has only
  `new`): "business permit renewal" gives `variants: {}` plus reason
  `variant_unavailable:applicant_type=renewal`; same for cooperative and partnership. Two values of
  one dimension in a request cancel out (`variant_conflict:<dimension>`).
- **Services not in the graph** (14, see `docs/seed_status.md`) are in the alias table with
  `in_graph: false`, so the gateway can name them and their office instead of pretending
  (`out_of_scope` with `unavailable`). **behavior_spec row 3** (fees for the marriage license) lands
  here today, because LCRO-03 is one of the 14; it becomes an `ok` answer the day LCRO-03 is
  curated (set `in_graph: true`, change the registry id to the graph's slug).
- **Withheld services.** CLAUDE.md says LCRO-01 and LCRO-06 must not reach citizens until the LGU
  confirms them. The spec for this session marks them `in_graph: true`, so the gateway answers
  them. `withheld_services: []` in `limits.yaml` treats listed ids like `in_graph: false`
  (reason `withheld`); **the lead should decide whether to list `birth_registration_timely` and
  `death_registration_timely` there before any citizen sees the system.**
- **One alias, several services on purpose.** "birth certificate", "death certificate", "permit"
  are listed under every service they could mean, with the same kind weight, so they tie and the
  gateway asks. A longer alias of one service ("delayed birth registration") beats the shorter one
  of another, and cue words (`cues_en` / `cues_fil` in the registry: late, delayed, huli, newborn)
  or a single named office settle a tie without a question. Nothing else breaks a tie.
- **Status questions never ask which service.** "asa na ang permit ko?" is `status` with
  `service_id: null` (`status_service_unresolved`); Core 2 finds the application.
- **Office alone** ("BPLO") asks which of that office's services; an office next to a service
  only helps choose the service and never splits a message.
- **Unavailable part of a multi-request.** "fees for business permit and indigency certificate"
  answers the first and lists the second under `unavailable`.
- **Other government services** (passport, NBI, LTO ... list in `vocab.yaml`) are `out_of_scope`
  (`other_service`), even after a previous question in the session, and a bare "permit" inside
  "building permit" does not become the business permit.
- **Echo before answering** for input over `max_chars`, for noisy input (at least 12 words, 60 %
  unknown) and for a match made only by phrase-level fuzzy matching (`low_confidence_match`).
  After a clarifying question the echo still follows if the message was long or noisy. The echo
  text is an English draft line; the composer owns final wording in both languages.
- **Language** (`en` / `fil` / `mixed`) is a guess from words that belong to one language only. A
  Filipino frame around English nouns ("magkano ang marriage license") is `mixed`. It is
  informational: the reply language comes from the UI toggle.
- **Refuse is final and quiet.** A refused message is not normalized, linked or echoed, `reasons`
  holds codes (`prompt_injection`, `mutation_attempt`, `cypher_fragment`, `sql_fragment`,
  `markup_fragment`, `mixed_script`, `too_long`), never pieces of the text.
- The YAML lists were checked for the YAML trap that reads bare `yes`, `no`, `on`, `off` as
  booleans; the lexicon loader raises if any word is not a string.

## Thresholds (`config/limits.yaml`, `gateway:`)

| Key | Value | Effect |
|---|---|---|
| `max_chars` | 500 | longer: long-input path, whole text scanned, always echoed back |
| `hard_max_chars` | 2000 | longer: `refuse` / `too_long`, nothing processed |
| `rate_limit_per_minute` | 10 | the 11th message inside 60 s is `rate_limited` (with `retry_after_s`) |
| `repeat_limit`, `repeat_window_s` | 3, 300 | the 3rd identical message (case, spacing, punctuation ignored) inside 5 min is throttled; answers to a pending question do not count |
| `gibberish_threshold` | 0.75 | score at or above, and no service found: `fallback` / `gibberish` |
| `link_min_score` | 0.80 | weakest alias match accepted |
| `ambiguity_margin` | 0.04 | candidates within this of the best stay ambiguous |
| `echo_min_score` | 0.90 | a match method below this (phrase fuzzy) is echoed |
| `noisy_unknown_ratio`, `noisy_min_tokens` | 0.6, 12 | what counts as a noisy message |
| `max_phrase_chars` | 160 | phrase handed to the model |
| `max_sub_requests` | 6 | the rest are dropped (`sub_requests_truncated`) |
| `withheld_services` | `[]` | see above |
| `default_intent` | null | see above |

A bad value raises `GatewayConfigError` when the gateway is built; missing keys use these defaults.
Match weights by alias kind: name 1.00, synonym 0.97, abbreviation 0.95, everyday 0.93. Match
confidence: exact 1.0, token set 0.95 (0.90 with one extra word), phrase fuzzy 0.9 x ratio/100.

## What is heuristic (and what is exact)

Exact and deterministic: length caps, rate limit, repeat count, the option protocol, variant
filtering against the graph, the split boundaries, the statuses. Heuristic, tuned on invented
examples only, to be re-tuned on real data outside `eval/heldout/`:

- **Typo repair** (`normalize.py`): never for words under 5 letters, words with digits, or words
  already in the lexicon; at most 1 edit for 5 to 7 letters and 2 for longer ones; two edits only
  as insertions, deletions or a swap (never two substitutions: "magtanong" is not "magsabong");
  two equally close words mean no repair ("medicl" stays unknown and the phrase-level fuzzy match,
  then an echo, takes over); run-together words are split when both halves are known.
- **Gibberish score**: `0.6 x unknown-word share + 0.4 x max(keyboard-mash share, repeated-character
  share)`, at least the repeated-character share. Only used when nothing links, so a request buried
  in noise is still found.
- **Linker scoring and margins** above; **cue words**, the **office hint** and the merge of
  loosely joined mentions ("change of first name in birth certificate" is one request) are
  hand-written rules.
- **Mutation detector**: delete-like words always refuse; weaker verbs (change, update, add, set,
  drop ...) refuse only when a target word (fee, requirement, record, data ...) follows within
  4 words, and not as a noun ("change of first name", "update on my permit").
- **Language guess** and the **noisy** test are simple word counts.

## Known limits

- Coverage is the alias table: a phrase nobody listed is "unknown" (`no_service_match`). Situation
  phrases ("my baby was born last week") exist only where added. Add rows to
  `graph/seed/aliases.yaml`; no code change or retraining is needed.
- Short typos are not repaired (`marige`, `brth`); service words are not guessed from fragments.
- "you are now ..." and "delete" always refuse, including a harmless "my record was deleted".
  Letters outside Latin are separators, and a Latin word mixed with another script is refused
  (`mixed_script`).
- Bare "permit" is ambiguous among 7 services and "death certificate" among 4; the UI must cope
  with a list that long.
- Follow-ups ("and the fees?") use only the last resolved service; short messages only.
- Application references (for status) are not parsed; Core 2 receives only the cleaned phrase.
- `row 14` uses "asa na", a Bisaya/Waray-flavoured phrase; it is accepted as status, but Waray is
  otherwise out of scope.
- The display name of some services is the graph's (retrieved) text, typos included (CHO-15 reads
  "Medial Certificates"); the echo shows it as is.
- Lexicon YAML sits next to the code (`gateway/lexicon/`); an editable install (`pip install -e .`)
  finds it. A wheel would need `package-data`, which `pyproject.toml` does not declare yet
  (outside this session's paths).
- Hyphens and apostrophes are dropped (`mag-apply` is `mag apply`, `mayor's` is `mayors`), so a
  Filipino alias with a hyphen is written without one.
- Registry ids of the 14 services not in the graph are their charter refs (`BPLO-03`); when one is
  curated, rename the id to the graph slug and set `in_graph: true` (the loader checks both ways).
- Measured here: a 500-character message takes about 5 to 10 ms after warm-up (the first call
  also builds caches); building the gateway takes about 1 s (graph, aliases, lexicon). No GPU, no
  model file.

## Tests

`tests/test_gateway_pipeline.py` (behavior rows 1 to 13 in English, Filipino and mixed, status,
clarify and echo flows, sessions, determinism, timing), `_aliases` (completeness and the loader's
every error), `_spam` (rate, repeats, caps, about 90 detector cases, gibberish), `_normalize`
(folding, SMS table, repair and non-repair), `_linker` (matching, intents, variants, splitter),
`_invariants` (random messages and sessions: no crash, valid statuses, only real services and variants), `_config`, `_boundary` (no model or network imports, held-out folder untouched, the list below stays
complete). None needs a GPU, a model file, the network or Neo4j.

## Filipino strings that need native review

Every string below is DRAFT (`# NEEDS-NATIVE-REVIEW`): alias rows carry `needs_native_review: true`
in `graph/seed/aliases.yaml`; the lexicon files mark their Filipino sections. The gateway writes no
Filipino sentence itself. Regenerate with `python -m citizengraph.gateway.native_review`;
`test_notes_list_every_filipino_string_needing_review` fails if this list is stale.

<!-- BEGIN native-review (generated: python -m citizengraph.gateway.native_review) -->
995 strings in 76 lists.

**graph/seed/aliases.yaml, Filipino aliases of `business_permit`** (12)

`business permit` · `permit sa negosyo` · `lisensya sa negosyo` · `permiso sa negosyo` · `mayors permit` · `magbukas ng negosyo` · `magtayo ng negosyo` · `bagong negosyo` · `i renew ang negosyo` · `pag renew ng business permit` · `pagpaparehistro ng negosyo` · `permiso`

**graph/seed/aliases.yaml, Filipino aliases of `occupational_permit`** (8)

`occupational permit` · `permit sa trabaho` · `permit para sa empleyado` · `permit para sa trabaho` · `permiso sa trabaho` · `permit ng empleyado` · `permit para makapagtrabaho` · `permiso`

**graph/seed/aliases.yaml, Filipino aliases of `BPLO-03`** (9)

`special mayors permit` · `permit sa tarpaulin` · `permit sa streamer` · `permit para sa tarpaulin` · `permit sa pagsabit ng tarpaulin` · `magsabit ng tarpaulin` · `tarpaulin` · `streamer` · `permiso`

**graph/seed/aliases.yaml, Filipino aliases of `product_promotion_peddlers`** (8)

`product promotion at peddlers` · `permit sa peddler` · `permit para sa peddler` · `permit sa promosyon ng produkto` · `promosyon ng produkto` · `magtinda sa kalye` · `magbenta ng paninda` · `magpromote ng produkto`

**graph/seed/aliases.yaml, Filipino aliases of `cockfight_permit`** (9)

`permit sa sabong` · `lisensya sa sabong` · `permiso sa sabong` · `sabong permit` · `sabong` · `magsabong` · `permit para sa sabong` · `permit para sa derby` · `permiso`

**graph/seed/aliases.yaml, Filipino aliases of `BPLO-06`** (7)

`sertipikasyon ng indigency` · `sertipiko ng indigency` · `indigency certificate` · `indigency` · `sertipiko ng kahirapan` · `patunay ng kahirapan` · `sertipiko para sa mahihirap`

**graph/seed/aliases.yaml, Filipino aliases of `fishing_permit`** (9)

`permit sa pangingisda` · `lisensya sa pangingisda` · `permiso sa pangingisda` · `permit ng mangingisda` · `pangingisda` · `mangisda` · `permit para sa mangingisda` · `permit para mangisda` · `permiso`

**graph/seed/aliases.yaml, Filipino aliases of `cho_sanitary_permit`** (8)

`permiso` · `sanitary permit` · `pag isyu ng sanitary permit` · `permiso sa sanitasyon` · `permit sa sanitasyon` · `sanitasyon` · `inspeksyon ng sanitasyon` · `inspeksyon para sa negosyo`

**graph/seed/aliases.yaml, Filipino aliases of `cho_cadaver_transfer_permit`** (8)

`permiso` · `permit sa paglilipat ng bangkay` · `paglilipat ng bangkay` · `permiso sa paglilipat ng bangkay` · `bangkay` · `ilipat ang bangkay` · `ilipat ang patay` · `dalhin ang bangkay sa ibang bayan`

**graph/seed/aliases.yaml, Filipino aliases of `birth_registration_timely`** (14)

`birth certificate` · `kapanganakan` · `sertipiko ng kapanganakan` · `pagpaparehistro ng kapanganakan` · `rehistro ng kapanganakan` · `pagpapatala ng kapanganakan` · `iparehistro ang anak` · `iparehistro ang sanggol` · `magparehistro ng bata` · `ipinanganak ang anak ko` · `nanganak ako` · `pagpaparehistro ng sertipiko ng kapanganakan sa tamang oras` · `pagpaparehistro ng bagong silang na sanggol` · `rehistro ng bagong silang na sanggol`

**graph/seed/aliases.yaml, Filipino aliases of `birth_registration_delayed`** (16)

`birth certificate` · `kapanganakan` · `sertipiko ng kapanganakan` · `pagpaparehistro ng kapanganakan` · `rehistro ng kapanganakan` · `pagpapatala ng kapanganakan` · `iparehistro ang anak` · `iparehistro ang sanggol` · `magparehistro ng bata` · `hindi pa nairehistro ang anak ko` · `hindi pa rehistrado ang anak ko` · `huling pagpaparehistro ng sertipiko ng kapanganakan` · `huling pagpaparehistro ng kapanganakan` · `nahuling pagpaparehistro ng kapanganakan` · `huling rehistro ng kapanganakan` · `late registration ng birth certificate`

**graph/seed/aliases.yaml, Filipino aliases of `certified_transcription`** (18)

`birth certificate` · `kapanganakan` · `sertipiko ng kapanganakan` · `sertipiko ng kasal` · `marriage certificate` · `kasal` · `sertipiko ng kamatayan` · `kamatayan` · `death certificate` · `sertipikadong transkripsyon` · `sertipikadong kopya` · `certified true copy` · `kopya ng sertipiko ng kapanganakan` · `kopya ng sertipiko ng kasal` · `kopya ng sertipiko ng kamatayan` · `kopya mula sa civil registry` · `kopya ng birth certificate` · `kumuha ng kopya ng sertipiko`

**graph/seed/aliases.yaml, Filipino aliases of `marriage_registration_timely`** (10)

`sertipiko ng kasal` · `marriage certificate` · `kasal` · `pagpaparehistro ng kasal` · `rehistro ng kasal` · `pagpapatala ng kasal` · `iparehistro ang kasal` · `magparehistro ng kasal` · `pagpaparehistro ng sertipiko ng kasal sa tamang oras` · `pagpaparehistro ng kasal na nasa oras`

**graph/seed/aliases.yaml, Filipino aliases of `LCRO-05`** (11)

`sertipiko ng kasal` · `marriage certificate` · `kasal` · `pagpaparehistro ng kasal` · `rehistro ng kasal` · `pagpapatala ng kasal` · `iparehistro ang kasal` · `magparehistro ng kasal` · `huling pagpaparehistro ng sertipiko ng kasal` · `huling pagpaparehistro ng kasal` · `nahuling pagpaparehistro ng kasal`

**graph/seed/aliases.yaml, Filipino aliases of `LCRO-03`** (11)

`kasal` · `aplikasyon para sa lisensya sa kasal` · `lisensya sa kasal` · `lisensya ng kasal` · `marriage license` · `mag apply ng lisensya sa kasal` · `kumuha ng lisensya sa kasal` · `magpakasal` · `ikakasal` · `ikakasal na kami` · `gusto naming magpakasal`

**graph/seed/aliases.yaml, Filipino aliases of `death_registration_timely`** (10)

`sertipiko ng kamatayan` · `kamatayan` · `death certificate` · `pagpaparehistro ng kamatayan` · `rehistro ng kamatayan` · `pagpapatala ng kamatayan` · `iparehistro ang namatay` · `pagpaparehistro ng namatay` · `pagpaparehistro ng sertipiko ng kamatayan sa tamang oras` · `pagpaparehistro ng kamatayan na nasa oras`

**graph/seed/aliases.yaml, Filipino aliases of `LCRO-07`** (11)

`sertipiko ng kamatayan` · `kamatayan` · `death certificate` · `pagpaparehistro ng kamatayan` · `rehistro ng kamatayan` · `pagpapatala ng kamatayan` · `iparehistro ang namatay` · `pagpaparehistro ng namatay` · `huling pagpaparehistro ng sertipiko ng kamatayan` · `huling pagpaparehistro ng kamatayan` · `nahuling pagpaparehistro ng kamatayan`

**graph/seed/aliases.yaml, Filipino aliases of `cho_death_certificate`** (10)

`sertipiko ng kamatayan` · `kamatayan` · `death certificate` · `pag isyu ng sertipiko ng kamatayan` · `sertipiko ng kamatayan mula sa cho` · `sertipiko ng kamatayan sa health office` · `kumuha ng sertipiko ng kamatayan sa health office` · `namatay ang tatay ko` · `namatay ang nanay ko` · `namatay ang kamag anak ko`

**graph/seed/aliases.yaml, Filipino aliases of `LCRO-08`** (6)

`elektronikong endorsement sa psa` · `endorsement sa psa` · `ipadala sa psa` · `i endorse sa psa` · `ipasa sa psa` · `ipadala ang sertipiko sa psa`

**graph/seed/aliases.yaml, Filipino aliases of `court_order_registration`** (6)

`pagpaparehistro ng utos ng korte` · `utos ng korte` · `rehistro ng court order` · `pagpaparehistro ng court order` · `iparehistro ang utos ng korte` · `magparehistro ng utos ng korte`

**graph/seed/aliases.yaml, Filipino aliases of `LCRO-10`** (5)

`paghahain ng supplemental report` · `supplemental report` · `karagdagang ulat` · `maghain ng supplemental report` · `dagdag na impormasyon sa sertipiko`

**graph/seed/aliases.yaml, Filipino aliases of `LCRO-12`** (8)

`pagpaparehistro ng lehitimasyon` · `lehitimasyon` · `legitimation` · `rehistro ng lehitimasyon` · `gawing lehitimo ang anak` · `legal instrument` · `legal na instrumento` · `pagpaparehistro ng legal instrument`

**graph/seed/aliases.yaml, Filipino aliases of `ausf_registration`** (9)

`affidavit sa paggamit ng apelyido ng ama` · `ausf` · `gamitin ang apelyido ng ama` · `apelyido ng ama` · `paggamit ng apelyido ng ama` · `gamitin ng bata ang apelyido ng tatay` · `legal instrument` · `legal na instrumento` · `pagpaparehistro ng legal instrument`

**graph/seed/aliases.yaml, Filipino aliases of `legal_instrument_other`** (9)

`magparehistro ng affidavit` · `iparehistro ang affidavit` · `pagpaparehistro ng legal instrument maliban sa lehitimasyon at ausf` · `ibang legal instrument` · `iba pang legal instrument` · `affidavit ng paternity` · `legal instrument` · `legal na instrumento` · `pagpaparehistro ng legal instrument`

**graph/seed/aliases.yaml, Filipino aliases of `LCRO-15`** (12)

`petisyon para sa pagpapalit ng pangalan o pagwawasto ng pagkakamali` · `ra 9048` · `ra 10172` · `pagpapalit ng pangalan` · `pagbabago ng pangalan` · `pagtatama ng pangalan` · `pagwawasto ng pangalan` · `pagwawasto ng pagkakamali sa pangalan` · `maling spelling ng pangalan` · `mali ang pangalan sa birth certificate` · `mali sa sertipiko ng kapanganakan` · `palitan ang pangalan sa birth certificate`

**graph/seed/aliases.yaml, Filipino aliases of `LCRO-16`** (5)

`pagproseso ng kahilingan mula sa ibang cro psa at ahensya` · `kahilingan mula sa ibang civil registry` · `kahilingan mula sa psa` · `tanong mula sa ibang cro` · `kahilingan ng ahensya sa civil registry`

**graph/seed/aliases.yaml, Filipino aliases of `LCRO-17`** (8)

`pagproseso ng breqs` · `breqs` · `kopya mula sa psa` · `kopya ng psa` · `psa na kopya` · `psa na sertipiko` · `kumuha ng kopya sa psa` · `sertipiko mula sa psa`

**graph/seed/aliases.yaml, Filipino aliases of `cswdo_referrals`** (9)

`referral sa cswdo` · `referral` · `referrals` · `referral sa social welfare` · `referral ng social welfare` · `tulong pinansyal` · `tulong medikal` · `humingi ng tulong sa social welfare` · `tulong mula sa social welfare`

**graph/seed/aliases.yaml, Filipino aliases of `cho_routine_immunization`** (11)

`regular na pagbabakuna` · `bakuna` · `pagbabakuna` · `bakuna ng bata` · `bakuna para sa sanggol` · `immunization` · `pabakuna` · `mag pabakuna` · `magpabakuna` · `ipabakuna ang anak` · `ipabakuna ang sanggol`

**graph/seed/aliases.yaml, Filipino aliases of `cho_prenatal_consultation`** (9)

`konsultasyon bago manganak` · `prenatal` · `konsulta ng buntis` · `check up ng buntis` · `konsulta para sa buntis` · `pagpapacheck up ng buntis` · `buntis ako` · `magpacheck up na buntis` · `buntis`

**graph/seed/aliases.yaml, Filipino aliases of `cho_family_planning`** (6)

`pagpaplano ng pamilya` · `family planning` · `serbisyo sa family planning` · `pills sa family planning` · `magplano ng pamilya` · `pampaplano ng pamilya`

**graph/seed/aliases.yaml, Filipino aliases of `CHO-04`** (11)

`paggamot sa tb hpn filariasis schstosomiasis at ketong` · `gamot sa tb` · `gamot sa tuberculosis` · `paggamot ng tb` · `paggamot ng tuberculosis` · `gamot sa hypertension` · `ketong` · `alta presyon` · `mataas na presyon` · `may tb ako` · `gamot para sa mataas na presyon`

**graph/seed/aliases.yaml, Filipino aliases of `CHO-05`** (7)

`serbisyo ng nutrition center` · `nutrisyon` · `nutrition center` · `kulang sa timbang` · `malnutrisyon` · `payat na bata` · `timbangan ng bata`

**graph/seed/aliases.yaml, Filipino aliases of `CHO-06`** (8)

`serbisyo ng laboratoryo` · `laboratoryo` · `lab test` · `pagsusuri ng dugo` · `pagsusuri sa laboratoryo` · `magpa lab` · `magpasuri ng dugo` · `magpa lab test`

**graph/seed/aliases.yaml, Filipino aliases of `cho_pharmacy_services`** (8)

`serbisyo ng botika` · `botika` · `gamot` · `libreng gamot` · `botika ng cho` · `kumuha ng gamot` · `bumili ng gamot` · `magpakuha ng gamot`

**graph/seed/aliases.yaml, Filipino aliases of `cho_dental_services`** (10)

`serbisyong dental` · `dental` · `dentista` · `ngipin` · `pabunot ng ngipin` · `pagbunot ng ngipin` · `linis ng ngipin` · `magpabunot ng ngipin` · `masakit ang ngipin` · `sumasakit ang ngipin`

**graph/seed/aliases.yaml, Filipino aliases of `cho_animal_bite_center`** (11)

`serbisyo ng animal bite center` · `kagat ng aso` · `kagat ng pusa` · `kagat ng hayop` · `bakuna sa rabies` · `anti rabies` · `animal bite` · `nakagat ako ng aso` · `kinagat ako ng aso` · `kinagat ng aso ang anak ko` · `nakagat ng pusa`

**graph/seed/aliases.yaml, Filipino aliases of `cho_post_mortem_examination`** (7)

`pagsusuri sa bangkay` · `awtopsiya` · `post mortem` · `pagsusuri pagkatapos mamatay` · `post mortem examination` · `ipasuri ang bangkay` · `suriin ang bangkay`

**graph/seed/aliases.yaml, Filipino aliases of `cho_medico_legal_consultation`** (7)

`medico legal na konsultasyon` · `medico legal` · `medicolegal` · `medico legal na pagsusuri` · `medico legal na sertipiko` · `pagsusuri para sa kaso` · `ulat ng pinsala para sa pulis`

**graph/seed/aliases.yaml, Filipino aliases of `cho_medical_certificate`** (8)

`pag isyu ng medical certificate para sa trabaho` · `medical certificate` · `sertipiko medikal` · `medical para sa trabaho` · `medical certificate para sa trabaho` · `kumuha ng medical para sa trabaho` · `magpamedical para sa trabaho` · `magpamedical`

**graph/seed/aliases.yaml, Filipino aliases of `bplo`** (8)

`bplo` · `tanggapan ng business permits and licensing` · `opisina ng business permit` · `opisina ng bplo` · `tanggapan ng bplo` · `opisina ng business permits` · `opisina para sa business permit` · `opisina ng negosyo`

**graph/seed/aliases.yaml, Filipino aliases of `lcro`** (12)

`lcro` · `ccro` · `lcr` · `cro` · `tanggapan ng civil registry` · `opisina ng civil registry` · `civil registry` · `opisina ng lcro` · `tanggapan ng lcr` · `opisina ng civil registrar` · `opisina ng rehistro` · `tanggapan ng rehistro`

**graph/seed/aliases.yaml, Filipino aliases of `cho`** (9)

`cho` · `tanggapan ng kalusugan ng lungsod` · `opisina ng kalusugan ng lungsod` · `opisina ng cho` · `tanggapan ng cho` · `health office` · `opisina ng kalusugan` · `sentrong pangkalusugan` · `health center`

**graph/seed/aliases.yaml, Filipino aliases of `cswdo`** (9)

`cswdo` · `cswd` · `tanggapan ng social welfare at development ng lungsod` · `opisina ng social welfare` · `opisina ng cswdo` · `tanggapan ng social welfare` · `kagalingang panlipunan` · `kapakanang panlipunan` · `opisina ng welfare`

**graph/seed/aliases.yaml, `cues_fil`** (20)

`birth_registration_timely: nasa oras` · `birth_registration_timely: bagong panganak` · `birth_registration_timely: bagong silang` · `birth_registration_delayed: huli` · `birth_registration_delayed: huling` · `birth_registration_delayed: nahuli` · `birth_registration_delayed: nahuling` · `birth_registration_delayed: lampas na` · `marriage_registration_timely: nasa oras` · `LCRO-05: huli` · `LCRO-05: huling` · `LCRO-05: nahuli` · `LCRO-05: nahuling` · `LCRO-05: lampas na` · `death_registration_timely: nasa oras` · `LCRO-07: huli` · `LCRO-07: huling` · `LCRO-07: nahuli` · `LCRO-07: nahuling` · `LCRO-07: lampas na`

**lexicon/sms.yaml, `sms_fil` (typed -> canonical)** (42)

`mgkano -> magkano` · `mkano -> magkano` · `magkno -> magkano` · `magkanu -> magkano` · `pano -> paano` · `panu -> paano` · `paanu -> paano` · `asan -> nasaan` · `nasan -> nasaan` · `kelangan -> kailangan` · `kylangan -> kailangan` · `kaylangan -> kailangan` · `kailngan -> kailangan` · `pde -> pwede` · `pwde -> pwede` · `pwd -> pwede` · `puede -> puwede` · `pwedi -> pwede` · `lng -> lang` · `nmn -> naman` · `nman -> naman` · `dba -> diba` · `ksi -> kasi` · `poh -> po` · `opoh -> opo` · `oho -> opo` · `hnd -> hindi` · `hndi -> hindi` · `gus2 -> gusto` · `gsto -> gusto` · `sertifiko -> sertipiko` · `sertifiket -> sertipiko` · `sertipikeyt -> sertipiko` · `sirtipiko -> sertipiko` · `certipiko -> sertipiko` · `rehistrasyon -> rehistro` · `lisensiya -> lisensya` · `lisensia -> lisensya` · `lisencia -> lisensya` · `lisensa -> lisensya` · `bisnes -> business` · `bisnis -> business`

**lexicon/vocab.yaml, `fil_function`** (130)

`ang` · `ng` · `sa` · `mga` · `ay` · `na` · `pa` · `ba` · `po` · `opo` · `oo` · `din` · `rin` · `naman` · `lang` · `daw` · `raw` · `kasi` · `kaya` · `pero` · `dahil` · `para` · `ko` · `mo` · `ka` · `ako` · `ikaw` · `siya` · `kami` · `tayo` · `kayo` · `sila` · `namin` · `natin` · `ninyo` · `nila` · `ito` · `iyan` · `iyon` · `yan` · `yun` · `yung` · `ano` · `anong` · `aling` · `paano` · `saan` · `saang` · `kailan` · `magkano` · `sino` · `sinong` · `bakit` · `gusto` · `nais` · `may` · `mayroon` · `meron` · `wala` · `hindi` · `huwag` · `wag` · `pwede` · `puwede` · `maaari` · `dapat` · `kung` · `kapag` · `pag` · `mula` · `hanggang` · `tungkol` · `kasama` · `lahat` · `bawat` · `ilan` · `ilang` · `diba` · `salamat` · `magandang` · `umaga` · `hapon` · `gabi` · `kumusta` · `kamusta` · `pakiusap` · `paki` · `sana` · `muna` · `pala` · `nga` · `kayo` · `amin` · `atin` · `iyo` · `inyo` · `doon` · `dito` · `diyan` · `nito` · `niyan` · `noon` · `ngayon` · `bukas` · `kahapon` · `mismo` · `lamang` · `rin` · `lalo` · `talaga` · `sobra` · `medyo` · `masyado` · `hindi` · `di` · `oo` · `sige` · `tama` · `mali` · `tanong` · `tulong` · `tulungan` · `ibig` · `sabihin` · `anu` · `anuman` · `alin` · `nasaan` · `asan` · `asa`

**lexicon/vocab.yaml, `fil_common`** (175)

`negosyo` · `tindahan` · `puwesto` · `paninda` · `nagtitinda` · `magtitinda` · `tindera` · `mangingisda` · `isda` · `pamilya` · `anak` · `bata` · `sanggol` · `magulang` · `nanay` · `tatay` · `ina` · `ama` · `asawa` · `kapatid` · `lolo` · `lola` · `buntis` · `panganganak` · `kapanganakan` · `kamatayan` · `namatay` · `patay` · `bangkay` · `kasal` · `kasalan` · `ikakasal` · `magpakasal` · `mag-asawa` · `kasalanan` · `papel` · `papeles` · `dokumento` · `kopya` · `litrato` · `lagda` · `pirma` · `selyo` · `opisina` · `tanggapan` · `munisipyo` · `lungsod` · `barangay` · `probinsya` · `bayan` · `kalye` · `daan` · `pila` · `bintana` · `oras` · `araw` · `linggo` · `buwan` · `taon` · `petsa` · `bukas` · `ngayon` · `kahapon` · `pera` · `piso` · `bayad` · `presyo` · `halaga` · `libre` · `mura` · `mahal` · `resibo` · `buwis` · `gamot` · `botika` · `ospital` · `doktor` · `nars` · `klinika` · `sakit` · `bakuna` · `ngipin` · `dugo` · `hayop` · `aso` · `pusa` · `manok` · `sabong` · `tandang` · `trabaho` · `empleyado` · `amo` · `kumpanya` · `korporasyon` · `samahan` · `kooperatiba` · `pangalan` · `apelyido` · `edad` · `kasarian` · `tirahan` · `lugar` · `bansa` · `dayuhan` · `banyaga` · `pilipino` · `mamamayan` · `residente` · `hinihingi` · `hinihiling` · `hiling` · `kahilingan` · `tanong` · `sagot` · `sagutin` · `tulong` · `serbisyo` · `proseso` · `paraan` · `hakbang` · `gawin` · `gagawin` · `gawa` · `punan` · `isumite` · `ipasa` · `dalhin` · `kunin` · `kumuha` · `makakuha` · `magpa` · `mag` · `nag` · `pag` · `ipa` · `magrehistro` · `magpa-rehistro` · `mag-apply` · `magrenew` · `mag-renew` · `mahirap` · `mayaman` · `matanda` · `bata` · `bagong` · `bago` · `luma` · `huli` · `nahuli` · `maaga` · `tama` · `mali` · `kulang` · `sobra` · `pwedeng` · `puwedeng` · `maaaring` · `makukuha` · `nakuha` · `nawala` · `nasira` · `ninakaw` · `ibang` · `iba` · `lahat` · `ilan` · `wala` · `meron` · `mayroon` · `magandang` · `umaga` · `hapon` · `gabi` · `salamat` · `pasensya`

**lexicon/vocab.yaml, `greetings` (Filipino entries)** (9)

`salamat` · `kumusta` · `kamusta` · `magandang` · `umaga` · `hapon` · `gabi` · `po` · `opo`

**lexicon/vocab.yaml, `confirm_yes` (Filipino entries)** (4)

`oo` · `opo` · `tama` · `sige`

**lexicon/vocab.yaml, `confirm_no` (Filipino entries)** (4)

`hindi` · `mali` · `di` · `hnd`

**lexicon/vocab.yaml, `conjunctions` (Filipino entries)** (7)

`at` · `saka` · `tsaka` · `atsaka` · `tapos` · `pati` · `o`

**lexicon/vocab.yaml, `menu_requests` (Filipino entries)** (6)

`anong serbisyo` · `ano ang mga serbisyo` · `anong mga serbisyo` · `listahan ng serbisyo` · `mga serbisyo` · `ano ang maitutulong mo`

**lexicon/intents.yaml, `requirements` Filipino phrases** (16)

`kailangan` · `kinakailangan` · `mga kailangan` · `dokumento` · `papeles` · `dalhin` · `ihanda` · `isumite` · `ano ang kailangan` · `anong kailangan` · `anu ang kailangan` · `ano ang dadalhin` · `ano ang hinihingi` · `anong hinihingi` · `mga hinihingi` · `hinihingi`

**lexicon/intents.yaml, `fees` Filipino phrases** (11)

`magkano` · `bayad` · `babayaran` · `bayaran` · `presyo` · `singil` · `gastos` · `halaga` · `magkano ang` · `magkano po` · `magkano ba`

**lexicon/intents.yaml, `steps` Filipino phrases** (11)

`paano` · `hakbang` · `paraan` · `anong gagawin` · `ano ang gagawin` · `anong proseso` · `ano ang proseso` · `paano mag apply` · `paano kumuha` · `paano magparehistro` · `paano ang proseso`

**lexicon/intents.yaml, `steps_weak` Filipino phrases** (1)

`proseso`

**lexicon/intents.yaml, `processing_time` Filipino phrases** (15)

`gaano katagal` · `gaano ka tagal` · `ilang araw` · `ilang oras` · `ilang minuto` · `ilang linggo` · `katagal` · `tagal` · `matagal` · `gaano kabilis` · `kailan matatapos` · `kailan makukuha` · `kailan pwede kunin` · `kailan puwede kunin` · `ilang araw bago`

**lexicon/intents.yaml, `where_to_secure` Filipino phrases** (14)

`saan kukuha` · `saan kumuha` · `saan makakakuha` · `saan makakuha` · `saan kukunin` · `saan mag secure` · `saan i secure` · `saan mahahanap` · `saan nakukuha` · `saan nakakakuha` · `saan pwede kumuha` · `saan puwede kumuha` · `saan makukuha` · `saan ako kukuha`

**lexicon/intents.yaml, `who_may_avail` Filipino phrases** (17)

`sino ang pwede` · `sino ang puwede` · `sino pwede` · `sino puwede` · `sino ang maaaring` · `sino maaaring` · `pwede ba ako` · `puwede ba ako` · `para kanino` · `sino ang qualified` · `sino ang pwedeng` · `sino ang puwedeng` · `sino ang maaari` · `sino ang eligible` · `sino ang pwedeng mag apply` · `sino ang puwedeng mag apply` · `pwede ba akong mag apply`

**lexicon/intents.yaml, `office` Filipino phrases** (23)

`saan mag apply` · `saan mag file` · `saan magpa` · `saan pupunta` · `saan pumunta` · `saan ang opisina` · `nasaan ang opisina` · `anong opisina` · `aling opisina` · `saang opisina` · `nasaan` · `saan matatagpuan` · `saan ang` · `saan po ang` · `saan pwede mag apply` · `saan puwede mag apply` · `saan magpaparehistro` · `saan magpaproseso` · `saan ako pupunta` · `saan ako mag apply` · `saan ito` · `saan po` · `saan`

**lexicon/intents.yaml, `status` Filipino phrases** (21)

`asa na` · `asan na` · `nasaan na` · `nasaan na ang` · `kumusta na` · `kamusta na` · `anong balita` · `wala pa` · `hindi pa` · `approved na ba` · `tapos na ba` · `ready na ba` · `na approve na ba` · `matagal na` · `ilang araw na` · `kumusta na ang` · `kamusta na ang` · `asa na ang` · `asan na ang` · `anong nangyari sa` · `ano na nangyari sa`

**lexicon/variants.yaml, cues `applicant_type:new` Filipino phrases** (7)

`bagong negosyo` · `bagong aplikasyon` · `unang beses` · `unang pagkakataon` · `bago pa lang` · `bago` · `bagong`

**lexicon/variants.yaml, cues `business_type:single_proprietor` Filipino phrases** (2)

`sariling negosyo` · `single proprietor`

**lexicon/variants.yaml, cues `business_type:corporation` Filipino phrases** (1)

`korporasyon`

**lexicon/variants.yaml, cues `business_type:association` Filipino phrases** (2)

`asosasyon` · `samahan`

**lexicon/variants.yaml, cues `taxpayer:company` Filipino phrases** (2)

`kumpanya` · `kompanya`

**lexicon/variants.yaml, cues `taxpayer:individual` Filipino phrases** (4)

`indibidwal` · `sarili` · `sa sarili` · `empleyado`

**lexicon/variants.yaml, cues `birth_status:marital` Filipino phrases** (3)

`kasal ang magulang` · `mag asawa ang magulang` · `kasal ang mga magulang`

**lexicon/variants.yaml, cues `birth_status:non_marital` Filipino phrases** (4)

`hindi kasal ang magulang` · `hindi kasal ang mga magulang` · `anak sa labas` · `hindi kasal`

**lexicon/variants.yaml, cues `foreign_parent:yes` Filipino phrases** (8)

`dayuhan` · `banyaga` · `hindi pilipino` · `dayuhang magulang` · `dayuhan ang tatay` · `dayuhan ang nanay` · `banyaga ang tatay` · `banyaga ang nanay`

**lexicon/variants.yaml, unsupported `applicant_type:renewal` Filipino phrases** (9)

`renew` · `irenew` · `pag renew` · `pagre renew` · `magrenew` · `mag renew` · `i renew` · `pagbabago ng permit` · `muling pagkuha`

**lexicon/variants.yaml, unsupported `business_type:cooperative` Filipino phrases** (1)

`kooperatiba`

**lexicon/spam.yaml, `injection.fil` patterns (regex)** (7)

- `\b(?:huwag|wag|di|hindi)\s+(?:mo(?:ng)?\s+)?(?:pansinin|sundin|pakinggan)\b(?:\W+\w+){0,4}?\W+(?:patakaran|utos|panuntunan|instruksyon|instructions?|rules?|bilin|alituntunin)\b`
- `\b(?:kalimutan|kalimutin|balewalain|isantabi|lampasan|suwayin|labagin)\b(?:\W+\w+){0,4}?\W+(?:patakaran|utos|panuntunan|instruksyon|instructions?|rules?|bilin|alituntunin)\b`
- `\b(?:ipakita|ibigay|ilista|ilabas|ipadala|kunin)\b(?:\W+\w+){0,3}?\W+(?:lahat|buong|kumpletong)\b(?:\W+\w+){0,2}?\W+(?:data|datos|record|rekord|database|talaan)\b`
- `\b(?:magpanggap|umarte\s+ka)\b`
- `\bikaw\s+na\s+ngayon\b`
- `\bmula\s+ngayon\b(?:\W+\w+){0,6}?\W+(?:ikaw|huwag|sagutin)\b`
- `\b(?:ibunyag|ilabas|sabihin)\b(?:\W+\w+){0,3}?\W+(?:prompt|instruksyon|password|sikreto)\b`

**lexicon/spam.yaml, `mutation.strong.fil` verbs** (5)

`burahin` · `buburahin` · `burahing` · `wasakin` · `sirain`

**lexicon/spam.yaml, `mutation.weak.fil` verbs** (7)

`tanggalin` · `alisin` · `baguhin` · `palitan` · `idagdag` · `dagdagan` · `gumawa`
<!-- END native-review -->
