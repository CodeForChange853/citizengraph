"""The scenario set, the scoring, and the harness. No model, GPU, network or Neo4j."""

import json
from collections import Counter

import pytest
from core2_helpers import graph

from citizengraph.core2.agent import ReActAgent
from citizengraph.core2.baseline import RuleBasedAgent
from citizengraph.core2.eval import (
    ALL_TOOLS,
    build_case,
    evaluate,
    format_table,
    load_scenarios,
    main,
    make_runner,
    score_run,
    summarize,
)
from citizengraph.core2.runtime import Task
from citizengraph.core2.scripted import ScriptedPolicy
from citizengraph.core2.simulator import Simulator
from citizengraph.llm.fake import FakeLLM

SCENARIOS = load_scenarios()
BY_ID = {s.id: s for s in SCENARIOS}

# The frozen baseline (docs/core2_notes.md section 2) is expected to miss exactly these. If this
# set changes, the baseline rules or the scenarios changed: say so in the notes.
BASELINE_MISSES = {
    "M01_absent_signatory_suspension_missing_timestamp",
    "M02_earlier_timestamp_lost_current_on_time",
    "M03_earlier_timestamp_lost_statutory_overdue",
    "M04_completed_with_lost_timestamp",
    "M06_posting_period_over",
    "M09_suspension_today_holds_alerts",
    "M14_external_wait_and_lost_timestamp",
    "M18_minor_delay_and_lost_timestamp",
    "M20_posting_period_and_lost_timestamp",
    "M23_suspension_today_and_statutory_overdue",
}


class TestScenarioSet:
    def test_at_least_forty_with_unique_ids(self):
        assert len(SCENARIOS) >= 40
        assert len({s.id for s in SCENARIOS}) == len(SCENARIOS)

    def test_categories_and_kinds_are_covered(self):
        cats = Counter(s.category for s in SCENARIOS)
        assert set(cats) == {"easy", "messy", "sweep", "calendar"}
        assert cats["easy"] >= 10 and cats["messy"] >= 15
        kinds = {s.task["kind"] for s in SCENARIOS}
        assert kinds == {"status", "office_sweep", "working_days", "suspension_check"}

    def test_the_named_messy_combinations_exist(self):
        assert "M01_absent_signatory_suspension_missing_timestamp" in BY_ID
        assert "M05_external_wait_beside_a_posting_period" in BY_ID
        assert BY_ID["M10_four_applications_one_citizen"].gold["applications"].keys() >= {
            "A1",
            "A2",
        }
        situations = {a.get("situation") for s in SCENARIOS for a in s.apps}
        assert {"on_time", "minor_delay", "over_charter", "overdue_statutory", "external_waiting",
                "external_over", "completed"} <= situations  # fmt: skip
        injected = {i for s in SCENARIOS for a in s.apps for i in a.get("inject", [])}
        assert injected == {
            "missing_current",
            "missing_earlier",
            "role_unavailable",
            "extra_suspension",
        }

    @pytest.mark.parametrize("scn", SCENARIOS, ids=lambda s: s.id)
    def test_each_scenario_is_well_formed(self, scn):
        assert scn.required_tools and set(scn.required_tools) <= set(ALL_TOOLS)
        assert set(scn.allowed()) <= set(ALL_TOOLS)
        assert set(scn.required_tools) <= set(scn.allowed())
        assert scn.task_obj().kind == scn.task["kind"]
        assert ("answer" in scn.gold) != ("applications" in scn.gold)
        for a in scn.apps:
            assert {"id", "ref", "service"} <= set(a)
            if "stamps" in a:
                assert a["submitted"] and a["citizen"]
                assert len(a["stamps"]) <= len(graph().steps(a["service"]))
        want = scn.gold.get("applications", {})
        assert set(want) <= {a["id"] for a in scn.apps}
        for exp in want.values():
            assert exp["status"] and isinstance(exp.get("alerts", []), list)

    @pytest.mark.parametrize("scn", SCENARIOS, ids=lambda s: s.id)
    def test_the_case_builds_and_holds_only_simulated_data(self, scn):
        case = build_case(scn, graph())
        for app in case.sim.store.all():
            assert app.ref.startswith("CG-") and app.citizen_ref.startswith("CIT-")
        json.loads(case.sim.store.to_json())

    def test_no_holiday_is_invented_outside_scenario_fixtures(self):
        for scn in SCENARIOS:
            case = build_case(scn, graph())
            assert set(case.toolbox.calendar.holidays) == {
                __import__("datetime").date.fromisoformat(d) for d in scn.holidays
            }


