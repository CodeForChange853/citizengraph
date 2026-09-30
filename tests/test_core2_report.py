"""AgentResult -> the API's kind "status" response (templates only, EN and FIL draft)."""

import pytest
from graph_fixtures import staff_names
from test_core2_support import graph

from citizengraph.api.schemas import ChatResponse
from citizengraph.core2.agent import ReActAgent
from citizengraph.core2.eval import build_case, load_scenarios
from citizengraph.core2.report import FILIPINO_STRINGS, to_chat_response
from citizengraph.core2.scripted import ScriptedPolicy
from citizengraph.llm.fake import FakeLLM

BY_ID = {s.id: s for s in load_scenarios()}


def run(scn_id, llm=None):
    scn = BY_ID[scn_id]
    case = build_case(scn, graph())
    res = ReActAgent(llm or ScriptedPolicy()).run(scn.task_obj(), case.toolbox, scn.max_steps)
    return res, case.toolbox


def test_answer_is_a_status_response_the_frontend_contract_accepts():
    res, box = run("E04_delayed_signatory_present")
    out = to_chat_response(res, box, "en", session_id="s1")
    ChatResponse.model_validate(out.model_dump())
    assert out.kind == "status" and out.session_id == "s1" and out.language == "en"
    (section,) = out.sections
    assert section.service_name == "Business Permit"
    assert section.office.startswith("Business Permits")
    assert any("longer than" in n for n in section.notes)


def test_one_section_per_application():
    res, box = run("M10_four_applications_one_citizen")
    out = to_chat_response(res, box, "en")
    assert len(out.sections) == 4 and out.kind == "status"


@pytest.mark.parametrize(
    "scn_id", sorted(k for k, s in BY_ID.items() if s.task["kind"] == "status")
)
def test_every_status_scenario_renders_in_both_languages_without_staff_names(scn_id):
    res, box = run(scn_id)
    names = staff_names(graph().seed)
    en = to_chat_response(res, box, "en")
    fil = to_chat_response(res, box, "fil")
    for out in (en, fil):
        blob = out.model_dump_json()
        assert not any(n in blob for n in names)
        assert "RA 11032" not in blob  # the unverified statutory cap is never shown as law
    if res.final.get("applications"):
        assert en.sections[0].notes != fil.sections[0].notes


def test_external_wait_names_the_agency_and_says_it_is_not_the_offices_delay():
    res, box = run("E09_external_wait_over_stated_time")
    (note,) = to_chat_response(res, box, "en").sections[0].notes
    assert "City Treasurer’s Office" in note and "outside" in note


def test_cannot_determine_asks_the_citizen_to_check_with_the_office():
    res, box = run("E07_missing_current_timestamp")
    (note,) = to_chat_response(res, box, "en").sections[0].notes
    assert "check with the office" in note.lower()
    assert "2026" not in note  # no invented or echoed dates


def test_nothing_found():
    res, box = run("E12_no_such_application")
    out = to_chat_response(res, box, "en")
    assert out.kind == "status" and out.sections == [] and "could not find" in out.text


def test_agent_fallback_becomes_the_fallback_kind_with_the_safe_message():
    scn = BY_ID["E01_on_time_business_permit"]
    case = build_case(scn, graph())
    res = ReActAgent(FakeLLM(["x"] * 4)).run(scn.task_obj(), case.toolbox)
    out = to_chat_response(res, case.toolbox, "en")
    assert out.kind == "fallback" and "check with the office" in out.text.lower()
    fil = to_chat_response(res, case.toolbox, "fil")
    assert fil.kind == "fallback" and fil.text != out.text


def test_calendar_tasks_are_not_citizen_answers():
    res, box = run("C01_working_days_plain_week")
    with pytest.raises(ValueError):
        to_chat_response(res, box, "en")


def test_filipino_strings_are_listed_for_review():
    assert len(FILIPINO_STRINGS) >= 10 and len(set(FILIPINO_STRINGS)) == len(FILIPINO_STRINGS)
