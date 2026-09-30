"""The nine Core 2 tools: strict arguments, compact read-only output, alerts to their own store."""

import json

import pytest
from graph_fixtures import staff_names
from test_core2_support import chain, dt, fixture_calendar, graph, make_app, toolbox

from citizengraph.core2.store import AlertStore
from citizengraph.core2.tools import ToolArgumentError, UnknownToolError

BP = "business_permit"
TOOLS = [
    "get_applications",
    "get_workflow_state",
    "get_step_sla",
    "working_days_elapsed",
    "check_work_suspension",
    "get_step_roles",
    "get_role_availability",
    "list_overdue",
    "draft_alert",
]


def late_signatory_app():
    """business_permit step 8 (BPLO Chief, 3-5 min) open for 30 minutes."""
    stamps = chain(dt(3, 9), [2, 2, 5, 8, 20, 5, 5, 30])
    return make_app(BP, stamps)


NOW = dt(3, 10, 17)


class TestRegistry:
    def test_exactly_the_specified_tools(self):
        tb = toolbox(now=NOW)
        assert sorted(tb.specs) == sorted(TOOLS)

    def test_every_tool_is_documented(self):
        for spec in toolbox(now=NOW).specs.values():
            assert len(spec.doc) > 20, spec.name
            assert all(p.doc for p in spec.params), spec.name

    def test_describe_lists_every_tool_compactly(self):
        text = toolbox(now=NOW).describe()
        assert all(name in text for name in TOOLS)
        assert len(text) < 2500

    def test_unknown_tool_is_refused(self):
        with pytest.raises(UnknownToolError):
            toolbox(now=NOW).call("delete_application", {"app_id": "A1"})


class TestArgumentValidation:
    @pytest.mark.parametrize(
        ("tool", "args"),
        [
            ("get_applications", {}),
            ("get_applications", {"ref": ""}),
            ("get_applications", {"ref": 5}),
            ("get_applications", {"ref": "CG-1", "extra": "x"}),
            ("get_applications", {"ref": "x" * 200}),
            ("get_applications", {"ref": "a b; DROP"}),
            ("get_workflow_state", {"app_id": None}),
            ("get_workflow_state", {"app_id": ["A1"]}),
            ("get_step_sla", {"service_id": BP}),
            ("get_step_sla", {"service_id": BP, "step_id": "x", "app_id": 3}),
            ("working_days_elapsed", {"start": "2026-3-4", "end": "2026-03-05"}),
            ("working_days_elapsed", {"start": "20260304", "end": "2026-03-05"}),
            ("working_days_elapsed", {"start": "March 4", "end": "2026-03-05"}),
            ("working_days_elapsed", {"start": "2026-02-30", "end": "2026-03-05"}),
            ("check_work_suspension", {"date": "2026-03-04T10:00"}),
            ("check_work_suspension", {"date": 20260304}),
            ("get_role_availability", {"role": "BPLO Chief", "date": "tomorrow"}),
            ("list_overdue", {"office_id": "bplo", "as_of": "2026-03-04"}),
            ("list_overdue", {"office_id": "bplo", "as_of": "2026-03-04T10:00+08:00"}),
            ("draft_alert", {"app_id": "A1", "kind": "shout_at_staff"}),
            ("draft_alert", {"app_id": "A1"}),
            ("draft_alert", {"app_id": "A1", "kind": True}),
        ],
    )
    def test_bad_arguments_raise_with_a_message_for_the_model(self, tool, args):
        with pytest.raises(ToolArgumentError) as exc:
            toolbox(now=NOW).call(tool, args)
        assert str(exc.value)

    def test_arguments_must_be_a_mapping(self):
        with pytest.raises(ToolArgumentError):
            toolbox(now=NOW).call("get_applications", ["CG-1"])  # type: ignore[arg-type]