class TestGoldMatchesTheSimulatorTruth:
    """The gold was written by hand from the injected situation. The simulator states what it
    built. Where a scenario is a plain simulator case the two must agree (independent check)."""

    @pytest.mark.parametrize(
        "scn", [s for s in SCENARIOS if s.check_truth and s.apps and s.task["kind"] != "office_sweep"],
        ids=lambda s: s.id,
    )  # fmt: skip
    def test_status_and_alerts(self, scn):
        sim = build_case(scn, graph()).sim
        for app_id, exp in scn.gold["applications"].items():
            spec = next(a for a in scn.apps if a["id"] == app_id)
            if "stamps" in spec:
                continue  # hand-built timeline: no simulator truth
            truth = sim.truth[app_id]
            assert exp["status"] == truth.status, app_id
            assert set(exp.get("alerts", [])) == set(truth.alerts), app_id


class TestReferencePolicyThroughTheHarness:
    def test_scripted_policy_passes_every_scenario(self):
        """Checks the loop, prompt, grammar, tools, simulator and gold agree. NOT model quality."""
        scores = evaluate(make_runner("scripted"), SCENARIOS, graph())
        assert [s.scenario for s in scores if not s.outcome] == []
        s = summarize(scores)
        assert (s.outcome, s.trajectory, s.fallback) == (1.0, 1.0, 0.0)
        assert s.false_alert == 0.0 and s.missed_alert == 0.0 and s.arg_ok == 1.0

    def test_declared_budgets_cover_the_reference_trajectory(self):
        for scn in SCENARIOS:
            case = build_case(scn, graph())
            res = ReActAgent(ScriptedPolicy()).run(scn.task_obj(), case.toolbox, scn.max_steps)
            assert res.stopped_reason == "final", scn.id
            assert res.steps <= (scn.max_steps or 8), scn.id

    def test_default_cap_is_enough_for_the_typical_scenario(self):
        default = [s for s in SCENARIOS if s.max_steps is None]
        assert len(default) >= 25


class TestBaselineThroughTheHarness:
    def test_frozen_baseline_result_is_pinned(self):
        scores = evaluate(make_runner("baseline"), SCENARIOS, graph())
        missed = {s.scenario for s in scores if not s.outcome}
        assert missed == BASELINE_MISSES
        assert all(s.outcome for s in scores if s.category in ("easy", "calendar", "sweep"))

    def test_baseline_misses_are_data_and_rule_driven_not_crashes(self):
        for s in evaluate(make_runner("baseline"), SCENARIOS, graph()):
            assert not s.fallback, s.scenario


