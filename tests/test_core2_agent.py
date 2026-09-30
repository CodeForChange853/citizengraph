"""The ReAct loop, with scripted replies (FakeLLM) standing in for a model."""

import json

import pytest
from core2_helpers import chain, dt, make_app, toolbox

from citizengraph.core2.agent import (
    ActionError,
    ReActAgent,
    build_preamble,
    build_prompt,
    parse_action,
)
from citizengraph.core2.config import Core2Config
from citizengraph.core2.runtime import Task
from citizengraph.core2.store import AlertStore
from citizengraph.llm.fake import FakeLLM

BP = "business_permit"
NOW = dt(3, 10, 17)
TASK = Task(kind="status", now="2026-03-03T10:17", ref="CG-SIM-0001")


def tb(**kw):
    app = make_app(BP, chain(dt(3, 9), [2, 2, 5, 8, 20, 5, 5, 30]))
    return toolbox([app], now=NOW, **kw)


def act(tool, **args):
    return json.dumps({"tool": tool, "args": args})


def fin(**body):
    return json.dumps({"final": body or {"applications": []}})


class Spy(FakeLLM):
    def __init__(self, responses):
        super().__init__(responses)
        self.grammars: list[str | None] = []
        self.max_tokens: list[int] = []

    def generate(self, prompt, *, max_tokens=256, grammar=None):
        self.grammars.append(grammar)
        self.max_tokens.append(max_tokens)
        return super().generate(prompt, max_tokens=max_tokens, grammar=grammar)


class TestParseAction:
    def test_tool_and_final(self):
        assert parse_action(act("get_workflow_state", app_id="A1")) == {
            "tool": "get_workflow_state",
            "args": {"app_id": "A1"},
        }
        assert parse_action(' {"final": {"applications": []}} \n') == {
            "final": {"applications": []}
        }

    def test_optional_thought_is_dropped(self):
        got = parse_action('{"thought":"look","tool":"get_applications","args":{"ref":"x"}}')
        assert got == {"tool": "get_applications", "args": {"ref": "x"}}

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "hello",
            "```json\n{}\n```",
            "[]",
            "{}",
            '{"tool": "a"}',
            '{"tool": "a", "args": []}',
            '{"tool": 5, "args": {}}',
            '{"tool": "a", "args": {}, "final": {}}',
            '{"tool": "a", "args": {}, "extra": 1}',
            '{"final": {}} trailing',
            '{"thought": 5, "final": {}}',
            '{"final": NaN}',
            None,
        ],
    )
    def test_rejects(self, raw):
        with pytest.raises(ActionError):
            parse_action(raw)


class TestPrompt:
    def test_shape_and_size(self):
        box = tb()
        pre = build_preamble(box)
        text = build_prompt(TASK, pre, [('{"tool":"x","args":{}}', '{"ok":1}')])
        assert text.count("TASK:") == 1 and "ACTION 1:" in text and text.endswith("NEXT:")
        assert all(name in pre for name in box.specs)
        assert len(pre) < 4000

    def test_prompt_holds_only_the_controlled_task_not_free_text(self):
        assert TASK.brief() == '{"kind":"status","now":"2026-03-03T10:17","ref":"CG-SIM-0001"}'


class TestHappyPath:
    def test_runs_tools_then_finishes(self):
        llm = Spy(
            [
                act("get_workflow_state", app_id="A1"),
                fin(
                    applications=[
                        {"app_id": "A1", "status": "delayed", "reasons": [], "alerts": []}
                    ]
                ),
            ]
        )
        res = ReActAgent(llm).run(TASK, tb())
        assert res.stopped_reason == "final" and res.steps == 2 and res.llm_calls == 2
        assert [s.kind for s in res.trace] == ["tool", "final"]
        assert res.tool_calls == [("get_workflow_state", {"app_id": "A1"})]
        assert res.final["applications"][0]["status"] == "delayed"
        assert res.runner == "react"

    def test_grammar_and_token_limit_are_passed_to_the_model(self):
        llm = Spy([fin()])
        ReActAgent(llm).run(TASK, tb())
        assert "root ::=" in llm.grammars[0]
        assert llm.max_tokens == [Core2Config().max_tokens]

    def test_grammar_can_be_switched_off(self):
        llm = Spy([fin()])
        ReActAgent(llm, use_grammar=False).run(TASK, tb())
        assert llm.grammars == [None]

    def test_each_call_sees_the_whole_history(self):
        llm = Spy([act("get_applications", ref="CG-SIM-0001"), fin()])
        ReActAgent(llm).run(TASK, tb())
        assert "RESULT 1:" in llm.prompts[1] and '"count":1' in llm.prompts[1]
        assert "ACTION 1:" not in llm.prompts[0]

    def test_a_write_tool_call_lands_only_in_the_alert_store(self):
        alerts = AlertStore()
        box = tb(alerts=alerts)
        before = box.store.to_json()
        llm = Spy([act("draft_alert", app_id="A1", kind="citizen_delay_notice"), fin()])
        ReActAgent(llm).run(TASK, box)
        assert [a.kind for a in alerts.all()] == ["citizen_delay_notice"]
        assert box.store.to_json() == before


class TestInvalidJson:
    def test_one_retry_then_success(self):
        llm = Spy(["I think we should look", fin()])
        res = ReActAgent(llm).run(TASK, tb())
        assert res.stopped_reason == "final" and res.llm_calls == 2 and res.steps == 1
        assert [s.kind for s in res.trace] == ["invalid_json", "final"]
        assert "NOTE:" in llm.prompts[1] and "NOTE:" not in llm.prompts[0]

    def test_second_failure_is_the_safe_fallback(self):
        res = ReActAgent(FakeLLM(["nope", "still nope", fin()])).run(TASK, tb())
        assert res.stopped_reason == "invalid_json"
        assert res.final["fallback"] == "check_with_office" and res.final["applications"] == []
        assert res.llm_calls == 2

    def test_retry_count_is_configurable(self):
        cfg = Core2Config(invalid_json_retries=0)
        res = ReActAgent(FakeLLM(["nope", fin()]), config=cfg).run(TASK, tb())
        assert res.stopped_reason == "invalid_json" and res.llm_calls == 1


