# Core 2 evaluation

Scenarios and harness for the SLA agent (RQ3). The harness code is `src/citizengraph/core2/eval.py`;
the design, the frozen baseline, the results and the limits are in `docs/core2_notes.md`.

```
python -m citizengraph.core2.eval          # baseline + ScriptedPolicy test double, results table
python -m citizengraph.core2.eval -v       # also list every scenario a runner gets wrong, and why
```

To score a real model, wrap it as an `LLMClient` and call
`evaluate(ReActAgent(llm, name="my-model"), load_scenarios())`, then `summarize` and `format_table`.
The `scripted-policy` row is a **test double** written by the scenario author: it checks the harness
and the loop, and says nothing about language-model quality.

## Scenario files (`scenarios/*.yaml`)

| File | Category | What |
|---|---|---|
| `01_easy.yaml` | easy | one application, one situation |
| `02_messy.yaml` | messy | several facts interact (absent signatory + suspension + lost timestamp, several applications, posting periods, external waits) |
| `03_sweep.yaml` | sweep | the department head asks which applications are overdue in an office |
| `04_calendar.yaml` | calendar | working days between two dates, is a date a declared suspension |

Each scenario: `id`, `title`, `category`, `seed`, `as_of` (the simulated clock, local time),
`task`, `apps`, `gold`, `required_tools`, and optionally `calendar` (fixture holidays and
suspensions, TEST ONLY), `day_types` (explicit calendar/working day type, otherwise unknown),
`absences` (role -> dates), `max_steps` (budget), `allowed_tools`, `check_truth: false`, `notes`.

* An `apps` entry with `situation` / `at_step` / `inject` is built by the simulator (see
  `core2/simulator.py` for the situations and injections). An entry with `stamps` (one
  `[entered, completed]` pair per step, `null` for a missing time) and `submitted` is a hand-built
  timeline. Every application needs an `id`, `ref` (fake, `CG-SIM-...`) and `service`.
* `gold.applications` maps application id to `status`, `alerts` (exact set) and optional `reasons`
  (a subset the answer must contain). `gold.reasons` is for "nothing found". Calendar tasks use
  `gold.answer`.
* Success needs the final answer, the reported alerts and the alerts actually written to the alert
  store to all match gold, with no fallback. `required_tools` decide "trajectory" success.

Data are simulated. The dates are a fixture (2026-03-02 is a Monday); no holiday here is real.
The gold was written by hand from the situations, not produced by any agent, model or the held-out
set (`eval/heldout/` is never read).