class TestGetApplications:
    def test_by_reference_code_and_by_citizen(self):
        a = make_app(BP, chain(dt(3, 9), [2]), app_id="A1", ref="CG-SIM-0001", citizen="CIT-0001")
        b = make_app(BP, chain(dt(3, 9), [2]), app_id="A2", ref="CG-SIM-0002", citizen="CIT-0001")
        tb = toolbox([a, b], now=NOW)
        assert tb.call("get_applications", {"ref": "CG-SIM-0002"})["count"] == 1
        out = tb.call("get_applications", {"ref": "CIT-0001"})
        assert [r["app_id"] for r in out["applications"]] == ["A1", "A2"]
        assert set(out["applications"][0]) == {"app_id", "ref", "service_id", "submitted_at"}

    def test_unknown_reference_is_an_observation_not_an_exception(self):
        out = toolbox(now=NOW).call("get_applications", {"ref": "CG-NOPE"})
        assert out == {"ref": "CG-NOPE", "count": 0, "truncated": False, "applications": []}

    def test_row_limit(self):
        apps = [
            make_app(BP, chain(dt(3, 9), [2]), app_id=f"A{i}", ref=f"CG-SIM-{i:04d}")
            for i in range(1, 15)
        ]
        out = toolbox(apps, now=NOW).call("get_applications", {"ref": "CIT-0001"})
        assert out["count"] == 14 and len(out["applications"]) == 10 and out["truncated"]


class TestGetWorkflowState:
    def test_open_application(self):
        tb = toolbox([late_signatory_app()], now=NOW)
        out = tb.call("get_workflow_state", {"app_id": "A1"})
        assert out["current"]["step_id"] == "business_permit-S08"
        assert out["current"]["elapsed_min"] == 30.0
        assert out["complete"] is False and out["issues"] == []

    def test_reports_missing_timestamps(self):
        stamps = chain(dt(3, 9), [2, 2], open_last=False)
        out = toolbox([make_app(BP, stamps)], now=NOW).call("get_workflow_state", {"app_id": "A1"})
        assert out["issues"] == [
            {"step_id": "business_permit-S03", "problem": "missing_entered_at"}
        ]
        assert "elapsed_min" not in out["current"]

    def test_external_and_posting_flags(self):
        stamps = chain(dt(3, 9), [2, 2, 5, 8, 30])
        out = toolbox([make_app(BP, stamps)], now=NOW).call("get_workflow_state", {"app_id": "A1"})
        assert out["current"]["external"] == "City Treasurer’s Office"

    def test_unknown_application(self):
        out = toolbox(now=NOW).call("get_workflow_state", {"app_id": "A9"})
        assert out["error"] == "not_found"

    def test_output_is_compact(self):
        out = toolbox([late_signatory_app()], now=NOW).call("get_workflow_state", {"app_id": "A1"})
        assert len(json.dumps(out)) < 700


class TestGetStepSla:
    def test_charter_and_statutory_basis_are_labelled(self):
        out = toolbox(now=NOW).call("get_step_sla", {"service_id": BP, "step_id": f"{BP}-S08"})
        assert out["charter"]["basis"] == "charter_step_time"
        assert out["charter"]["allowed"] == 5.0
        assert out["statutory"]["basis"] == "statutory_cap_unverified"
        assert out["statutory"]["cap_working_days"] == 3
        assert "check" not in out

    def test_with_an_application_the_comparison_is_done_in_code(self):
        tb = toolbox([late_signatory_app()], now=NOW)
        out = tb.call("get_step_sla", {"service_id": BP, "step_id": f"{BP}-S08", "app_id": "A1"})
        assert out["check"]["charter"]["verdict"] == "over"
        assert out["check"]["charter"]["measured"] == 30.0
        assert out["check"]["charter"]["basis"] == "charter_step_time"
        assert "charter" not in out and "statutory" not in out  # static blocks only without an app
        assert out["check"]["statutory"]["verdict"] == "within"
        assert out["check"]["statutory"]["basis"] == "statutory_cap_unverified"

    def test_day_based_step_says_cannot_compare(self):
        out = toolbox(now=NOW).call(
            "get_step_sla",
            {
                "service_id": "birth_registration_delayed",
                "step_id": "birth_registration_delayed-S04",
            },
        )
        assert out["charter"]["comparable"] is False
        assert out["charter"]["reason"] == "day_type_unknown"
        assert out["posting"] is True

    def test_scenario_day_type_is_honoured(self):
        tb = toolbox(now=NOW, day_types={"birth_registration_delayed-S04": "calendar"})
        out = tb.call(
            "get_step_sla",
            {
                "service_id": "birth_registration_delayed",
                "step_id": "birth_registration_delayed-S04",
            },
        )
        assert out["charter"]["comparable"] is True and out["charter"]["kind"] == "calendar_days"

    def test_errors_are_observations(self):
        tb = toolbox([late_signatory_app()], now=NOW)
        assert tb.call("get_step_sla", {"service_id": "nope", "step_id": "x"})["error"] == (
            "not_found"
        )
        assert tb.call("get_step_sla", {"service_id": BP, "step_id": "x-S01"})["error"] == (
            "not_found"
        )
        wrong = tb.call(
            "get_step_sla",
            {
                "service_id": "occupational_permit",
                "step_id": "occupational_permit-S01",
                "app_id": "A1",
            },
        )
        assert wrong["error"] == "app_service_mismatch"

    def test_output_is_compact(self):
        tb = toolbox([late_signatory_app()], now=NOW)
        out = tb.call("get_step_sla", {"service_id": BP, "step_id": f"{BP}-S08", "app_id": "A1"})
        assert len(json.dumps(out)) < 800


