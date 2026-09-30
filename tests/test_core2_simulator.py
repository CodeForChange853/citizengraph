"""The deterministic simulator of applications (no real citizen data)."""

import json
from datetime import timedelta

import pytest
from core2_helpers import dt, fixture_calendar, graph, toolbox
from graph_fixtures import staff_names

from citizengraph.core2.models import SIM_CODE
from citizengraph.core2.simulator import AppSpec, SimulationError, Simulator

AS_OF = dt(4, 14, 0)  # Wednesday 14:00, a working day
SITUATIONS = [
    "on_time",
    "minor_delay",
    "over_charter",
    "overdue_statutory",
    "suspension_pause",
    "external_waiting",
    "external_over",
    "completed",
]


def build(specs, seed=1, as_of=AS_OF, calendar=None):
    return Simulator(graph(), seed=seed).build(specs, as_of, calendar=calendar)


def outcome(sim, app_id):
    """What the exact tools say about one simulated application (independent of any agent)."""
    tb = toolbox(
        sim.store.all(), now=sim.as_of, calendar=sim.calendar, day_types=sim.day_types,
    )  # fmt: skip
    tb.store = sim.store
    state = tb.call("get_workflow_state", {"app_id": app_id})
    if state["complete"]:
        return state, None
    cur = state["current"]
    sla = tb.call(
        "get_step_sla",
        {"service_id": state["service_id"], "step_id": cur["step_id"], "app_id": app_id},
    )
    return state, sla["check"]


class TestDeterminism:
    def test_same_seed_same_data(self):
        a = build([AppSpec("business_permit", situation="over_charter")], seed=7)
        b = build([AppSpec("business_permit", situation="over_charter")], seed=7)
        assert a.store.to_json() == b.store.to_json()

    def test_different_seeds_differ_somewhere(self):
        dumps = {
            build(
                [AppSpec("business_permit", at_step=8, situation="on_time")], seed=s
            ).store.to_json()
            for s in range(6)
        }
        assert len(dumps) > 1

    def test_population_is_deterministic(self):
        a = Simulator(graph(), seed=3).population(40, AS_OF)
        b = Simulator(graph(), seed=3).population(40, AS_OF)
        assert a.store.to_json() == b.store.to_json()
        assert a.truth == b.truth


class TestSafetyOfTheData:
    def test_codes_look_simulated_and_no_staff_names_are_present(self):
        pop = Simulator(graph(), seed=5).population(60, AS_OF)
        text = pop.store.to_json()
        for a in pop.store.all():
            assert (
                SIM_CODE.match(a.app_id) and SIM_CODE.match(a.ref) and SIM_CODE.match(a.citizen_ref)
            )
        assert not any(n in text for n in staff_names(graph().seed))

    def test_serializes_to_plain_json(self):
        pop = Simulator(graph(), seed=5).population(10, AS_OF)
        assert json.loads(pop.store.to_json())["applications"]


class TestSituationsMatchTheExactTools:
    @pytest.mark.parametrize("service", [s.id for s in graph().services()])
    @pytest.mark.parametrize("situation", SITUATIONS)
    def test_every_service_and_situation_builds_or_says_it_cannot(self, service, situation):
        try:
            sim = build([AppSpec(service, situation=situation)], seed=2)
        except SimulationError:
            pytest.skip("no step of this service can host that situation")
        (truth,) = sim.truth.values()
        state, check = outcome(sim, "A0001")
        if situation == "completed":
            assert state["complete"] and truth.status == "completed"
            return
        c, s = check["charter"], check["statutory"]
        if situation == "on_time":
            assert (c["verdict"], s["verdict"]) == ("within", "within")
        elif situation == "minor_delay":
            assert (c["verdict"], s["verdict"]) == ("minor_over", "within")
        elif situation == "over_charter":
            assert c["verdict"] == "over" and s["verdict"] == "within"
        elif situation == "overdue_statutory":
            assert c["verdict"] == "within" and s["verdict"] == "over"
        elif situation == "suspension_pause":
            assert s["verdict"] == "within" and s.get("suspension_effect") is True
        elif situation == "external_waiting":
            assert state["current"]["external"] and c["verdict"] in ("within", "not_comparable")
        elif situation == "external_over":
            assert state["current"]["external"] and c["verdict"] == "over"

    def test_at_least_most_services_can_host_the_basic_situations(self):
        for situation in ("on_time", "minor_delay", "over_charter"):
            ok = 0
            for svc in graph().services():
                try:
                    build([AppSpec(svc.id, situation=situation)])
                    ok += 1
                except SimulationError:
                    pass
            assert ok >= 20, (situation, ok)

    def test_truth_table(self):
        t = {
            s: next(iter(build([AppSpec("business_permit", situation=s)]).truth.values()))
            for s in ("on_time", "minor_delay", "over_charter", "overdue_statutory",
                      "suspension_pause")
        }  # fmt: skip
        assert (t["on_time"].status, t["on_time"].alerts) == ("on_track", frozenset())
        assert t["minor_delay"].status == "minor_delay" and t["minor_delay"].alerts == frozenset()
        assert t["over_charter"].status == "delayed"
        assert t["over_charter"].alerts == {"citizen_delay_notice"}
        assert t["overdue_statutory"].status == "overdue_statutory"
        assert t["overdue_statutory"].alerts == {
            "citizen_delay_notice",
            "department_head_escalation",
        }
        assert t["suspension_pause"].status == "paused_by_suspension"


