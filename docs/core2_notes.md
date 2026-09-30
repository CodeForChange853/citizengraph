# Core 2 notes (SLA agent)

Session 6, branch `session6-core2`. Code in `src/citizengraph/core2/`, config in `config/core2.yaml`,
scenarios and harness in `eval/core2/`, tests in `tests/test_core2*.py`. Not wired into the API.

Sections 1 and 2 were written before any scenario existed; section 2 is the **frozen** baseline.
The rest of the file (scenarios, results, limits, Filipino strings) is filled in at the end.

## 1. Design in one screen

```
Task (status of a reference | office sweep | working days | suspension check)
  -> ReAct loop over LLMClient: {"tool": ..., "args": {...}} or {"final": {...}}
       tools (read-only, plain code) -> compact JSON observation -> next prompt
  -> AgentResult (final, trace, steps, stopped_reason)
```

* **Exact things are code.** Elapsed minutes, working days, verdicts (`within`, `minor_over`, `over`,
  `not_comparable`) and alert text are computed by the tools (`sla.py`, `tools.py`, `alerts.py`).
  The model chooses which tool to call next, with which arguments, and when to stop, and it
  assembles the final labels from tool output.
* **Two clocks, always labelled.** `charter_step_time` (from the seed) and
  `statutory_cap_unverified` (from `config/sla.yaml`, NOT verified against RA 11032 and never
  presented as law; citizen-facing alert text does not mention the statute).
* **Nothing is guessed.** A day-based charter time has day type `unknown`; without an explicit
  override (config or scenario) the step is `not_comparable` (`day_type_unknown`). A step with no
  stated time is `not_comparable` (`charter_time_not_stated`). A missing timestamp is never filled in.
* **External steps are not LGU delay.** A step with `external_agency` is reported as
  `external_waiting`; its days are removed from the statutory count.
* **Separate stores.** Simulated applications live in `WorkflowStore` (never the charter graph);
  drafted alerts live in `AlertStore` (memory or one JSONL file). Neither touches Neo4j, and
  `draft_alert` is the only write in the whole package.
* **Statuses:** `on_track`, `minor_delay`, `delayed`, `overdue_statutory`, `external_waiting`,
  `waiting_posting`, `paused_by_suspension`, `cannot_determine`, `completed`.
* **Final answer:** `{"applications": [{"app_id", "status", "reasons": [...], "alerts": [...]}]}`
  for status tasks and sweeps, `{"answer": {"working_days": n}}` or `{"answer": {"suspended": b}}`
  for the calendar tasks.

## 2. Baseline (rule-based) agent: FROZEN rules

`core2/baseline.py`. Written from the task description and the tool list, before the scenarios were
written. It uses the same tools and returns the same `AgentResult`, so the harness scores it like a
model. **These rules are frozen: do not change them after seeing scenario results.** A change needs a
new dated entry below saying why, and results must be re-reported for both versions.

Status task (`get_applications(ref)` first; no application means `cannot_determine`,
reason `no_application_found`). Then for every application returned, in order, the first rule that
matches wins:

| # | Rule | Result |
|---|---|---|
| B1 | `get_workflow_state`; the record has any timestamp `issues` | draft `missing_data_flag`; `cannot_determine` (`missing_timestamp`); stop for this application |
| B2 | the application is complete | `completed` |
| B3 | the current step has an `external` agency | `get_step_sla` with the application; `external_waiting` (`external_agency`); if the charter verdict is `over` also draft `external_wait_notice` |
| B4 | the current step is a `posting` period | `waiting_posting` (`posting_period`); no alerts |
| B5 | `get_step_sla` with the application; `suspension_effect` is set on the statutory or charter check | `paused_by_suspension` (`suspension_days_excluded`); no alerts |
| B6 | statutory verdict `over` | `overdue_statutory` (`statutory_cap_exceeded`); draft `citizen_delay_notice` and `department_head_escalation` |
| B7 | charter verdict `over` | `delayed` (`over_charter_step_time`); draft `citizen_delay_notice`; then `get_step_roles`, and if the step has a role, `get_role_availability` on the as-of date; if the role is absent also draft `department_head_escalation` (`role_unavailable`) |
| B8 | charter verdict `minor_over` | `minor_delay`; no alerts |
| B9 | charter verdict `within` | `on_track` |
| B10 | charter verdict `not_comparable` | `cannot_determine` with the tool's reason (`day_type_unknown`, `charter_time_not_stated`, ...); no alerts |

