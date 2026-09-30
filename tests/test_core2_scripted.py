"""ScriptedPolicy through the real loop, checked against the simulator's ground truth.

This tests the plumbing (prompt, grammar, loop, tools, simulator agree). It says NOTHING about how
well a language model would do: the policy is a test double written by the same author.
"""

import pytest
from core2_helpers import dt, fixture_calendar, graph
from gbnf_regex import to_regex

from citizengraph.core2.agent import ReActAgent, build_preamble, build_prompt
from citizengraph.core2.config import Core2Config, load_statutory_caps
from citizengraph.core2.grammar import build_grammar
from citizengraph.core2.runtime import Task, validate_final
from citizengraph.core2.scripted import ScriptedPolicy, parse_prompt, reference_plan
from citizengraph.core2.simulator import AppSpec, Simulator
from citizengraph.core2.store import AlertStore
from citizengraph.core2.tools import Toolbox

AS_OF = dt(4, 14, 0)


def box_for(sim, alerts=None):
    return Toolbox(
        graph=graph(),
        store=sim.store,
        calendar=sim.calendar,
        alerts=alerts or AlertStore(),
        config=Core2Config(),
        caps=load_statutory_caps(),
        now=sim.as_of,
        day_types=sim.day_types,
    )


def ask(sim, app_id, max_steps=14):
    app = sim.store.get(app_id)
    box = box_for(sim)
    task = Task(kind="status", now=sim.as_of.strftime("%Y-%m-%dT%H:%M"), ref=app.ref)
    return ReActAgent(ScriptedPolicy()).run(task, box, max_steps=max_steps), box


class TestPromptRoundTrip:
    def test_parse_prompt_recovers_task_and_history(self):
        sim = Simulator(graph(), 1).build([AppSpec("business_permit")], AS_OF)
        box = box_for(sim)
        task = Task(kind="status", now="2026-03-04T14:00", ref="CG-SIM-0001")
        hist = [('{"tool":"get_applications","args":{"ref":"CG-SIM-0001"}}', '{"count":1}')]
        got_task, got_hist = parse_prompt(build_prompt(task, build_preamble(box), hist))
        assert got_task == task
        assert got_hist == [
            ({"tool": "get_applications", "args": {"ref": "CG-SIM-0001"}}, {"count": 1})
        ]

    def test_the_policy_is_stateless(self):
        task = Task(
            kind="working_days", now="2026-03-04T14:00", start="2026-03-02", end="2026-03-06"
        )
        p = ScriptedPolicy()
        prompt = build_prompt(task, "pre", [])
        assert p.generate(prompt) == p.generate(prompt)


class TestAgainstSimulatorTruth:
    @pytest.mark.parametrize("seed", range(6))
    def test_population(self, seed):
        sim = Simulator(graph(), seed).population(60, AS_OF)
        rx = to_regex(build_grammar(box_for(sim)))
        for app in sim.store.all():
            res, _ = ask(sim, app.app_id)
            truth = sim.truth[app.app_id]
            assert res.stopped_reason == "final", (app.app_id, res.final)
            assert validate_final(res.final) == []
            (got,) = res.final["applications"]
            assert (got["status"], set(got["alerts"])) == (truth.status, set(truth.alerts)), (
                app.app_id, app.service_id, truth,
            )  # fmt: skip
            assert set(truth.reasons) <= set(got["reasons"]), (app.app_id, truth, got)
            for step in res.trace:
                assert rx.fullmatch(step.raw), step.raw

    def test_cap_of_eight_fits_the_typical_case(self):
        sim = Simulator(graph(), 3).build([AppSpec("business_permit", "over_charter")], AS_OF)
        res, _ = ask(sim, "A0001", max_steps=8)
        assert res.stopped_reason == "final" and res.steps <= 8


class TestMessyCombination:
    def test_absent_signatory_suspension_earlier_and_missing_timestamp(self):
        sim = Simulator(graph(), 5).build(
            [AppSpec("business_permit", "over_charter", at_step=8,
                     inject=("role_unavailable", "missing_earlier", "extra_suspension"))],
            AS_OF,
        )  # fmt: skip
        res, box = ask(sim, "A0001")
        (got,) = res.final["applications"]
        assert got["status"] == "delayed"
        assert set(got["alerts"]) == {
            "citizen_delay_notice",
            "department_head_escalation",
            "missing_data_flag",
        }
        assert {"role_unavailable", "missing_timestamp_earlier_step"} <= set(got["reasons"])
        assert {a.kind for a in box.alerts.all()} == set(got["alerts"])
        assert res.steps > 8  # needs more than the default cap: scenarios declare a budget

    def test_suspension_today_holds_the_alerts(self):
        base = fixture_calendar(suspensions=[AS_OF.date()])
        sim = Simulator(graph(), 5).build(
            [AppSpec("business_permit", "over_charter", at_step=8)], AS_OF, calendar=base
        )
        res, box = ask(sim, "A0001")
        (got,) = res.final["applications"]
        assert got["status"] == "paused_by_suspension" and got["reasons"] == ["suspension_today"]
        assert box.alerts.all() == []


class TestOtherTaskKinds:
    def test_no_application(self):
        sim = Simulator(graph(), 1).build([AppSpec("business_permit")], AS_OF)
        task = Task(kind="status", now="2026-03-04T14:00", ref="CG-SIM-9999")
        res = ReActAgent(ScriptedPolicy()).run(task, box_for(sim))
        assert res.final == {"applications": [], "reasons": ["no_application_found"]}

    def test_several_applications(self):
        sim = Simulator(graph(), 2).build(
            [AppSpec("business_permit", "on_time", citizen_ref="CIT-0100"),
             AppSpec("cho_dental_services", "over_charter", citizen_ref="CIT-0100")],
            AS_OF,
        )  # fmt: skip
        task = Task(kind="status", now="2026-03-04T14:00", ref="CIT-0100")
        res = ReActAgent(ScriptedPolicy()).run(task, box_for(sim), max_steps=14)
        assert [a["status"] for a in res.final["applications"]] == ["on_track", "delayed"]

    def test_office_sweep(self):
        sim = Simulator(graph(), 2).build(
            [AppSpec("business_permit", "over_charter"), AppSpec("business_permit", "on_time"),
             AppSpec("cho_dental_services", "over_charter")],
            AS_OF,
        )  # fmt: skip
        task = Task(kind="office_sweep", now="2026-03-04T14:00", office_id="bplo")
        res = ReActAgent(ScriptedPolicy()).run(task, box_for(sim), max_steps=14)
        assert [a["app_id"] for a in res.final["applications"]] == ["A0001"]

    def test_calendar_tasks(self):
        sim = Simulator(graph(), 1).build([AppSpec("business_permit")], AS_OF)
        box = box_for(sim)
        t = Task(kind="working_days", now="2026-03-04T14:00", start="2026-03-02", end="2026-03-06")
        assert ReActAgent(ScriptedPolicy()).run(t, box).final == {"answer": {"working_days": 4}}
        t = Task(kind="suspension_check", now="2026-03-04T14:00", date="2026-03-03")
        assert ReActAgent(ScriptedPolicy()).run(t, box).final == {"answer": {"suspended": False}}

    def test_reference_plan_is_a_generator_of_plain_actions(self):
        plan = reference_plan(Task(kind="status", now="2026-03-04T14:00", ref="CG-SIM-0001"))
        assert next(plan) == {"tool": "get_applications", "args": {"ref": "CG-SIM-0001"}}
