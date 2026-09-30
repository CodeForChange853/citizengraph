"""Exact SLA logic: workflow state, charter step check, statutory check."""

from datetime import timedelta

import pytest
from test_core2_support import chain, dt, fixture_calendar, graph, make_app

from citizengraph.core2.config import Core2Config, load_statutory_caps
from citizengraph.core2.sla import (
    allowance,
    check_statutory,
    check_step,
    workflow_state,
)

CFG = Core2Config()
CAPS = load_statutory_caps()
BP = "business_permit"  # SIMPLE, steps: 2,2,5,5-10,ext(-),5,5,3-5,2-3,- minutes


def step(service, n):
    return graph().steps(service)[n - 1]


class TestAllowance:
    def test_minutes_are_compared_on_the_max_of_the_range(self):
        a = allowance(step(BP, 4), "unknown")
        assert (a.comparable, a.kind, a.allowed_minutes) == (True, "clock", 10.0)

    def test_hours_are_converted(self):
        a = allowance(step("cswdo_referrals", 4), "unknown")  # 1 hour
        assert a.allowed_minutes == 60.0

    def test_not_stated_time_cannot_be_compared(self):
        a = allowance(step(BP, 5), "unknown")
        assert (a.comparable, a.reason) == (False, "charter_time_not_stated")

    def test_days_with_unknown_day_type_are_not_guessed(self):
        a = allowance(step("birth_registration_delayed", 4), "unknown")
        assert (a.comparable, a.reason) == (False, "day_type_unknown")

    def test_days_with_explicit_day_type(self):
        w = allowance(step("birth_registration_delayed", 4), "working")
        c = allowance(step("birth_registration_delayed", 4), "calendar")
        assert (w.kind, w.allowed_days) == ("working_days", 10.0)
        assert (c.kind, c.allowed_days) == ("calendar_days", 10.0)

    def test_week_needs_a_day_type_too(self):
        st = step("cswdo_referrals", 2)  # 1 week
        assert allowance(st, "unknown").reason == "day_type_unknown"
        assert allowance(st, "calendar").allowed_days == 7.0
        assert allowance(st, "working", weekend_len=2).allowed_days == 5.0


class TestWorkflowState:
    def test_current_step_is_the_open_one(self):
        app = make_app(BP, chain(dt(2, 9), [2, 2, 3]))
        s = workflow_state(app, graph())
        assert s.current.id == "business_permit-S03"
        assert s.issues == [] and not s.complete
        assert s.steps_done == 2

    def test_complete_when_last_step_is_finished(self):
        n = len(graph().steps("occupational_permit"))
        app = make_app("occupational_permit", chain(dt(2, 9), [2] * n, open_last=False))
        s = workflow_state(app, graph())
        assert s.complete and s.current is None

    def test_next_step_without_timestamps_is_a_missing_entered_at(self):
        app = make_app(BP, chain(dt(2, 9), [2, 2], open_last=False))
        s = workflow_state(app, graph())
        assert s.current.id == "business_permit-S03"
        assert [(i.step_id, i.problem) for i in s.issues] == [
            ("business_permit-S03", "missing_entered_at")
        ]

    def test_earlier_step_missing_completed_at(self):
        stamps = chain(dt(2, 9), [2, 2, 3])
        stamps[0] = (stamps[0][0], None)
        s = workflow_state(make_app(BP, stamps), graph())
        assert [(i.step_id, i.problem) for i in s.issues] == [
            ("business_permit-S01", "missing_completed_at")
        ]
        assert s.current.id == "business_permit-S03"

    def test_earlier_step_missing_entered_at(self):
        stamps = chain(dt(2, 9), [2, 2, 3])
        stamps[1] = (None, stamps[1][1])
        s = workflow_state(make_app(BP, stamps), graph())
        assert [(i.step_id, i.problem) for i in s.issues] == [
            ("business_permit-S02", "missing_entered_at")
        ]

    def test_completed_before_entered(self):
        stamps = chain(dt(2, 9), [2, 2, 3])
        stamps[0] = (stamps[0][0], stamps[0][0] - timedelta(minutes=5))
        s = workflow_state(make_app(BP, stamps), graph())
        assert s.issues[0].problem == "completed_before_entered"

    def test_application_with_no_entries_starts_at_step_one_with_no_timestamp(self):
        app = make_app(BP, [])
        s = workflow_state(app, graph())
        assert s.current.id == "business_permit-S01"
        assert s.issues[0].problem == "missing_entered_at"