Office sweep: `list_overdue(office_id, as_of)`, then B1 to B10 for each row. Working-days task:
`working_days_elapsed`. Suspension task: `check_work_suspension`. The baseline never calls
`check_work_suspension` in a status task and never looks at applications beyond the tool's row limit.

Known simplifications, written down on purpose: it stops at the first timestamp issue (B1) and does
not assess the current step when an *earlier* step has a bad timestamp; it treats every posting
period as waiting (B4) even when the posting time is over; it does not treat "today is a declared
suspension" as a reason to hold alerts. These are the choices a straightforward if-else agent makes;
they were not chosen to fail any scenario.

## 3. Tools (`core2/tools.py`)

Nine typed, documented, read-only tools behind `Toolbox.call(name, args)`. Arguments are validated
strictly (unknown keys, missing keys, wrong types, `2026-3-4`, `20260304`, timezone suffixes and
free text are all rejected with a message the model can read). Ids are limited to letters, digits
and `_ . : -` (64 characters). Content problems (`not_found`, `end_before_start`, `unknown_role`,
`not_applicable`) come back as `{"error": ...}` observations, not exceptions. Outputs drop `None`
values and stay under `max_observation_chars` (900); list tools return at most `row_limit` (10) rows.

| Tool | Returns |
|---|---|
| `get_applications(ref)` | applications for a reference code or citizen code: id, ref, service, submitted |
| `get_workflow_state(app_id)` | complete?, current step (id, order, start, minutes in step, external agency, posting flag), timestamp `issues` |
| `get_step_sla(service_id, step_id, app_id?)` | without `app_id`: charter time, day type, statutory cap, both with a `basis`. With `app_id`: the exact comparison (`check.charter.verdict`, `check.statutory.verdict`, measured, allowed, `suspension_effect`) |
| `working_days_elapsed(start, end)` | working days `d` with `start < d <= end` |
| `check_work_suspension(date)` | suspended?, working day?, reason |
| `get_step_roles(step_id)` | the role title (never a name), or none with a note |
| `get_role_availability(role, date)` | available? (simulated absence roster) |
| `list_overdue(office_id, as_of)` | LGU-overdue applications of an office; external waits and records with no start time are not listed |
| `draft_alert(app_id, kind)` | the only writer; appends to the alert store; refuses alerts the facts do not support; one alert per (application, kind) |

`get_step_sla` with `app_id` is an addition to the specified signature (optional third argument).
It exists so the comparison is done in code, not by the model.

**Verdicts.** Charter: `within` (elapsed <= max of the charter range), `minor_over` (up to
`minor_delay_ratio` = 1.5 times), `over`, `not_comparable` (with a reason: `charter_time_not_stated`,
`day_type_unknown`, `missing_timestamp`, `timestamps_out_of_order`). Statutory: `within`, `over`,
`not_comparable` (`posting_period_treatment_unverified`, `missing_timestamp`, `cap_not_configured`).
Clock steps (minutes, hours) use wall-clock minutes. Day steps use working days or calendar days
only when the day type is explicit (config `day_type_overrides` or a scenario); `week` = 7 calendar
days or the number of working days in a week. Statutory days are working days from receipt, minus the
days spent in external steps. `suspension_effect` is set when the verdict would be worse without the
declared suspension days.

## 4. Reference policy (`core2/scripted.py`)

The rules that the gold outcomes, the ScriptedPolicy and the gold trajectories follow. The first
matching line wins within a group.

