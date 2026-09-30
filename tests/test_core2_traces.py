"""Gold trajectories from the reference policy: synthetic, produced by code, chat-message format."""

import json
import re

import pytest
from test_core2_gbnf_regex import to_regex
from test_core2_support import graph

from citizengraph.core2.agent import ReActAgent, parse_action
from citizengraph.core2.config import load_core2_config
from citizengraph.core2.eval import build_case, load_scenarios
from citizengraph.core2.grammar import build_grammar
from citizengraph.core2.scripted import ScriptedPolicy
from citizengraph.core2.traces import EVAL_SEEDS, episode, generate, main, write_jsonl
from citizengraph.llm.fake import FakeLLM

EXAMPLES = list(generate(n_apps=40, seed=9001, graph=graph()))


def test_format_is_chat_messages_with_synthetic_markers():
    assert len(EXAMPLES) > 100
    for ex in EXAMPLES:
        assert [m["role"] for m in ex["messages"]] == ["system", "user", "assistant"]
        assert ex["messages"][1]["content"].startswith("TASK: ")
        assert ex["messages"][1]["content"].endswith("NEXT:")
        meta = ex["meta"]
        assert meta["synthetic"] is True and meta["generated_by_llm"] is False
        assert meta["produced_by"].startswith("code:") and meta["core"] == 2


def test_assistant_turns_are_valid_actions_under_the_grammar():
    from test_core2_support import dt, toolbox

    rx = to_regex(build_grammar(toolbox(now=dt(4, 14))))
    for ex in EXAMPLES:
        text = ex["messages"][2]["content"]
        parse_action(text)
        assert rx.fullmatch(text), text


def test_prompts_are_within_the_prompt_budget():
    budget = load_core2_config().max_prompt_chars
    for ex in EXAMPLES:
        assert len(ex["messages"][0]["content"]) + len(ex["messages"][1]["content"]) <= budget


def test_every_episode_ends_with_a_final_answer_that_is_valid():
    finals = [e for e in EXAMPLES if json.loads(e["messages"][2]["content"]).get("final")]
    assert finals and len(finals) >= 40


def test_deterministic_per_seed_and_different_across_seeds():
    again = list(generate(n_apps=40, seed=9001, graph=graph()))
    assert again == EXAMPLES
    other = list(generate(n_apps=40, seed=9002, graph=graph()))
    assert other != EXAMPLES


def test_evaluation_seeds_are_refused():
    seed = next(iter(EVAL_SEEDS))
    with pytest.raises(ValueError):
        list(generate(n_apps=5, seed=seed, graph=graph()))


def test_no_training_prompt_is_an_evaluation_prompt():
    eval_prompts = set()
    for scn in load_scenarios():
        case = build_case(scn, graph())
        for ex in episode(scn.task_obj(), case.toolbox, scn.max_steps):
            eval_prompts.add(ex["messages"][1]["content"])
    assert eval_prompts
    # Prompts with no history (same task text) or an empty result may coincide; any prompt
    # whose history carries application data must not.
    mine = {e["messages"][1]["content"] for e in EXAMPLES}
    carries_data = re.compile(r"^RESULT \d+: .*(app_id|CG-SIM-(?!9999))", re.MULTILINE)
    shared = {p for p in eval_prompts & mine if carries_data.search(p)}
    assert shared == set()


def test_prompts_match_what_the_agent_sends():
    scn = next(s for s in load_scenarios() if s.id == "E05_delayed_signatory_absent")
    sent = FakeLLM()  # records prompts
    case = build_case(scn, graph())
    scripted = ScriptedPolicy()

    class Tee:
        def generate(self, prompt, *, max_tokens=256, grammar=None):
            sent.prompts.append(prompt)
            return scripted.generate(prompt)

    ReActAgent(Tee()).run(scn.task_obj(), case.toolbox, scn.max_steps)
    case2 = build_case(scn, graph())
    eps = episode(scn.task_obj(), case2.toolbox, scn.max_steps)
    rebuilt = [ex["messages"][0]["content"] + "\n" + ex["messages"][1]["content"] for ex in eps]
    assert rebuilt == sent.prompts


def test_write_and_cli(tmp_path, capsys):
    p = tmp_path / "gold.jsonl"
    n = write_jsonl(p, EXAMPLES[:10])
    assert n == 10 and len(p.read_text(encoding="utf-8").splitlines()) == 10
    out = tmp_path / "cli.jsonl"
    assert main(["--out", str(out), "--apps", "10", "--seed", "9005"]) == 0
    assert "synthetic" in capsys.readouterr().out
    assert json.loads(out.read_text(encoding="utf-8").splitlines()[0])["meta"]["synthetic"]