class TestInjections:
    def test_role_unavailable_marks_the_current_role_absent_and_adds_escalation(self):
        sim = build([AppSpec("business_permit", at_step=8, situation="over_charter",
                             inject=("role_unavailable",))])  # fmt: skip
        assert sim.store.absence("BPLO Chief", AS_OF) is not None
        (truth,) = sim.truth.values()
        assert truth.alerts == {"citizen_delay_notice", "department_head_escalation"}

    def test_role_unavailable_needs_a_role(self):
        with pytest.raises(SimulationError):
            build([AppSpec("business_permit", at_step=2, inject=("role_unavailable",))])

    def test_missing_current_timestamp(self):
        sim = build([AppSpec("business_permit", at_step=4, inject=("missing_current",))])
        state, _ = outcome(sim, "A0001")
        assert state["issues"][0]["problem"] == "missing_entered_at"
        (truth,) = sim.truth.values()
        assert (truth.status, truth.alerts) == ("cannot_determine", {"missing_data_flag"})

    def test_missing_earlier_timestamp_keeps_the_current_step_assessable(self):
        sim = build([AppSpec("business_permit", at_step=8, situation="on_time",
                             inject=("missing_earlier",))])  # fmt: skip
        state, check = outcome(sim, "A0001")
        assert state["issues"] and check["charter"]["verdict"] == "within"
        (truth,) = sim.truth.values()
        assert (truth.status, truth.alerts) == ("on_track", {"missing_data_flag"})

    def test_extra_suspension_days_are_declared_in_the_calendar(self):
        sim = build([AppSpec("business_permit", at_step=8, situation="overdue_statutory",
                             inject=("extra_suspension",))])  # fmt: skip
        assert len(sim.calendar.suspensions) >= 1
        _, check = outcome(sim, "A0001")
        assert check["statutory"]["verdict"] == "over"  # suspension does not rescue this one

    def test_suspension_pause_declares_days_and_never_the_as_of_day(self):
        sim = build([AppSpec("business_permit", at_step=8, situation="suspension_pause")])
        assert sim.calendar.suspensions
        assert AS_OF.date() not in sim.calendar.suspensions

    def test_base_calendar_is_kept(self):
        base = fixture_calendar(holidays=[dt(3).date()])
        sim = build([AppSpec("business_permit", at_step=8, situation="suspension_pause")],
                    calendar=base)  # fmt: skip
        assert dt(3).date() in sim.calendar.holidays


class TestSeveralApplications:
    def test_one_citizen_can_have_several_applications(self):
        sim = build([
            AppSpec("business_permit", situation="on_time", citizen_ref="CIT-0100"),
            AppSpec("cho_dental_services", situation="over_charter", citizen_ref="CIT-0100"),
        ])  # fmt: skip
        found = sim.store.find("CIT-0100")
        assert len(found) == 2
        assert len({a.ref for a in found}) == 2


class TestTimelines:
    @pytest.mark.parametrize("seed", range(8))
    def test_timestamps_never_run_backwards_and_never_pass_as_of(self, seed):
        pop = Simulator(graph(), seed=seed).population(30, AS_OF)
        for a in pop.store.all():
            prev = a.submitted_at
            for e in a.entries:
                if e.entered_at:
                    assert e.entered_at >= prev - timedelta(seconds=1), a.app_id
                    assert e.entered_at <= AS_OF
                if e.entered_at and e.completed_at:
                    assert e.completed_at >= e.entered_at
                    prev = e.completed_at
                assert not e.completed_at or e.completed_at <= AS_OF

    def test_population_covers_every_situation(self):
        pop = Simulator(graph(), seed=11).population(300, AS_OF)
        statuses = {t.status for t in pop.truth.values()}
        assert {"on_track", "minor_delay", "delayed", "overdue_statutory", "external_waiting",
                "paused_by_suspension", "cannot_determine", "completed"} <= statuses  # fmt: skip
