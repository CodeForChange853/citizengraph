"""The GBNF grammar string for llama.cpp: checked by transpiling it to a regex."""

import json

import pytest
from test_core2_gbnf_regex import parse_rules, referenced, to_regex
from test_core2_support import dt, toolbox

from citizengraph.core2.grammar import build_grammar
from citizengraph.core2.models import ALERT_KINDS, STATUSES

TB = toolbox(now=dt(3, 10, 17))
GRAMMAR = build_grammar(TB)
RX = to_regex(GRAMMAR)

VALID_ACTIONS = [
    {"tool": "get_applications", "args": {"ref": "CG-SIM-0001"}},
    {"tool": "get_workflow_state", "args": {"app_id": "A0001"}},
    {
        "tool": "get_step_sla",
        "args": {"service_id": "business_permit", "step_id": "business_permit-S08"},
    },
    {
        "tool": "get_step_sla",
        "args": {"service_id": "business_permit", "step_id": "business_permit-S08", "app_id": "A1"},
    },
    {"tool": "working_days_elapsed", "args": {"start": "2026-03-02", "end": "2026-03-06"}},
    {"tool": "check_work_suspension", "args": {"date": "2026-03-04"}},
    {"tool": "get_step_roles", "args": {"step_id": "business_permit-S08"}},
    {
        "tool": "get_role_availability",
        "args": {"role": "Any authorized City Treasurer’s Office collector", "date": "2026-03-03"},
    },
    {"tool": "list_overdue", "args": {"office_id": "bplo", "as_of": "2026-03-03T10:17"}},
    *({"tool": "draft_alert", "args": {"app_id": "A1", "kind": k}} for k in ALERT_KINDS),
    {"final": {"applications": []}},
    {"final": {"applications": [], "reasons": ["no_application_found"]}},
    {
        "final": {
            "applications": [
                {
                    "app_id": "A1",
                    "status": "delayed",
                    "reasons": ["role_unavailable"],
                    "alerts": ["citizen_delay_notice", "department_head_escalation"],
                }
            ]
        }
    },
    {"final": {"answer": {"working_days": 3}}},
    {"final": {"answer": {"suspended": False}}},
]


class TestWellFormed:
    def test_every_referenced_rule_is_defined(self):
        rules = parse_rules(GRAMMAR)
        assert "root" in rules
        for body in rules.values():
            assert referenced(body) <= set(rules)

    def test_names_every_tool_status_and_alert_kind(self):
        for name in TB.specs:
            assert f'\\"{name}\\"' in GRAMMAR
        for word in (*STATUSES, *ALERT_KINDS):
            assert f'\\"{word}\\"' in GRAMMAR

    def test_is_deterministic(self):
        assert build_grammar(TB) == GRAMMAR


class TestAcceptsValidActions:
    @pytest.mark.parametrize(
        "action", VALID_ACTIONS, ids=lambda a: next(iter(a)) + str(len(str(a)))
    )
    def test_compact_and_pretty(self, action):
        assert RX.fullmatch(json.dumps(action, separators=(",", ":"), ensure_ascii=False))
        assert RX.fullmatch(json.dumps(action, ensure_ascii=False))
        assert RX.fullmatch(json.dumps(action, indent=2, ensure_ascii=False))

    def test_optional_thought_first(self):
        text = json.dumps(
            {"thought": "check the record", "tool": "get_workflow_state", "args": {"app_id": "A1"}}
        )
        assert RX.fullmatch(text)


class TestRejectsWhatCannotBeRun:
    @pytest.mark.parametrize(
        "text",
        [
            '{"tool":"delete_application","args":{"app_id":"A1"}}',
            '{"tool":"get_workflow_state","args":{}}',
            '{"tool":"get_workflow_state","args":{"app_id":"A1","extra":"x"}}',
            '{"tool":"get_workflow_state","args":{"app_id":5}}',
            '{"tool":"draft_alert","args":{"app_id":"A1","kind":"shout"}}',
            '{"tool":"working_days_elapsed","args":{"start":"2026-3-2","end":"2026-03-06"}}',
            '{"tool":"list_overdue","args":{"office_id":"bplo","as_of":"2026-03-03"}}',
            '{"tool":"get_applications","args":{"ref":"a b"}}',
            '{"final":{"applications":[{"app_id":"A1","status":"maybe","reasons":[],"alerts":[]}]}}',
            '{"final":{"applications":[{"app_id":"A1","status":"delayed","reasons":["x"],"alerts":[]}]}}',
            '{"final":{"answer":{"working_days":-1}}}',
            '{"final":{"answer":{"working_days":"3"}}}',
            '{"final":"done"}',
            '{"tool":"get_applications","args":{"ref":"A1"}} {"final":{"applications":[]}}',
            'Sure! {"tool":"get_applications","args":{"ref":"A1"}}',
            "```json\n{}\n```",
            "",
        ],
    )
    def test_rejected(self, text):
        assert not RX.fullmatch(text)