class TestCalendarTools:
    def test_working_days_elapsed(self):
        tb = toolbox(now=NOW, calendar=fixture_calendar(holidays=[dt(4).date()]))
        out = tb.call("working_days_elapsed", {"start": "2026-03-02", "end": "2026-03-06"})
        assert out == {"start": "2026-03-02", "end": "2026-03-06", "working_days": 3}

    def test_reversed_range_is_an_error_observation(self):
        out = toolbox(now=NOW).call(
            "working_days_elapsed", {"start": "2026-03-06", "end": "2026-03-02"}
        )
        assert out["error"] == "end_before_start"

    def test_check_work_suspension(self):
        tb = toolbox(now=NOW, calendar=fixture_calendar(suspensions=[dt(4).date()]))
        out = tb.call("check_work_suspension", {"date": "2026-03-04"})
        assert out["suspended"] is True and out["working_day"] is False
        assert tb.call("check_work_suspension", {"date": "2026-03-05"})["suspended"] is False


class TestRoles:
    def test_step_roles(self):
        tb = toolbox(now=NOW)
        out = tb.call("get_step_roles", {"step_id": f"{BP}-S08"})
        assert out["roles"] == [{"role_id": "bplo-chief", "title": "BPLO Chief"}]

    def test_step_without_a_role_title_says_so(self):
        out = toolbox(now=NOW).call("get_step_roles", {"step_id": f"{BP}-S02"})
        assert out["roles"] == [] and "no role title" in out["note"]

    def test_unknown_step(self):
        assert (
            toolbox(now=NOW).call("get_step_roles", {"step_id": "zz-S01"})["error"] == "not_found"
        )

    def test_availability(self):
        tb = toolbox(now=NOW, absences=[("BPLO Chief", dt(3).date())])
        gone = tb.call("get_role_availability", {"role": "BPLO Chief", "date": "2026-03-03"})
        assert gone["available"] is False and "absent" in gone["reason"]
        assert tb.call("get_role_availability", {"role": "BPLO Chief", "date": "2026-03-04"})[
            "available"
        ]

    def test_role_can_be_given_by_id(self):
        tb = toolbox(now=NOW, absences=[("BPLO Chief", dt(3).date())])
        out = tb.call("get_role_availability", {"role": "bplo-chief", "date": "2026-03-03"})
        assert out["available"] is False and out["role"] == "BPLO Chief"

    def test_unknown_role_is_not_assumed_available(self):
        out = toolbox(now=NOW).call(
            "get_role_availability", {"role": "Mayor's Cousin", "date": "2026-03-03"}
        )
        assert out["error"] == "unknown_role"


