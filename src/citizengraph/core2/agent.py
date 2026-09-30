"""ReAct loop over an ``LLMClient``: the model picks the next tool call or the final answer.

The reply must be ONE strict JSON object: ``{"tool": name, "args": {...}}`` or
``{"final": {...}}`` (an optional short ``"thought"`` string may come first). Around that:

* a GBNF grammar (``grammar.py``) is passed to ``generate`` so llama.cpp can only emit valid actions;
* an unparseable reply gets ONE retry (config ``invalid_json_retries``), then the safe fallback;
* bad arguments, an unknown tool or an invalid final are returned to the model as an observation
  (bounded by ``invalid_args_retries``); an unknown tool is refused, never run;
* a hard step cap (config ``max_steps``, default 8) ends in the safe fallback
  ("please check with the office"); the model never loops forever;
* every run is appended to a JSONL trajectory log when ``log_path`` is given.

The loop is stateless towards the model: each call gets the whole prompt (task + history).
The agent is not wired into the API.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from citizengraph.core2.config import Core2Config
from citizengraph.core2.grammar import build_grammar
from citizengraph.core2.models import ALERT_KINDS, STATUSES
from citizengraph.core2.runtime import (
    REASONS,
    AgentResult,
    StoppedReason,
    Task,
    TraceStep,
    append_jsonl,
    safe_fallback,
    validate_final,
)
from citizengraph.core2.tools import ToolArgumentError, Toolbox, UnknownToolError
from citizengraph.llm.base import LLMClient

_COMPACT = {"separators": (",", ":"), "ensure_ascii": False}


def _dumps(obj: Any) -> str:
    return json.dumps(obj, **_COMPACT)


def build_preamble(toolbox: Toolbox) -> str:
    """The fixed part of the prompt: rules, output format, vocabulary and tools."""
    return "\n".join(
        [
            "You are the SLA assistant of a city government office. Each turn, reply with ONE",
            "JSON object and nothing else:",
            '  {"tool": "<name>", "args": {...}}   call one tool',
            '  {"final": {...}}                    finish',
            "Rules: use only the tools listed. Ids, dates and numbers come from tool results;",
            "never invent them. Comparisons and alert texts are made by the tools. Do not",
            "blame the office for a step done by an external agency.",
            'Final for a status or office task: {"final": {"applications": [{"app_id": "..",',
            '"status": "..", "reasons": [..], "alerts": [..]}]}}. If no application exists:',
            '{"final": {"applications": [], "reasons": ["no_application_found"]}}.',
            '"alerts" lists the alerts you drafted with draft_alert.',
            'Final for a calendar task: {"final": {"answer": {"working_days": N}}} or',
            '{"final": {"answer": {"suspended": true}}}.',
            "status: " + ", ".join(STATUSES),
            "reasons: " + ", ".join(REASONS),
            "alert kinds: " + ", ".join(ALERT_KINDS),
            "Tools:",
            toolbox.describe(),
        ]
    )


def build_prompt(
    task: Task,
    preamble: str,
    history: list[tuple[str, str]],
    note: str | None = None,
) -> str:
    """Preamble, the task, the numbered history of actions and results, then the cue."""
    lines = [preamble, f"TASK: {task.brief()}", "HISTORY:"]
    for i, (action, result) in enumerate(history, start=1):
        lines.append(f"ACTION {i}: {action}")
        lines.append(f"RESULT {i}: {result}")
    if note:
        lines.append(f"NOTE: {note}")
    lines.append("NEXT:")
    return "\n".join(lines)


class ActionError(ValueError):
    """The reply is not one valid action object."""


def parse_action(raw: str) -> dict[str, Any]:
    """Strict parse of a model reply into ``{"tool", "args"}`` or ``{"final"}``."""
    if not isinstance(raw, str):
        raise ActionError("reply is not text")

    def reject(name: str) -> Any:
        raise ActionError(f"{name} is not allowed in JSON")

    try:
        obj = json.loads(raw.strip(), parse_constant=reject)
    except json.JSONDecodeError as exc:
        raise ActionError(f"not valid JSON ({exc.msg})") from None
    if not isinstance(obj, dict):
        raise ActionError("the reply must be a JSON object")
    thought = obj.get("thought")
    if thought is not None and (not isinstance(thought, str) or len(thought) > 300):
        raise ActionError("thought must be a short string")
    keys = set(obj) - {"thought"}
    if keys == {"tool", "args"}:
        if not isinstance(obj["tool"], str) or not isinstance(obj["args"], dict):
            raise ActionError("tool must be a string and args an object")
        return {"tool": obj["tool"], "args": obj["args"]}
    if keys == {"final"}:
        return {"final": obj["final"]}
    raise ActionError('use exactly {"tool", "args"} or {"final"}')


class ReActAgent:
    def __init__(
        self,
        llm: LLMClient,
        *,
        config: Core2Config | None = None,
        log_path: str | Path | None = None,
        use_grammar: bool = True,
        name: str = "react",
    ) -> None:
        self.llm = llm
        self.config = config
        self.log_path = Path(log_path) if log_path else None
        self.use_grammar = use_grammar
        self.name = name

    def run(self, task: Task, toolbox: Toolbox, max_steps: int | None = None) -> AgentResult:
        cfg = self.config or toolbox.config
        cap = max_steps or cfg.max_steps
        preamble = build_preamble(toolbox)
        grammar = build_grammar(toolbox) if self.use_grammar else None
        history: list[tuple[str, str]] = []
        trace: list[TraceStep] = []
        llm_calls = 0
        bad_actions = 0

        def finish(final: dict[str, Any], why: StoppedReason, steps: int) -> AgentResult:
            result = AgentResult(
                task=task,
                final=final,
                trace=trace,
                steps=steps,
                llm_calls=llm_calls,
                stopped_reason=why,
                runner=self.name,
            )
            if self.log_path:
                append_jsonl(result, self.log_path)
            return result

        for n in range(1, cap + 1):
            note: str | None = None
            action: dict[str, Any] | None = None
            for _attempt in range(cfg.invalid_json_retries + 1):
                prompt = build_prompt(task, preamble, history, note)
                if len(prompt) > cfg.max_prompt_chars:
                    return finish(safe_fallback(), "prompt_too_long", n - 1)
                try:
                    raw = self.llm.generate(prompt, max_tokens=cfg.max_tokens, grammar=grammar)
                except Exception as exc:  # noqa: BLE001 - any model failure ends in the fallback
                    trace.append(TraceStep(n=n, kind="invalid_json", error=f"llm error: {exc}"))
                    return finish(safe_fallback(), "llm_error", n - 1)
                llm_calls += 1
                try:
                    action = parse_action(raw)
                    break
                except ActionError as exc:
                    trace.append(
                        TraceStep(n=n, kind="invalid_json", raw=str(raw)[:400], error=str(exc))
                    )
                    note = f"your last reply was rejected: {exc}. Reply with one JSON object."
            if action is None:
                return finish(safe_fallback(), "invalid_json", n)

            if "final" in action:
                problems = validate_final(action["final"])
                if not problems:
                    trace.append(TraceStep(n=n, kind="final", raw=_dumps(action), action=action))
                    return finish(action["final"], "final", n)
                obs: dict[str, Any] = {"error": "invalid_final", "problems": problems[:3]}
                trace.append(
                    TraceStep(
                        n=n,
                        kind="invalid_final",
                        action=action,
                        observation=obs,
                        error="; ".join(problems[:3]),
                    )
                )
                history.append((_dumps(action), _dumps(obs)))
                bad_actions += 1
            else:
                try:
                    obs = toolbox.call(action["tool"], action["args"])
                    kind = "tool"
                    error = None
                except UnknownToolError:
                    obs = {
                        "error": "unknown_tool",
                        "tool": str(action["tool"])[:60],
                        "valid_tools": list(toolbox.specs),
                    }
                    kind, error = "unknown_tool", "unknown tool refused"
                except ToolArgumentError as exc:
                    obs = {"error": "invalid_arguments", "detail": str(exc)[:300]}
                    kind, error = "invalid_args", str(exc)[:300]
                except Exception as exc:  # noqa: BLE001 - a tool bug must not crash the loop
                    obs = {"error": "tool_failed", "detail": type(exc).__name__}
                    kind, error = "invalid_args", f"tool failed: {type(exc).__name__}"
                text = _dumps(obs)
                if len(text) > cfg.max_observation_chars:
                    obs = {"error": "observation_too_large", "chars": len(text)}
                    text = _dumps(obs)
                trace.append(
                    TraceStep(
                        n=n,
                        kind=kind,
                        raw=_dumps(action),
                        action=action,
                        observation=obs,
                        error=error,
                    )
                )
                history.append((_dumps(action), text))
                if kind != "tool":
                    bad_actions += 1
            if bad_actions > cfg.invalid_args_retries:
                return finish(safe_fallback(), "invalid_action", n)
        return finish(safe_fallback(), "step_cap", cap)