class TestObservationErrors:
    def test_invalid_arguments_go_back_to_the_model(self):
        llm = Spy(
            [
                act("working_days_elapsed", start="2026-3-2", end="2026-03-06"),
                act("working_days_elapsed", start="2026-03-02", end="2026-03-06"),
                fin(answer={"working_days": 4}),
            ]
        )
        res = ReActAgent(llm).run(TASK, tb())
        assert res.stopped_reason == "final"
        assert res.trace[0].kind == "invalid_args" and "YYYY-MM-DD" in res.trace[0].error
        assert '"error":"invalid_arguments"' in llm.prompts[1]
        assert res.trace[1].kind == "tool"

    def test_unknown_tool_is_refused_and_not_run(self):
        alerts = AlertStore()
        llm = Spy([act("delete_application", app_id="A1"), fin()])
        res = ReActAgent(llm).run(TASK, tb(alerts=alerts))
        assert res.trace[0].kind == "unknown_tool"
        assert res.trace[0].observation["error"] == "unknown_tool"
        assert "get_applications" in res.trace[0].observation["valid_tools"]
        assert res.stopped_reason == "final"

    def test_repeated_bad_actions_are_bounded(self):
        llm = FakeLLM([act("delete_application")] * 10)
        res = ReActAgent(llm).run(TASK, tb())
        assert res.stopped_reason == "invalid_action"
        assert res.steps == Core2Config().invalid_args_retries + 1
        assert res.final["fallback"] == "check_with_office"

    def test_invalid_final_is_returned_as_an_observation(self):
        llm = Spy(
            [
                fin(applications=[{"app_id": "A1", "status": "sad", "reasons": [], "alerts": []}]),
                fin(),
            ]
        )
        res = ReActAgent(llm).run(TASK, tb())
        assert res.trace[0].kind == "invalid_final" and res.stopped_reason == "final"
        assert "invalid_final" in llm.prompts[1]

    def test_content_errors_are_observations_and_do_not_use_the_retry_budget(self):
        llm = FakeLLM([act("get_workflow_state", app_id="A9")] * 4 + [fin()])
        cfg = Core2Config(max_steps=8)
        res = ReActAgent(llm, config=cfg).run(TASK, tb())
        assert res.stopped_reason == "final" and res.steps == 5

    def test_oversized_observation_is_replaced(self):
        cfg = Core2Config(max_observation_chars=100)
        llm = FakeLLM([act("get_workflow_state", app_id="A1"), fin()])
        res = ReActAgent(llm, config=cfg).run(TASK, tb())
        assert res.trace[0].observation["error"] == "observation_too_large"


class TestStepCap:
    def test_default_cap_is_eight_and_ends_in_the_safe_fallback(self):
        llm = FakeLLM([act("get_applications", ref="CG-SIM-0001")] * 20)
        res = ReActAgent(llm).run(TASK, tb())
        assert res.stopped_reason == "step_cap" and res.steps == 8
        assert res.final["fallback"] == "check_with_office"
        assert len(res.tool_calls) == 8

    def test_cap_can_be_overridden_per_run(self):
        llm = FakeLLM([act("get_applications", ref="CG-SIM-0001")] * 20)
        assert ReActAgent(llm).run(TASK, tb(), max_steps=3).steps == 3

    def test_finishing_on_the_last_step_is_fine(self):
        llm = FakeLLM([act("get_applications", ref="CG-SIM-0001")] * 2 + [fin()])
        assert ReActAgent(llm).run(TASK, tb(), max_steps=3).stopped_reason == "final"


class TestOtherFailures:
    def test_model_exception_is_a_safe_fallback(self):
        class Boom:
            def generate(self, prompt, *, max_tokens=256, grammar=None):
                raise RuntimeError("out of memory")

        res = ReActAgent(Boom()).run(TASK, tb())
        assert res.stopped_reason == "llm_error" and res.final["fallback"] == "check_with_office"

    def test_prompt_over_budget_never_reaches_the_model(self):
        llm = Spy([fin()])
        res = ReActAgent(llm, config=Core2Config(max_prompt_chars=1000)).run(TASK, tb())
        assert res.stopped_reason == "prompt_too_long" and llm.prompts == []


class TestTrajectoryLog:
    def test_every_run_is_appended_as_jsonl(self, tmp_path):
        p = tmp_path / "logs" / "traj.jsonl"
        agent = ReActAgent(
            FakeLLM([act("get_workflow_state", app_id="A1"), fin(), fin()]), log_path=p
        )
        agent.run(TASK, tb())
        agent.run(TASK, tb())
        rows = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines()]
        assert len(rows) == 2
        assert rows[0]["task"]["ref"] == "CG-SIM-0001" and rows[0]["stopped_reason"] == "final"
        assert [s["kind"] for s in rows[0]["trace"]] == ["tool", "final"]
        assert rows[0]["trace"][0]["observation"]["app_id"] == "A1"

    def test_fallback_runs_are_logged_too(self, tmp_path):
        p = tmp_path / "t.jsonl"
        ReActAgent(FakeLLM(["x", "y"]), log_path=p).run(TASK, tb())
        assert json.loads(p.read_text(encoding="utf-8"))["stopped_reason"] == "invalid_json"