| # | Rule |
|---|---|
| R1 | No application found: `applications: []`, reason `no_application_found`. |
| R2 | Any timestamp `issues` on the record: draft `missing_data_flag` (also for finished applications). |
| R3 | The current step has no start time: `cannot_determine` (`missing_timestamp`); nothing else can be measured. A lost timestamp in an EARLIER step does not stop the assessment of the current step. |
| R4 | Complete: `completed`. |
| R5 | Current step is external: `external_waiting` (`external_agency`); `external_wait_notice` only when the stated external time is exceeded beyond the tolerance. Never a citizen delay notice. |
| R6 | Posting period: `waiting_posting` unless the charter verdict is `over` (only possible when a day type is given), then it is treated as an ordinary delay. |
| R7 | Delay candidate (statutory `over` or charter `over`): call `check_work_suspension` for today; if today is a declared suspension day, `paused_by_suspension` (`suspension_today`) and the delay alerts are held. |
| R8 | Statutory `over`: `overdue_statutory`, alerts `citizen_delay_notice` + `department_head_escalation`. Charter `over`: `delayed`, `citizen_delay_notice`; then `get_step_roles` and `get_role_availability` for today, and if the role is absent also `department_head_escalation` (`role_unavailable`). |
| R9 | `suspension_effect`: `paused_by_suspension` (`suspension_days_excluded`). Otherwise `minor_over` is `minor_delay`, `within` is `on_track`, `not_comparable` is `cannot_determine` with the tool's reason. No alerts for these. |

R7 (hold alerts on a declared suspension day) and the "earlier lost timestamp does not stop the
assessment" part of R3 are design choices of this session; they are not charter or legal facts.
They are the two places where the reference policy differs on purpose from the frozen baseline.

## 5. Simulator (`core2/simulator.py`)

Deterministic (seed) generator of simulated applications for the 26 curated services. Situations:
`on_time`, `minor_delay`, `over_charter`, `overdue_statutory`, `suspension_pause`,
`external_waiting`, `external_over`, `completed`. Injections: `missing_current`, `missing_earlier`,
`role_unavailable`, `extra_suspension`. Several applications for one citizen share a `citizen_ref`.
Reference codes are fake (`CG-SIM-0001`, `CIT-0001`); the model rejects anything else, and staff
names never enter the store. Every application carries the `Truth` it was built to produce; a test
runs the reference policy over 360 generated applications (6 seeds) and checks status and alerts
against that truth. An ad-hoc run over 4,800 (80 seeds) also agreed. Writing that check found and
fixed two of the simulator's own mistakes (the role roster is shared between applications, and
dropping a timestamp of an external step makes the statutory count undecidable). Simulated timelines keep clock steps inside one day
(as-of is 14:00), because office hours are unknown (see limits).

## 6. Scenarios (`eval/core2/scenarios/*.yaml`, 54)

Four files: easy (single situation), messy (facts interact), sweeps (`list_overdue`), calendar.
Gold is hand-written per scenario from the injected situation. For simulator-built applications a
test also checks the gold against the simulator's own truth. Budget = `max_steps` for that scenario
(default 8 = `config/core2.yaml`); "reference steps" = steps the reference policy used (tool calls
+ the final answer).

