"""GBNF grammar (llama.cpp) that makes the model's reply a valid Core 2 action.

One alternative per tool with its exact argument names, order and value shapes, so the model
cannot invent a tool, drop or add an argument, or send a malformed date. Finals are limited to the
two shapes ``validate_final`` accepts, with status, reason and alert words as enumerations.
The grammar has no recursion, so the tests can transpile it to a regex and check it.
"""

from __future__ import annotations

from citizengraph.core2.models import ALERT_KINDS, STATUSES
from citizengraph.core2.runtime import REASONS
from citizengraph.core2.tools import Param, Toolbox

_DIGIT = "[0-9]"
_STATIC = {
    "ws": "[ \\t\\n]*",
    "string": '"\\"" ([^"\\\\\\x00-\\x1f] | "\\\\" ["\\\\/bfnrt])* "\\""',
    "id": '"\\"" [A-Za-z0-9_.:-]+ "\\""',
    "role": '"\\"" [^"\\\\\\x00-\\x1f]+ "\\""',
    "date": f'"\\"" {_DIGIT} {_DIGIT} {_DIGIT} {_DIGIT} "-" {_DIGIT} {_DIGIT} "-" {_DIGIT} {_DIGIT} "\\""',
    "datetime": (
        f'"\\"" {_DIGIT} {_DIGIT} {_DIGIT} {_DIGIT} "-" {_DIGIT} {_DIGIT} "-" {_DIGIT} {_DIGIT} '
        f'"T" {_DIGIT} {_DIGIT} ":" {_DIGIT} {_DIGIT} "\\""'
    ),
    "integer": "[0-9]+",
    "boolean": '"true" | "false"',
}


def _quoted(word: str) -> str:
    return f'"\\"{word}\\""'


def _alternatives(words: tuple[str, ...]) -> str:
    return " | ".join(_quoted(w) for w in words)


def _param_rule(p: Param) -> str:
    return f"enum-{p.name}" if p.type == "enum" else p.type


def _args_rule(params: tuple[Param, ...]) -> str:
    parts: list[str] = []
    for p in params:
        item = f'{_quoted(p.name)} ws ":" ws {_param_rule(p)}'
        if p.required:
            parts.append(item if not parts else f'ws "," ws {item}')
        else:
            parts.append(f'(ws "," ws {item})?')
    return '"{" ws ' + " ".join(parts) + ' ws "}"'


def build_grammar(toolbox: Toolbox) -> str:
    """The GBNF text for ``toolbox``'s tools (pass it as ``grammar=`` to ``LLMClient.generate``)."""
    rules: dict[str, str] = {
        "root": "ws (action | final) ws",
        **_STATIC,
        "thought": f'{_quoted("thought")} ws ":" ws string ws "," ws',
    }
    calls: list[str] = []
    enums: dict[str, str] = {}
    for name, spec in toolbox.specs.items():
        rule = "call-" + name.replace("_", "-")
        calls.append(rule)
        rules[rule] = (
            f'"{{" ws thought? {_quoted("tool")} ws ":" ws {_quoted(name)} ws "," ws '
            f'{_quoted("args")} ws ":" ws {_args_rule(spec.params)} ws "}}"'
        )
        for p in spec.params:
            if p.type == "enum":
                enums[_param_rule(p)] = _alternatives(p.enum)
    rules["action"] = " | ".join(calls)
    rules.update(enums)
    rules["status"] = _alternatives(STATUSES)
    rules["reason"] = _alternatives(REASONS)
    rules["alert"] = _alternatives(ALERT_KINDS)
    rules["reason-list"] = '"[" ws (reason (ws "," ws reason)*)? ws "]"'
    rules["alert-list"] = '"[" ws (alert (ws "," ws alert)*)? ws "]"'
    rules["app"] = (
        f'"{{" ws {_quoted("app_id")} ws ":" ws id ws "," ws {_quoted("status")} ws ":" ws status '
        f'ws "," ws {_quoted("reasons")} ws ":" ws reason-list ws "," ws {_quoted("alerts")} ws '
        f'":" ws alert-list ws "}}"'
    )
    rules["status-final"] = (
        f'"{{" ws {_quoted("applications")} ws ":" ws "[" ws (app (ws "," ws app)*)? ws "]" '
        f'(ws "," ws {_quoted("reasons")} ws ":" ws reason-list)? ws "}}"'
    )
    rules["calendar-final"] = (
        f'"{{" ws {_quoted("answer")} ws ":" ws ('
        f'"{{" ws {_quoted("working_days")} ws ":" ws integer ws "}}" | '
        f'"{{" ws {_quoted("suspended")} ws ":" ws boolean ws "}}") ws "}}"'
    )
    rules["final"] = (
        f'"{{" ws thought? {_quoted("final")} ws ":" ws (status-final | calendar-final) ws "}}"'
    )
    return "\n".join(f"{name} ::= {body}" for name, body in rules.items()) + "\n"
