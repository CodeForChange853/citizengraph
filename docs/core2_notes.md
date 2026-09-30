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