| Scenario | What it tests | Budget | Reference steps | Baseline |
|---|---|---|---|---|
| `E01` | on time, BPLO step 8 | 8 | 4 | ok |
| `E02` | on time, occupational permit | 8 | 4 | ok |
| `E03` | minor delay (within tolerance), dental | 8 | 4 | ok |
| `E04` | over charter, signatory present | 10 | 8 | ok |
| `E05` | over charter, signatory absent | 10 | 9 | ok |
| `E06` | statutory cap exceeded | 8 | 7 | ok |
| `E07` | current step has no start time | 8 | 4 | ok |
| `E08` | external wait, no stated time | 8 | 4 | ok |
| `E09` | external wait over stated time | 8 | 5 | ok |
| `E10` | CSWDO '1 week', day type unknown | 8 | 4 | ok |
| `E11` | completed | 8 | 3 | ok |
| `E12` | reference matches nothing | 8 | 2 | ok |
| `E13` | posting period, day type unknown | 8 | 4 | ok |
| `E16` | step with no charter time | 8 | 4 | ok |
| `E17` | on time, civil registry | 8 | 4 | ok |
| `E18` | on time, health | 8 | 4 | ok |
| `E19` | over charter, civil registry | 10 | 8 | ok |
| `E20` | City Civil Registrar absent | 10 | 9 | ok |
| `M01` | absent signatory + suspension day + lost earlier timestamp | 12 | 10 | **misses** |
| `M02` | lost earlier timestamp, current on time | 8 | 5 | **misses** |
| `M03` | lost earlier timestamp + statutory overdue | 10 | 8 | **misses** |
| `M04` | completed, lost timestamp | 8 | 4 | **misses** |
| `M05` | external wait beside a posting period (2 apps) | 16 | 7 | ok |
| `M06` | posting over (calendar days given), still waiting | 12 | 8 | **misses** |
| `M07` | suspension pauses a day-based step | 8 | 4 | ok |
| `M08` | suspension does not rescue an overdue | 8 | 7 | ok |
| `M09` | today is a suspension day, delayed app | 10 | 5 | **misses** |
| `M10` | four applications, four situations | 30 | 14 | ok |
| `M11` | absent role but step on time | 8 | 4 | ok |
| `M12` | statutory overdue + absent role | 8 | 7 | ok |
| `M13` | delayed step, charter names no role | 10 | 7 | ok |
| `M14` | external wait + lost timestamp | 8 | 5 | **misses** |
| `M15` | external days excluded from statutory count | 8 | 4 | ok |
| `M16` | holiday keeps count at the cap | 8 | 4 | ok |
| `M17` | exactly at the cap is not over | 8 | 4 | ok |
| `M18` | minor delay + lost timestamp | 8 | 5 | **misses** |
| `M19` | unknown day type but statutory overdue | 10 | 7 | ok |
| `M20` | posting period + lost timestamp | 8 | 5 | **misses** |
| `M21` | a different role is absent | 10 | 8 | ok |
| `M23` | today is a suspension day, statutory overdue | 10 | 5 | **misses** |
| `M24` | two applications share an absent role | 30 | 16 | ok |
| `W01` | BPLO sweep, mixed | 24 | 13 | ok |
| `W02` | sweep, nothing overdue | 8 | 2 | ok |
| `W03` | CHO sweep | 14 | 8 | ok |
| `W04` | sweep skips record with no current start time | 14 | 8 | ok |
| `W05` | civil registry sweep, absent registrar | 30 | 15 | ok |
| `C01` | Monday to Friday, no holidays | 8 | 2 | ok |
| `C02` | Monday to next Monday | 8 | 2 | ok |
| `C03` | Monday to Friday with a fixture holiday on Wednesday | 8 | 2 | ok |
| `C04` | Only Friday is left after two suspension days and a holiday | 8 | 2 | ok |
| `C05` | Start and end on the same day | 8 | 2 | ok |
| `C06` | Is 5 March a declared suspension day? (yes, fixture) | 8 | 2 | ok |
| `C07` | Saturday is not a declared work suspension | 8 | 2 | ok |
| `C08` | A fixture holiday is not a declared work suspension | 8 | 2 | ok |

## 7. Results

`python -m citizengraph.core2.eval` (add `-v` to list every miss). Deterministic; no model.

```
runner               N  outcome traject. tool_sel  req_cov   arg_ok  steps false_al missed_al  fallbk refused
-------------------------------------------------------------------------------------------------------------
baseline            54    81.5%    81.5%   100.0%    94.3%   100.0%    5.2     3.3%      9.7%    0.0%       0
scripted-policy     54   100.0%   100.0%   100.0%   100.0%   100.0%    5.7     0.0%      0.0%    0.0%       0

outcome by category (correct/total)
----------------------------------------
runner                calendar        easy       messy       sweep
baseline                   8/8       18/18       13/23         5/5
scripted-policy            8/8       18/18       23/23         5/5
```

How to read this, honestly:

* **The `scripted-policy` row is a test double, not a model.** It follows the reference policy
  that also wrote the gold. 100% means the loop, prompt, grammar, tools, simulator and gold agree
  with each other. It says nothing about language models. Real model evaluation is still to do:
  wrap the quantized model in an `LLMClient` and call `evaluate(ReActAgent(llm), scenarios)`.
* **The baseline misses 10 of 54** (all `messy`): seven scenarios where an earlier step lost a
  timestamp (baseline rule B1 stops at any timestamp issue), one where the posting period is over
  (B4), two where today is a declared suspension day (the baseline does not look at today). Each is
  a simplification written in section 2 before the scenarios existed. The set of misses is pinned
  by `tests/test_core2_eval.py`, so any change to the baseline rules or the scenarios shows up.
  The baseline passes all easy, calendar and sweep scenarios and 13 of 23 messy ones (including
  external waits, absent roles, several applications, statutory arithmetic with holidays,
  suspension days and external time).