class TestScoring:
    def run(self, scn_id, llm_replies):
        scn = BY_ID[scn_id]
        case = build_case(scn, graph())
        res = ReActAgent(FakeLLM(llm_replies), name="fake").run(
            scn.task_obj(), case.toolbox, scn.max_steps
        )
        return score_run(scn, case, res)

    def act(self, tool, **args):
        return json.dumps({"tool": tool, "args": args})

    def fin(self, status, alerts=(), reasons=(), app_id="A1"):
        return json.dumps({"final": {"applications": [
            {"app_id": app_id, "status": status, "reasons": list(reasons), "alerts": list(alerts)}]}})  # fmt: skip

    def test_correct_answer_without_the_required_tools_is_not_a_trajectory_success(self):
        s = self.run("E01_on_time_business_permit", [self.fin("on_track")])
        assert s.outcome and not s.trajectory and s.required_hit == 0

    def test_wrong_status_fails_the_outcome(self):
        s = self.run("E01_on_time_business_permit", [self.fin("delayed", ["citizen_delay_notice"])])
        assert not s.outcome and any("status" in p for p in s.problems)

    def test_reported_alerts_must_match_what_was_actually_drafted(self):
        s = self.run(
            "E06_overdue_statutory",
            [self.fin("overdue_statutory", ["citizen_delay_notice", "department_head_escalation"])],
        )
        assert not s.outcome and s.missed_alert_apps == 1  # claimed but never drafted

    def test_false_alert_is_counted_from_the_alert_store(self):
        replies = [
            self.act("get_applications", ref="CG-SIM-0104"),
            self.act("draft_alert", app_id="A1", kind="citizen_delay_notice"),
            self.act("draft_alert", app_id="A1", kind="department_head_escalation"),
            self.fin("delayed", ["citizen_delay_notice", "department_head_escalation"]),
        ]
        s = self.run("E04_delayed_signatory_present", replies)
        assert s.false_alert_apps == 1 and not s.outcome

    def test_refused_draft_is_reported_but_writes_nothing(self):
        replies = [
            self.act("draft_alert", app_id="A1", kind="missing_data_flag"),
            self.fin("on_track"),
        ]
        s = self.run("E01_on_time_business_permit", replies)
        assert s.refused_drafts == 1 and s.false_alert_apps == 0 and s.outcome

    def test_argument_correctness_checks_the_entity_not_just_the_shape(self):
        replies = [
            self.act("get_applications", ref="CG-SIM-0999"),  # valid shape, wrong reference
            self.act("get_workflow_state", app_id="A1"),
            self.act("working_days_elapsed", start="2026-3-1", end="2026-03-02"),  # invalid
            self.fin("on_track"),
        ]
        s = self.run("E01_on_time_business_permit", replies)
        assert (s.calls, s.arg_ok_calls) == (3, 1)

    def test_tool_selection_counts_calls_outside_the_allowed_set(self):
        replies = [
            self.act("list_overdue", office_id="bplo", as_of="2026-03-04T14:00"),
            self.act("get_applications", ref="CG-SIM-0101"),
            self.fin("on_track"),
        ]
        s = self.run("E01_on_time_business_permit", replies)
        assert (s.calls, s.allowed_calls) == (2, 1)

    def test_a_model_that_only_produces_garbage_falls_back_safely(self):
        s = self.run("E01_on_time_business_permit", ["nope"] * 4)
        assert s.fallback and not s.outcome and s.steps <= 1 + 1

    def test_calendar_answer_is_compared_exactly(self):
        ok = json.dumps({"final": {"answer": {"working_days": 4}}})
        bad = json.dumps({"final": {"answer": {"working_days": 5}}})
        assert self.run(
            "C01_working_days_plain_week",
            [self.act("working_days_elapsed", start="2026-03-02", end="2026-03-06"), ok],
        ).trajectory
        assert not self.run("C01_working_days_plain_week", [bad]).outcome


class TestSummaryAndCli:
    def test_summary_numbers(self):
        scores = evaluate(make_runner("baseline"), SCENARIOS[:6], graph())
        s = summarize(scores)
        assert s.n == 6 and 0 <= s.outcome <= 1
        assert "baseline" in format_table([s])

    def test_the_table_prints_both_runners_and_the_disclaimer(self, capsys):
        assert main([]) == 0
        out = capsys.readouterr().out
        assert "baseline" in out and "scripted-policy" in out
        assert "NOT a measure of language-model quality" in out
        assert "outcome by category" in out

    def test_verbose_lists_the_misses(self, capsys):
        main(["--runner", "baseline", "-v"])
        out = capsys.readouterr().out
        assert "M01_absent_signatory_suspension_missing_timestamp" in out

    def test_any_llm_client_can_be_evaluated(self):
        agent = ReActAgent(FakeLLM(["nope"] * 500), name="fake-llm")
        s = summarize(evaluate(agent, SCENARIOS[:4], graph()))
        assert s.runner == "fake-llm" and s.fallback == 1.0 and s.outcome == 0.0

    def test_runner_names(self):
        assert isinstance(make_runner("baseline"), RuleBasedAgent)
        with pytest.raises(ValueError):
            make_runner("gpt")

    def test_simulator_and_task_types_are_importable_from_the_harness_module(self):
        assert Simulator and Task
