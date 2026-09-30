"""Minimal Cypher tokenizer for the guardrail.

It is deliberately stricter than Cypher itself. Anything it cannot classify raises
``LexError``, and the validator turns that into a rejection (fail closed).

- Comments (``//`` and ``/* */``) are dropped; string literals are consumed whole, so
  a keyword inside either can never be mistaken for a clause, and vice versa.
- Backtick identifiers, ``;``, non-ASCII characters outside strings and comments, and
  control characters are refused outright.
- Inside comments, line/paragraph separators, control and format characters are refused
  too, because Neo4j may end a ``//`` comment at a separator we do not recognise, which
  would let real code hide from us.
"""

import re
import unicodedata
from dataclasses import dataclass

WORD = "WORD"
NUMBER = "NUMBER"
STRING = "STRING"
PARAM = "PARAM"
PUNCT = "PUNCT"

_SINGLE_PUNCT = frozenset("()[]{},.:|&!+-*/%^=<>~")
_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# Digits, then letters/digits/underscores or a dot that is followed by a digit. This keeps
# `1..3` as 1 / .. / 3 while swallowing `0x1F`, `1_0` and `1.5e3` as one (later rejected) token.
_NUMBER_RE = re.compile(r"[0-9](?:[A-Za-z0-9_]|\.(?=[0-9]))*")
_PARAM_RE = re.compile(r"\$([A-Za-z0-9_]+)")
_ALLOWED_WHITESPACE = " \t\r\n"
_LINE_END = "\n\r"


class LexError(ValueError):
    """The text cannot be tokenized safely. Messages never echo unbounded input."""


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    pos: int


def _describe(ch: str) -> str:
    return f"U+{ord(ch):04X}"


def _check_comment_char(ch: str, pos: int) -> None:
    if ch in "\t\n\r":
        return
    category = unicodedata.category(ch)
    if category in ("Cc", "Cf", "Zl", "Zp") or ch in "\x85  ":
        raise LexError(f"control or separator character {_describe(ch)} in comment at {pos}")


def _read_string(text: str, start: int) -> tuple[str, int]:
    quote = text[start]
    out: list[str] = []
    i = start + 1
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\\":
            if i + 1 >= n:
                break
            out.append(text[i + 1])
            i += 2
            continue
        if ch == quote:
            return "".join(out), i + 1
        out.append(ch)
        i += 1
    raise LexError(f"unterminated string literal starting at {start}")


def tokenize(text: str) -> list[Token]:
    tokens: list[Token] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]

        if ch in _ALLOWED_WHITESPACE:
            i += 1
            continue

        if ord(ch) > 127:
            raise LexError(f"non-ASCII character {_describe(ch)} outside a string at {i}")
        if ord(ch) < 32 or ord(ch) == 127:
            raise LexError(f"control character {_describe(ch)} at {i}")

        if ch == "/" and text.startswith("//", i):
            i += 2
            while i < n and text[i] not in _LINE_END:
                _check_comment_char(text[i], i)
                i += 1
            continue

        if ch == "/" and text.startswith("/*", i):
            start = i
            i += 2
            while True:
                if i >= n:
                    raise LexError(f"unterminated block comment starting at {start}")
                if text.startswith("*/", i):
                    i += 2
                    break
                _check_comment_char(text[i], i)
                i += 1
            continue

        if ch in "'\"":
            value, end = _read_string(text, i)
            tokens.append(Token(STRING, value, i))
            i = end
            continue

        if ch == "`":
            raise LexError(f"backtick-quoted identifiers are not allowed (at {i})")

        if ch == ";":
            raise LexError(f"semicolon ';' is not allowed: one statement only (at {i})")

        if ch == "$":
            match = _PARAM_RE.match(text, i)
            if not match:
                raise LexError(f"malformed parameter at {i}")
            tokens.append(Token(PARAM, match.group(1), i))
            i = match.end()
            continue

        match = _WORD_RE.match(text, i)
        if match:
            tokens.append(Token(WORD, match.group(0), i))
            i = match.end()
            continue

        match = _NUMBER_RE.match(text, i)
        if match:
            tokens.append(Token(NUMBER, match.group(0), i))
            i = match.end()
            continue

        if text.startswith("..", i):
            tokens.append(Token(PUNCT, "..", i))
            i += 2
            continue

        if ch in _SINGLE_PUNCT:
            tokens.append(Token(PUNCT, ch, i))
            i += 1
            continue

        raise LexError(f"unsupported character {ch!r} at {i}")

    return tokens
