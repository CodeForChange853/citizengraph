"""Test helper: turn the non-recursive GBNF subset we emit into a Python regex.

Lets the tests check the grammar for real (what it accepts and rejects) without llama.cpp.
Supports rule references, string literals, character classes, groups, ``|``, ``*``, ``+``, ``?``.
"""

from __future__ import annotations

import re

_LIT_ESC = {'"': '"', "\\": "\\", "n": "\n", "t": "\t", "r": "\r"}


def parse_rules(text: str) -> dict[str, str]:
    rules: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, sep, body = line.partition("::=")
        if not sep:
            raise ValueError(f"not a rule: {line!r}")
        rules[name.strip()] = body.strip()
    return rules


def referenced(body: str) -> set[str]:
    stripped = re.sub(r'"(?:[^"\\]|\\.)*"', " ", body)
    stripped = re.sub(r"\[(?:[^\]\\]|\\.)*\]", " ", stripped)
    return set(re.findall(r"[a-z][a-z0-9-]*", stripped))


class _Compiler:
    def __init__(self, rules: dict[str, str]):
        self.rules = rules
        self.cache: dict[str, str] = {}
        self.stack: list[str] = []

    def rule(self, name: str) -> str:
        if name in self.cache:
            return self.cache[name]
        if name in self.stack:
            raise ValueError(f"recursive rule {name}")
        self.stack.append(name)
        rx = self.expr(self.rules[name])
        self.stack.pop()
        self.cache[name] = f"(?:{rx})"
        return self.cache[name]

    def expr(self, body: str) -> str:
        saved = (getattr(self, "s", ""), getattr(self, "i", 0))  # rule refs re-enter here
        self.s, self.i = body, 0
        out = self.alt()
        if self.i != len(self.s):
            raise ValueError(f"trailing text in {body!r} at {self.i}")
        self.s, self.i = saved
        return out

    def alt(self) -> str:
        parts = [self.seq()]
        while self.peek() == "|":
            self.i += 1
            parts.append(self.seq())
        return "|".join(parts)

    def peek(self) -> str:
        while self.i < len(self.s) and self.s[self.i] == " ":
            self.i += 1
        return self.s[self.i] if self.i < len(self.s) else ""

    def seq(self) -> str:
        out = ""
        while self.peek() not in ("", "|", ")"):
            out += self.postfix()
        return out or "(?:)"

    def postfix(self) -> str:
        atom = self.atom()
        while self.peek() in ("*", "+", "?"):
            atom = f"(?:{atom}){self.s[self.i]}"
            self.i += 1
        return atom

    def atom(self) -> str:
        c = self.peek()
        if c == '"':
            j, lit = self.i + 1, ""
            while self.s[j] != '"':
                if self.s[j] == "\\":
                    lit += _LIT_ESC[self.s[j + 1]]
                    j += 2
                else:
                    lit += self.s[j]
                    j += 1
            self.i = j + 1
            return re.escape(lit)
        if c == "[":
            j = self.i + 1
            while self.s[j] != "]":
                j += 2 if self.s[j] == "\\" else 1
            body = self.s[self.i + 1 : j]
            self.i = j + 1
            return f"[{body}]"
        if c == "(":
            self.i += 1
            inner = self.alt()
            assert self.peek() == ")"
            self.i += 1
            return f"(?:{inner})"
        m = re.compile(r"[a-z][a-z0-9-]*").match(self.s, self.i)
        if not m:
            raise ValueError(f"cannot parse at {self.s[self.i :]!r}")
        self.i = m.end()
        return self.rule(m.group())


def to_regex(text: str, root: str = "root") -> re.Pattern[str]:
    rules = parse_rules(text)
    missing = {r for body in rules.values() for r in referenced(body)} - set(rules)
    if missing:
        raise ValueError(f"undefined rules: {sorted(missing)}")
    return re.compile(_Compiler(rules).rule(root))