class TestCharterCheck:
    def check(self, service, stamps, now, n, cal=None, overrides=None):
        app = make_app(service, stamps)
        st = step(service, n)
        return check_step(
            st,
            app.entry(st.id),
            now,
            service_id=service,
            calendar=cal or fixture_calendar(),
            day_types=overrides or {},
            config=CFG,
        )

    def test_within(self):
        c = self.check(BP, chain(dt(2, 9), [2, 2, 4]), dt(2, 9, 8), 3)  # 4 of 5 min
        assert c.verdict == "within" and c.elapsed_min == 4.0

    def test_boundary_is_within(self):
        c = self.check(BP, chain(dt(2, 9), [2, 2, 5]), dt(2, 9, 9), 3)
        assert c.verdict == "within"

    def test_minor_over(self):
        c = self.check(BP, chain(dt(2, 9), [2, 2, 7]), dt(2, 9, 11), 3)  # 7 of 5 (<= 7.5)
        assert c.verdict == "minor_over"

    def test_over(self):
        c = self.check(BP, chain(dt(2, 9), [2, 2, 8]), dt(2, 9, 12), 3)  # 8 of 5
        assert c.verdict == "over"

    def test_missing_entered_at(self):
        c = self.check(BP, chain(dt(2, 9), [2, 2], open_last=False), dt(2, 9, 12), 3)
        assert (c.verdict, c.reason) == ("not_comparable", "missing_timestamp")

    def test_not_stated_time(self):
        c = self.check(BP, chain(dt(2, 9), [2, 2, 3, 6, 40]), dt(2, 10), 5)
        assert (c.verdict, c.reason) == ("not_comparable", "charter_time_not_stated")

    def test_finished_step_is_measured_entered_to_completed(self):
        stamps = chain(dt(2, 9), [2, 2, 3])
        c = self.check(BP, stamps, dt(9, 9), 1)  # long after: only its own span counts
        assert c.elapsed_min == 2.0 and c.verdict == "within"

    def test_day_step_unknown_day_type_is_not_guessed(self):
        stamps = chain(dt(2, 9), [5, 10, 5, 60 * 24 * 12])
        c = self.check("birth_registration_delayed", stamps, dt(14, 9), 4)
        assert (c.verdict, c.reason) == ("not_comparable", "day_type_unknown")

    def test_day_step_with_calendar_days(self):
        stamps = chain(dt(2, 9), [5, 10, 5, 60 * 24 * 16])
        c = self.check(
            "birth_registration_delayed",
            stamps,
            dt(18, 9),
            4,
            overrides={"birth_registration_delayed-S04": "calendar"},
        )
        assert c.verdict == "over" and c.measured == pytest.approx(16, abs=0.05)  # 10 allowed
        c = self.check(
            "birth_registration_delayed",
            stamps,
            dt(14, 9),
            4,
            overrides={"birth_registration_delayed-S04": "calendar"},
        )
        assert c.verdict == "minor_over" and c.measured == pytest.approx(12, abs=0.05)

    def test_working_days_step_paused_by_suspension(self):
        # cho_sanitary_permit-S02: 3 days. Entered Mon 09:00, now Fri: 4 working days without
        # suspensions (over), 2 with Tue and Wed declared suspended (within).
        n = len(graph().steps("cho_sanitary_permit"))
        stamps = chain(dt(2, 9), [5, 60 * 24 * 4 + 60])[:2]
        assert n >= 2
        c = self.check(
            "cho_sanitary_permit",
            [(dt(2, 8), dt(2, 8, 5)), (dt(2, 9), None)],
            dt(6, 10),
            2,
            cal=fixture_calendar(suspensions=[dt(3).date(), dt(4).date()]),
            overrides={"cho_sanitary_permit": "working"},
        )
        assert stamps and c.kind == "working_days"
        assert c.verdict == "within" and c.suspension_effect is True and c.measured == 2

    def test_suspension_that_does_not_rescue_the_step_is_not_a_pause(self):
        c = self.check(
            "cho_sanitary_permit",
            [(dt(2, 8), dt(2, 8, 5)), (dt(2, 9), None)],
            dt(13, 10),  # 9 working days elapsed, 7 with two suspensions
            2,
            cal=fixture_calendar(suspensions=[dt(3).date(), dt(4).date()]),
            overrides={"cho_sanitary_permit": "working"},
        )
        assert c.verdict == "over" and c.suspension_effect is False