* **This is not evidence that a model beats if-else.** I wrote the baseline first, then the
  scenarios, knowing its documented simplifications; the share of scenarios that target them is my
  choice. A stronger if-else (assess the current step even when an earlier timestamp is bad, hold
  alerts on a suspension day, treat an expired posting as a delay) would pass all 54. What the
  numbers show is where this particular baseline breaks and that adding those rules is what fixes it.
  The RQ3 question (does the model choose well on combinations nobody wrote a rule for?) needs scenarios
  the rule author did not see, and a real model.
* `tool_sel`, `req_cov` and `arg_ok` are 100% for both runners here because neither ever calls a
  wrong tool or a wrong entity. They matter for real models.
* `false_al` for the baseline (3.3% of applications) comes from the two suspension-day scenarios,
  where it drafts alerts on a day the reference policy holds them. `missed_al` (9.7% of applications
  that should get an alert) comes from the B1 and B4 misses.
* Steps: the reference policy needs 2 to 16 steps; 19 of 54 scenarios declare a budget above the
  default 8 (the absent-signatory case alone needs 9 to 10). The default cap of 8 fits the typical
  single-application question but not the worst one; see limits.

## 8. Known limits

* **Office hours are unknown.** Clock steps are compared on wall-clock minutes, so a step left
  overnight reads as far over its time. Simulated timelines avoid this by staying inside one day. A
  real deployment needs office hours (or working-time timestamps) from the LGU.
* **Day types are unknown** (`docs/charter_data.md`): the 10-day posting (LCRO-02), the CSWDO "1 week"
  and the CHO sanitary inspection "3 days" are `not_comparable` unless a day type is supplied. The
  scenarios that supply one (M06, M07) are fixtures of this session, not LGU answers.
* **Statutory caps are unverified** (`config/sla.yaml`: SIMPLE 3, COMPLEX 7 working days). Every
  statutory result says `statutory_cap_unverified`; the escalation text says the limit is not
  verified; citizen texts never mention the statute. How a posting period counts against the cap is
  open, so the statutory check is switched off once a posting step has started.
* **External steps are only those the seed marks.** The seed marks 6 steps (4 City Treasurer's
  Office payments, 2 City Agriculture Office steps). PSA mailing/issuance steps and the marriage-license
  seminar are NOT marked `external_agency` in the seed (LCRO-03 and LCRO-17 are not curated), so Core 2
  cannot call them external waits. Marking them is a seed change; this session did not touch the seed.
* **Only 26 of 40 services** are in the graph (14 are held back, `docs/seed_status.md`); Core 2 has no
  data for the others. LCRO-06 and LCRO-01 must not reach citizens until the LGU confirms
  (`CLAUDE.md`); Core 2 shows only step times and status, but the same caution applies.
* **`minor_delay_ratio` (1.5)** is a tunable design choice, not a charter fact. The cut between "minor"
  and "over" changes which applications get alerts.
* **Roles.** 33 seed steps have no role title (the charter gives names only, or nothing), so
  absent-role checks cannot apply there.
  The absence roster is simulated; a real system needs an attendance source. "Head of the office" is
  generic: the charters name no department-head role.
* **Context.** `max_prompt_chars` (6,500) is a proxy for the 2,048-token context at an assumed 3 to 3.5
  characters per token; it was not measured with the real tokenizer. The longest scenario prompt is
  6,188 characters (four applications). More applications than that need the request split in code, one
  agent run per application; not implemented (the loop is stateless, state lives in code).
* **Step cap.** Default 8 (config). The absent-signatory case needs 9 to 10 steps, so a model with cap 8
  would fall back on it. Consider 12 after the adviser confirms; scenarios declare their own budget.
* **Gold is circular by construction.** Gold, ScriptedPolicy and the gold trajectories share one author.
  A model trained on the trajectories imitates the reference policy; it cannot outdo it.
* Alerts are drafts in a local store; nothing is sent. Timestamps are naive local time (PHT, fixed
  UTC+8, no daylight saving). Some simulator test cases are skipped on purpose: they are service and
  situation pairs the charter cannot host (for example an external wait in a service with no external
  step).

## 9. Filipino strings needing native-speaker review

