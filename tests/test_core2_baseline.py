"""The frozen rule-based baseline, one test per rule B1..B10 (hand-built applications, not the
evaluation scenarios)."""

import pytest
from core2_helpers import chain, dt, fixture_calendar, make_app, toolbox

from citizengraph.core2.baseline import RuleBasedAgent
from citizengraph.core2.runtime import Task, validate_final
from citizengraph.core2.store import AlertStore

BP = "business_permit"


def run(apps, now, **kw):
    alerts = AlertStore()
    tb = toolbox(apps, now=now, alerts=alerts, **kw)
    task = Task(kind="status", now=now.strftime("%Y-%m-%dT%H:%M"), ref="CG-SIM-0001")
    res = RuleBasedAgent().run(task, tb)
    assert validate_final(res.final) == []
    return res, alerts


def only(res):
    (app,) = res.final["applications"]
    return app


def test_no_application():
    res, _ = run([], dt(3, 10))
    assert res.final == {"applications": [], "reasons": ["no_application_found"]}
    assert res.steps == 2 and res.stopped_reason == "final"  # one tool call + the final answer


def test_b1_any_timestamp_issue_stops_at_a_flag():
    stamps = chain(dt(3, 9), [2, 2], open_last=False)
    res, alerts = run([make_app(BP, stamps)], dt(3, 9, 30))
    a = only(res)
    assert (a["status"], a["alerts"]) == ("cannot_determine", ["missing_data_flag"])
    assert [x.kind for x in alerts.all()] == ["missing_data_flag"]


def test_b2_completed():
    n = len(__import__("core2_helpers").graph().steps("occupational_permit"))
    res, _ = run(
        [make_app("occupational_permit", chain(dt(3, 9), [1] * n, open_last=False))], dt(3, 12)
    )
    assert only(res)["status"] == "completed"


def test_b3_external_wait_over_the_stated_time_gets_a_notice():
    res, alerts = run([make_app("occupational_permit", chain(dt(3, 9), [2, 2, 40]))], dt(3, 10, 30))
    a = only(res)
    assert (a["status"], a["alerts"]) == ("external_waiting", ["external_wait_notice"])
    assert [x.kind for x in alerts.all()] == ["external_wait_notice"]


def test_b3_external_wait_without_a_stated_time_is_only_reported():
    stamps = chain(dt(3, 9), [2, 2, 5, 8, 300])  # treasurer payment, no charter time
    res, alerts = run([make_app(BP, stamps)], dt(3, 14))
    a = only(res)
    assert (a["status"], a["alerts"]) == ("external_waiting", [])
    assert alerts.all() == []


def test_b4_posting_is_waiting():
    stamps = chain(dt(3, 9), [5, 10, 5, 60 * 24 * 3])
    res, _ = run([make_app("birth_registration_delayed", stamps)], dt(6, 9, 20))
    assert only(res)["status"] == "waiting_posting"


def test_b5_suspension_pause():
    stamps = [(dt(2, 8), dt(2, 8, 5)), (dt(2, 9), None)]
    res, _ = run(
        [make_app("cho_sanitary_permit", stamps)],
        dt(6, 10),
        calendar=fixture_calendar(suspensions=[dt(3).date(), dt(4).date()]),
        day_types={"cho_sanitary_permit": "working"},
    )
    a = only(res)
    assert (a["status"], a["alerts"]) == ("paused_by_suspension", [])


def test_b6_statutory_overdue():
    res, _ = run([make_app(BP, chain(dt(2, 9), [2, 2, 3]))], dt(6, 9))
    a = only(res)
    assert a["status"] == "overdue_statutory"
    assert a["alerts"] == ["citizen_delay_notice", "department_head_escalation"]


def test_b7_delayed_with_present_signatory():
    stamps = chain(dt(3, 9), [2, 2, 5, 8, 20, 5, 5, 30])
    res, _ = run([make_app(BP, stamps)], dt(3, 10, 17))
    a = only(res)
    assert (a["status"], a["alerts"]) == ("delayed", ["citizen_delay_notice"])