class TestListOverdue:
    def apps(self):
        late = late_signatory_app()  # over charter
        ok = make_app(
            BP, chain(dt(3, 10, 10), [2, 2, 3]), app_id="A2", ref="CG-SIM-0002", citizen="CIT-2"
        )
        ext = make_app(
            BP, chain(dt(3, 9), [2, 2, 5, 8, 200]), app_id="A3", ref="CG-SIM-0003", citizen="CIT-3"
        )  # waiting at the treasurer: never an LGU delay
        health = make_app(
            "cho_dental_services",
            chain(dt(3, 9), [200]),
            app_id="A4",
            ref="CG-SIM-0004",
            citizen="CIT-4",
        )
        return [late, ok, ext, health]

    def test_lists_only_lgu_overdue_in_the_office(self):
        tb = toolbox(self.apps(), now=NOW)
        out = tb.call("list_overdue", {"office_id": "bplo", "as_of": "2026-03-03T10:17"})
        assert [r["app_id"] for r in out["overdue"]] == ["A1"]
        assert out["overdue"][0]["charter"] == "over"
        assert out["count"] == 1 and out["truncated"] is False

    def test_other_office(self):
        tb = toolbox(self.apps(), now=NOW)
        out = tb.call("list_overdue", {"office_id": "cho", "as_of": "2026-03-03T10:17"})
        assert [r["app_id"] for r in out["overdue"]] == ["A4"]

    def test_as_of_is_an_argument(self):
        tb = toolbox(self.apps(), now=NOW)
        early = tb.call("list_overdue", {"office_id": "bplo", "as_of": "2026-03-03T09:50"})
        assert early["overdue"] == []

    def test_statutory_overdue_is_listed(self):
        app = make_app(BP, chain(dt(2, 9), [2, 2, 3]), app_id="A9", ref="CG-SIM-0009")
        tb = toolbox([app], now=dt(6, 9))
        out = tb.call("list_overdue", {"office_id": "bplo", "as_of": "2026-03-06T09:00"})
        assert out["overdue"][0]["statutory"] == "over"

    def test_unknown_office(self):
        assert (
            toolbox(now=NOW).call(
                "list_overdue", {"office_id": "zzz", "as_of": "2026-03-03T12:00"}
            )["error"]
            == "not_found"
        )

    def test_row_limit(self):
        apps = [
            make_app(
                BP,
                chain(dt(3, 9), [2, 2, 5, 8, 20, 5, 5, 30]),
                app_id=f"A{i}",
                ref=f"CG-SIM-{i:04d}",
                citizen=f"CIT-{i}",
            )
            for i in range(1, 15)
        ]
        out = toolbox(apps, now=NOW).call(
            "list_overdue", {"office_id": "bplo", "as_of": "2026-03-03T10:17"}
        )
        assert out["count"] == 14 and len(out["overdue"]) == 10 and out["truncated"]