Every Filipino string is a draft marked `# NEEDS-NATIVE-REVIEW` in the code. Waray is out of scope.
Alert texts (`core2/alerts.py`, `FILIPINO_STRINGS`), fragments:

- walang naitalang oras ng simula
- walang naitalang oras ng pagtatapos
- mas maaga ang oras ng pagtatapos kaysa sa simula
- minuto
- oras
- araw
- ng trabaho
- (kalendaryo)
- sa hakbang {n} ng {total}
- Ang aplikasyon ninyo na {ref} para sa {service}
- ay mas matagal kaysa sa itinakdang oras ng {office}
- itinakdang oras sa hakbang na ito
- Paumanhin po sa pagkaantala.
- Magtanong po sa opisina kung may katanungan.
- nang pinoproseso, na mas matagal kaysa inaasahan
- PAG-ULAT SA PINUNO ng {office}
- lampas na sa oras
- Lumipas:
- itinakdang oras:
- Araw ng trabaho mula pagtanggap:
- itinakdang limitasyon:
- HINDI pa napapatunayan sa RA 11032 ang limitasyong ito
- Responsableng tungkulin:
- (absent ngayon)
- naghihintay sa ibang ahensya
- nang mas matagal kaysa karaniwan
- karaniwang oras:
- Hindi ito kasama sa pagproseso ng {office}.
- Makipag-ugnayan po sa {agency}.
- BABALA SA DATOS para sa {office}
- may problema sa oras
- Hindi masusukat ang oras sa mga hakbang na ito at walang ipinagpalagay.
- Pakiayos po ang talaan.

Citizen status lines and lead-ins (`core2/report.py`, `FILIPINO_STRINGS`), whole strings:

- Aplikasyon {ref}: maayos ang takbo. Pinoproseso ito sa loob ng inaasahang oras.
- Aplikasyon {ref}: bahagyang lampas sa karaniwang oras sa hakbang na ito, pinoproseso pa rin.
- Aplikasyon {ref}: mas matagal kaysa sa itinakdang oras sa hakbang na ito. Paumanhin po.
- Aplikasyon {ref}: mas matagal na kaysa inaasahan ang pagproseso. Paumanhin po sa pagkaantala.
- Aplikasyon {ref}: naghihintay sa ibang ahensya ({agency}). Hindi ito kasama sa pagproseso ng aming opisina.
- Aplikasyon {ref}: nasa kinakailangang panahon ng pagpapaskil. Panahon ito ng paghihintay, hindi pagkaantala.
- Aplikasyon {ref}: naka-pause dahil sa idineklarang suspensyon ng trabaho.
- Aplikasyon {ref}: hindi namin matiyak mula sa aming talaan kung gaano katagal ito. Magtanong po sa opisina.
- Aplikasyon {ref}: kumpleto na ang lahat ng hakbang.
- Narito ang katayuan ng inyong aplikasyon.
- Wala kaming nakitang aplikasyon na may ganoong reference.
- Hindi namin ito nasuri nang ligtas. Magtanong po sa opisina.

Full alert texts as they render (English beside the Filipino draft):

**citizen_delay_notice**

- EN: Your application CG-SIM-0201 for Business Permit at step 8 of 10 is taking longer than the Business Permits & Licensing Office charter time (9.5 minutes so far; charter time for this step: 5 minutes). We are sorry for the delay. Please ask the office if you have questions.
- FIL (draft): Ang aplikasyon ninyo na CG-SIM-0201 para sa Business Permit sa hakbang 8 ng 10 ay mas matagal kaysa sa itinakdang oras ng Business Permits & Licensing Office (9.5 minuto na; itinakdang oras sa hakbang na ito: 5 minuto). Paumanhin po sa pagkaantala. Magtanong po sa opisina kung may katanungan.

**department_head_escalation**

- EN: ESCALATION for the head of Business Permits & Licensing Office: application CG-SIM-0201 (Business Permit) is past its time at step 8 of 10. Elapsed 9.5 minutes; charter step time 5 minutes. Responsible role: BPLO Chief (marked absent today).
- FIL (draft): PAG-ULAT SA PINUNO ng Business Permits & Licensing Office: ang aplikasyon CG-SIM-0201 (Business Permit) ay lampas na sa oras sa hakbang 8 ng 10. Lumipas: 9.5 minuto; itinakdang oras: 5 minuto. Responsableng tungkulin: BPLO Chief (absent ngayon).