def test_b7_delayed_with_absent_signatory_escalates():
    stamps = chain(dt(3, 9), [2, 2, 5, 8, 20, 5, 5, 30])
    res, _ = run([make_app(BP, stamps)], dt(3, 10, 17), absences=[("BPLO Chief", dt(3).date())])
    a = only(res)
    assert a["alerts"] == ["citizen_delay_notice", "department_head_escalation"]
    assert "role_unavailable" in a["reasons"]


def test_b8_minor_and_b9_on_track():
    stamps = chain(dt(3, 9), [2, 2, 5, 8, 20, 5, 5, 4])
    assert (
        only(run([make_app(BP, stamps)], dt(3, 9, 53))[0])["status"] == "minor_delay"
    )  # 6 min in a 3-5 min step
    stamps = chain(dt(3, 9), [2, 2, 3])
    assert only(run([make_app(BP, stamps)], dt(3, 9, 8))[0])["status"] == "on_track"


def test_b10_cannot_compare_day_based_step():
    stamps = chain(dt(3, 9), [30, 60 * 24])  # step 2 is "1 week" of unknown day type
    res, alerts = run([make_app("cswdo_referrals", stamps)], dt(4, 9, 30))
    a = only(res)
    assert a["status"] == "cannot_determine" and a["reasons"] == ["day_type_unknown"]
    assert alerts.all() == []


def test_several_applications_are_each_assessed():
    a = make_app(
        BP, chain(dt(3, 10, 10), [2, 2, 3]), app_id="A1", ref="CG-SIM-0001", citizen="CIT-1"
    )
    b = make_app(
        BP,
        chain(dt(3, 9), [2, 2, 5, 8, 20, 5, 5, 30]),
        app_id="A2",
        ref="CG-SIM-0002",
        citizen="CIT-1",
    )
    res = RuleBasedAgent().run(
        Task(kind="status", now="2026-03-03T10:17", ref="CIT-1"),
        toolbox([a, b], now=dt(3, 10, 17)),
        max_steps=20,  # several applications need more than the default 8 steps
    )
    assert [x["app_id"] for x in res.final["applications"]] == ["A1", "A2"]
    assert [x["status"] for x in res.final["applications"]] == ["on_track", "delayed"]


def test_sweep():
    late = make_app(BP, chain(dt(3, 9), [2, 2, 5, 8, 20, 5, 5, 30]), app_id="A1")
    fine = make_app(BP, chain(dt(3, 10, 10), [2, 2, 3]), app_id="A2", ref="CG-SIM-0002")
    tb = toolbox([late, fine], now=dt(3, 10, 17))
    res = RuleBasedAgent().run(
        Task(kind="office_sweep", now="2026-03-03T10:17", office_id="bplo"), tb
    )
    assert [a["app_id"] for a in res.final["applications"]] == ["A1"]
    assert validate_final(res.final) == []


def test_calendar_tasks():
    tb = toolbox(now=dt(3, 10), calendar=fixture_calendar(holidays=[dt(4).date()]))
    r = RuleBasedAgent().run(
        Task(kind="working_days", now="2026-03-03T10:00", start="2026-03-02", end="2026-03-06"), tb
    )
    assert r.final == {"answer": {"working_days": 3}}
    r = RuleBasedAgent().run(
        Task(kind="suspension_check", now="2026-03-03T10:00", date="2026-03-04"), tb
    )
    assert r.final == {"answer": {"suspended": False}}


def test_the_task_needs_its_fields():
    with pytest.raises(ValueError):
        Task(kind="status", now="2026-03-03T10:00")


def test_the_baseline_obeys_the_same_step_cap_as_the_agent():
    stamps = chain(dt(3, 9), [2, 2, 5, 8, 20, 5, 5, 30])
    tb = toolbox([make_app(BP, stamps)], now=dt(3, 10, 17))
    task = Task(kind="status", now="2026-03-03T10:17", ref="CG-SIM-0001")
    res = RuleBasedAgent().run(task, tb, max_steps=3)
    assert res.stopped_reason == "step_cap" and res.steps <= 3
    assert res.final["fallback"] == "check_with_office" and res.final["applications"] == []
    assert RuleBasedAgent().run(task, tb, max_steps=12).stopped_reason == "final"