class TestDraftAlert:
    def test_writes_only_to_the_alert_store(self):
        alerts = AlertStore()
        tb = toolbox([late_signatory_app()], now=NOW, alerts=alerts)
        before = tb.store.to_json()
        out = tb.call("draft_alert", {"app_id": "A1", "kind": "citizen_delay_notice"})
        assert out["created"] is True and out["audience"] == "citizen"
        assert [a.kind for a in alerts.all()] == ["citizen_delay_notice"]
        assert tb.store.to_json() == before

    def test_second_identical_draft_is_not_stored_twice(self):
        alerts = AlertStore()
        tb = toolbox([late_signatory_app()], now=NOW, alerts=alerts)
        tb.call("draft_alert", {"app_id": "A1", "kind": "citizen_delay_notice"})
        again = tb.call("draft_alert", {"app_id": "A1", "kind": "citizen_delay_notice"})
        assert again["created"] is False and len(alerts.all()) == 1

    def test_alert_text_has_both_languages_and_no_staff_names(self):
        alerts = AlertStore()
        tb = toolbox(
            [late_signatory_app()], now=NOW, absences=[("BPLO Chief", NOW.date())], alerts=alerts
        )
        tb.call("draft_alert", {"app_id": "A1", "kind": "department_head_escalation"})
        (a,) = alerts.all()
        assert "BPLO Chief" in a.text_en and "absent" in a.text_en
        assert "BPLO Chief" in a.text_fil and a.text_fil != a.text_en
        assert "CG-SIM-0001" in a.text_en
        names = staff_names(graph().seed)
        assert names
        assert not any(n in a.text_en + a.text_fil for n in names)

    def test_statutory_limit_is_never_presented_as_law(self):
        alerts = AlertStore()
        app = make_app(BP, chain(dt(2, 9), [2, 2, 3]), app_id="A9", ref="CG-SIM-0009")
        tb = toolbox([app], now=dt(6, 9), alerts=alerts)
        tb.call("draft_alert", {"app_id": "A9", "kind": "department_head_escalation"})
        tb.call("draft_alert", {"app_id": "A9", "kind": "citizen_delay_notice"})
        by = {a.kind: a for a in alerts.all()}
        assert "NOT verified" in by["department_head_escalation"].text_en
        assert "RA 11032" not in by["citizen_delay_notice"].text_en
        assert "RA 11032" not in by["citizen_delay_notice"].text_fil

    @pytest.mark.parametrize(
        "kind",
        [
            "citizen_delay_notice",
            "department_head_escalation",
            "external_wait_notice",
            "missing_data_flag",
        ],
    )
    def test_alert_that_the_facts_do_not_support_is_refused(self, kind):
        on_time = make_app(BP, chain(dt(3, 9), [2, 2, 3]))
        alerts = AlertStore()
        tb = toolbox([on_time], now=dt(3, 9, 8), alerts=alerts)
        out = tb.call("draft_alert", {"app_id": "A1", "kind": kind})
        assert out["error"] == "not_applicable" and alerts.all() == []

    def test_external_wait_notice(self):
        app = make_app("occupational_permit", chain(dt(3, 9), [2, 2, 40]))
        alerts = AlertStore()
        tb = toolbox([app], now=dt(3, 10, 30), alerts=alerts)  # 86 min at a 2 min external step
        assert tb.call("draft_alert", {"app_id": "A1", "kind": "external_wait_notice"})["created"]
        assert "City Treasurer’s Office" in alerts.all()[0].text_en
        # never a citizen delay notice for an external wait
        refused = tb.call("draft_alert", {"app_id": "A1", "kind": "citizen_delay_notice"})
        assert refused["error"] == "not_applicable"

    def test_missing_data_flag(self):
        stamps = chain(dt(3, 9), [2, 2, 3])
        stamps[0] = (stamps[0][0], None)
        alerts = AlertStore()
        tb = toolbox([make_app(BP, stamps)], now=dt(3, 9, 12), alerts=alerts)
        assert tb.call("draft_alert", {"app_id": "A1", "kind": "missing_data_flag"})["created"]
        assert "step 1" in alerts.all()[0].text_en

    def test_unknown_application(self):
        out = toolbox(now=NOW).call("draft_alert", {"app_id": "A9", "kind": "missing_data_flag"})
        assert out["error"] == "not_found"


class TestReadOnly:
    def test_no_read_tool_changes_the_store_or_the_alerts(self):
        alerts = AlertStore()
        tb = toolbox([late_signatory_app()], now=NOW, alerts=alerts)
        before = tb.store.to_json()
        calls = [
            ("get_applications", {"ref": "CG-SIM-0001"}),
            ("get_workflow_state", {"app_id": "A1"}),
            ("get_step_sla", {"service_id": BP, "step_id": f"{BP}-S08", "app_id": "A1"}),
            ("working_days_elapsed", {"start": "2026-03-02", "end": "2026-03-06"}),
            ("check_work_suspension", {"date": "2026-03-04"}),
            ("get_step_roles", {"step_id": f"{BP}-S08"}),
            ("get_role_availability", {"role": "BPLO Chief", "date": "2026-03-03"}),
            ("list_overdue", {"office_id": "bplo", "as_of": "2026-03-03T10:17"}),
        ]
        for name, args in calls:
            tb.call(name, args)
        assert tb.store.to_json() == before and alerts.all() == []

    def test_every_output_is_json_and_small(self):
        tb = toolbox([late_signatory_app()], now=NOW)
        for name, args in [
            ("get_applications", {"ref": "CG-SIM-0001"}),
            ("get_workflow_state", {"app_id": "A1"}),
            ("list_overdue", {"office_id": "bplo", "as_of": "2026-03-03T10:17"}),
        ]:
            text = json.dumps(tb.call(name, args))
            assert len(text) < tb.config.max_observation_chars