**external_wait_notice**

- EN: Your application CG-SIM-0109 for Occupational Permit is waiting at another agency (City Treasurer’s Office) for longer than the usual time (5 minutes so far; usual time: 2 minutes). This step is outside the processing of Business Permits & Licensing Office. Please follow up with City Treasurer’s Office.
- FIL (draft): Ang aplikasyon ninyo na CG-SIM-0109 para sa Occupational Permit ay naghihintay sa ibang ahensya (City Treasurer’s Office) nang mas matagal kaysa karaniwan (5 minuto na; karaniwang oras: 2 minuto). Hindi ito kasama sa pagproseso ng Business Permits & Licensing Office. Makipag-ugnayan po sa City Treasurer’s Office.

**missing_data_flag**

- EN: DATA FLAG for Business Permits & Licensing Office: application CG-SIM-0201 (Business Permit) has timestamp problems (step 3: no start time recorded). Time cannot be measured for these steps and nothing has been assumed. Please correct the record.
- FIL (draft): BABALA SA DATOS para sa Business Permits & Licensing Office: ang aplikasyon CG-SIM-0201 (Business Permit) ay may problema sa oras (hakbang 3: walang naitalang oras ng simula). Hindi masusukat ang oras sa mga hakbang na ito at walang ipinagpalagay. Pakiayos po ang talaan.

`tests/test_core2_notes.py` fails if a string above drifts from the code.

## 10. Files, commands, change log

* Code: `src/citizengraph/core2/` (`calendar`, `config`, `models`, `store`, `sla`, `tools`,
  `alerts`, `simulator`, `runtime`, `baseline`, `agent`, `grammar`, `scripted`, `eval`, `report`, `traces`).
  Config: `config/core2.yaml` (not `limits.yaml`, `sla.yaml` or `calendar.yaml`, which are only read).
  Data: `eval/core2/scenarios/`. Tests: `tests/test_core2*.py` (+ helpers `test_core2_support.py`, `test_core2_gbnf_regex.py`).
* `python -m citizengraph.core2.eval [-v] [--runner baseline scripted]`: results table.
* `python -m citizengraph.core2.traces --out data/simulated/core2_gold_traces.jsonl --apps 200 --seed 9000`:
  synthetic chat-format gold trajectories (`data/simulated/` is not tracked; do not commit output).
  Trajectories come from simulator populations; seeds used by scenarios are refused.
* Not wired into the API. `core2/report.py::to_chat_response` builds a `kind = "status"` (or
  `"fallback"`) `ChatResponse` from an `AgentResult` for whoever wires it later.
* The alert store is JSONL (or memory); the whole package never touches Neo4j and
  `tests/test_graph_write_boundary.py` still passes.

Change log (dated; the baseline section above is frozen):

* 2026-09-30: baseline rules frozen (section 2) before the scenarios were written.
* 2026-09-30: the baseline was made to obey the same step budget as the agent (it returns the same safe
  fallback when the budget runs out). Harness constraint added while the agent's cap was implemented,
  still before any scenario existed; not a change to rules B1 to B10.
* 2026-09-30: first full run showed the baseline missing M05 only because the gold demanded an incidental
  reason (`day_type_unknown`); gold reasons for M05 and M06 were trimmed to the essential reasons.
  The baseline was not changed.
* 2026-09-30: tool outputs and the prompt preamble were shortened (the four-application scenario did
  not fit the prompt budget). No rule changed.

## 11. Questions for the adviser or the LGU

1. Are the SIMPLE (3) and COMPLEX (7) working-day caps in `config/sla.yaml` right, and how does a
   legally required posting period count against them?
2. Calendar or working days for the 10-day posting, the "1 week" referral step and the 3-day sanitary
   inspection?
3. LGU office hours, so minute-level steps can be measured across a night?
4. Should PSA mailing/issuance and the marriage-license seminar be marked external in the seed?
5. Which role is "the head" to escalate to, per office? Is `minor_delay_ratio` 1.5 acceptable?
6. Is holding alerts on a declared suspension day (rule R7) the wanted behaviour?