class TestStatutory:
    def check(self, service, stamps, now, cal=None, submitted=None):
        app = make_app(service, stamps, submitted=submitted)
        return check_statutory(
            app,
            graph(),
            now,
            calendar=cal or fixture_calendar(),
            caps=CAPS,
            config=CFG,
        )

    def test_simple_service_cap_is_three_working_days(self):
        stamps = chain(dt(2, 9), [2, 2, 3])
        assert self.check(BP, stamps, dt(5, 9)).verdict == "within"  # Thursday: 3 days
        r = self.check(BP, stamps, dt(6, 9))  # Friday: 4 days
        assert (r.verdict, r.cap, r.elapsed_working_days) == ("over", 3, 4)
        assert r.basis == "statutory_cap_unverified"

    def test_weekend_does_not_count(self):
        stamps = chain(dt(6, 9), [2, 2, 3])  # Friday
        assert self.check(BP, stamps, dt(9, 9)).verdict == "within"  # Monday = 1 day

    def test_suspension_days_pause_the_clock(self):
        stamps = chain(dt(2, 9), [2, 2, 3])
        cal = fixture_calendar(suspensions=[dt(3).date(), dt(4).date()])
        r = self.check(BP, stamps, dt(6, 9), cal)  # Friday: 4 - 2 = 2 working days
        assert (r.verdict, r.suspension_effect) == ("within", True)

    def test_external_wait_is_not_counted_against_the_lgu(self):
        # Treasurer payment (external) took Tue 09:00 to Fri 09:00 (3 working days).
        stamps = [
            (dt(2, 9), dt(2, 9, 2)),
            (dt(2, 9, 2), dt(2, 9, 4)),
            (dt(2, 9, 4), dt(2, 9, 9)),
            (dt(2, 9, 9), dt(3, 9)),
            (dt(3, 9), dt(6, 9)),  # S05 external
            (dt(6, 9), None),
        ]
        r = self.check(BP, stamps, dt(6, 12))
        assert r.external_days_excluded == 3
        assert r.elapsed_working_days == 1 and r.verdict == "within"

    def test_missing_timestamp_on_an_external_step_blocks_the_comparison(self):
        stamps = [
            (dt(2, 9), dt(2, 9, 2)),
            (dt(2, 9, 2), dt(2, 9, 4)),
            (dt(2, 9, 4), dt(2, 9, 9)),
            (dt(2, 9, 9), dt(3, 9)),
            (dt(3, 9), None),  # S05 external, entered, never closed
            (dt(6, 9), None),
        ]
        r = self.check(BP, stamps, dt(9, 12))
        assert (r.verdict, r.reason) == ("not_comparable", "missing_timestamp")

    def test_complex_service_has_the_longer_cap(self):
        stamps = chain(dt(2, 9), [5, 10, 5])
        assert self.check("birth_registration_delayed", stamps, dt(11, 9)).cap == 7

    def test_posting_period_makes_the_cap_not_comparable_once_started(self):
        stamps = chain(dt(2, 9), [5, 10, 5, 60 * 24 * 3])
        r = self.check("birth_registration_delayed", stamps, dt(5, 9))
        assert (r.verdict, r.reason) == ("not_comparable", "posting_period_treatment_unverified")

    def test_before_the_posting_step_the_cap_still_applies(self):
        stamps = chain(dt(2, 9), [5, 10, 60 * 24 * 9])  # stuck in step 3 for 9 days
        r = self.check("birth_registration_delayed", stamps, dt(13, 9))  # 9 working days > 7
        assert r.verdict == "over"

    def test_unknown_class_is_not_guessed(self):
        caps = CAPS.model_copy(update={"working_days": {}})
        app = make_app(BP, chain(dt(2, 9), [2, 2, 3]))
        r = check_statutory(app, graph(), dt(3), calendar=fixture_calendar(), caps=caps, config=CFG)
        assert (r.verdict, r.reason) == ("not_comparable", "cap_not_configured")


@pytest.mark.parametrize("service", [s.id for s in graph().services()])
def test_every_curated_service_has_a_chain_the_state_machine_can_walk(service):
    steps = graph().steps(service)
    app = make_app(service, chain(dt(2, 9), [1] * len(steps), open_last=False))
    s = workflow_state(app, graph())
    assert s.complete and s.issues == []
