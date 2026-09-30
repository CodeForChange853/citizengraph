"""Read-only Cypher guardrail (docs/specs.md section 4).

``validate_cypher`` returns a ``ValidationResult`` and never raises: any failure, including
an unexpected internal error or an unreadable config, is a rejection (fail closed).

The check runs on tokens from ``lexer.tokenize``, never on raw text, so comments and string
literals can neither hide a clause nor fake one. The guardrail is one layer: queries must
still run in a read transaction (``session.execute_read``), see docs/specs.md section 4.
"""

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from .lexer import NUMBER, PUNCT, WORD, LexError, Token, tokenize
from .schema import OFFICIAL_SCHEMA, Schema

LIMITS_PATH = Path(__file__).resolve().parents[3] / "config" / "limits.yaml"

MAX_REASONS = 50
MAX_REASON_CHARS = 200

# Mutating or unsafe (docs/specs.md section 4). CALL is denied outright, including apoc.*.
FORBIDDEN_KEYWORDS = frozenset(
    {"CREATE", "MERGE", "SET", "DELETE", "DETACH", "REMOVE", "DROP", "FOREACH", "LOAD", "CALL"}
)
# Not mutating in themselves, but outside the clause allow-list. Words that are also legal
# variable names in Cypher are rejected as variables too: over-rejecting is the safe side.
DISALLOWED_CLAUSES = frozenset(
    {
        "CSV",
        "YIELD",
        "UNION",
        "USE",
        "USING",
        "START",
        "FINISH",
        "SHOW",
        "TERMINATE",
        "ALTER",
        "GRANT",
        "DENY",
        "REVOKE",
        "RENAME",
        "CONSTRAINT",
        "INDEX",
        "PROFILE",
        "EXPLAIN",
        "CYPHER",
        "INSERT",
        "FILTER",
        "LET",
        "NEXT",
        "OFFSET",
        "ON",
        "COMMIT",
        "TRANSACTIONS",
    }
)
# Clause words allowed to open a query, and clauses that may not follow the final RETURN.
OPENERS = frozenset({"MATCH", "OPTIONAL", "WITH", "UNWIND", "RETURN"})
CLAUSE_STARTERS = frozenset({"MATCH", "OPTIONAL", "WHERE", "WITH", "UNWIND", "RETURN"})
# Functions that expose properties the schema check cannot see.
FORBIDDEN_FUNCTIONS = frozenset({"PROPERTIES", "KEYS"})
# A `[` after any other word, `)`, `]`, string, number or parameter is a subscript such as
# `s['secret']`, which would read a property by a dynamic key.
LIST_PREFIX_KEYWORDS = frozenset(
    {
        "IN",
        "RETURN",
        "WHERE",
        "AND",
        "OR",
        "XOR",
        "NOT",
        "WITH",
        "UNWIND",
        "BY",
        "THEN",
        "ELSE",
        "WHEN",
        "CASE",
        "IS",
        "AS",
        "CONTAINS",
        "LIMIT",
        "SKIP",
    }
)
PLAIN_POSITIVE_INT = re.compile(r"[1-9][0-9]*")


@dataclass
class ValidationResult:
    ok: bool
    reasons: list[str] = field(default_factory=list)


@lru_cache(maxsize=8)
def _load_max_limit(path: Path) -> int:
    """Read core1.cypher_limit_max. Cached per path: restart to pick up config edits."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    value = data["core1"]["cypher_limit_max"]
    if type(value) is not int or value <= 0:
        raise ValueError("cypher_limit_max must be a positive integer")
    return value


def _clip(text: str, limit: int = MAX_REASON_CHARS) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _reject(*reasons: str) -> ValidationResult:
    return ValidationResult(ok=False, reasons=[_clip(r) for r in reasons])


def _is_punct(token: Token | None, *values: str) -> bool:
    return token is not None and token.kind == PUNCT and token.value in values


def _is_word(token: Token | None, *values: str) -> bool:
    return token is not None and token.kind == WORD and token.value.upper() in values


def _analyze(tokens: list[Token], schema: Schema, max_limit: int) -> list[str]:
    reasons: dict[str, None] = {}  # ordered, de-duplicated

    def add(reason: str) -> None:
        reasons.setdefault(_clip(reason), None)

    if not tokens:
        add("empty query")
        return list(reasons)

    if not (tokens[0].kind == WORD and tokens[0].value.upper() in OPENERS):
        add("query must start with MATCH, OPTIONAL MATCH, WITH, UNWIND or RETURN")

    stack: list[str] = []
    depths: list[int] = []
    expect_label = False
    last_was_label = False
    return_idx: int | None = None
    n = len(tokens)

    for i, tok in enumerate(tokens):
        prev = tokens[i - 1] if i else None
        nxt = tokens[i + 1] if i + 1 < n else None
        depths.append(len(stack))
        in_map = bool(stack) and stack[-1] == "{"

        # Brackets, and subscripts (dynamic property access).
        if tok.kind == PUNCT and tok.value in "([{":
            if tok.value == "[" and prev is not None:
                subscript = (
                    _is_punct(prev, ")", "]")
                    or prev.kind != PUNCT
                    and not _is_word(prev, *LIST_PREFIX_KEYWORDS)
                )
                if subscript:
                    add("subscripts and dynamic property access are not allowed")
            stack.append(tok.value)
        elif tok.kind == PUNCT and tok.value in ")]}":
            opener = {")": "(", "]": "[", "}": "{"}[tok.value]
            if stack and stack[-1] == opener:
                stack.pop()
            else:
                add("unbalanced brackets")
                if stack:
                    stack.pop()

        # Label / relationship-type expressions: `:A`, `:A|B`, `:A:B`, `:!A`.
        if expect_label:
            if tok.kind == WORD:
                _check_label(tok, stack, schema, add)
                expect_label = False
                last_was_label = True
                continue
            if _is_punct(tok, "!"):
                continue
            if not (_is_punct(tok, ":") and _is_punct(prev, "|", "&")):
                add("malformed label expression")
                expect_label = False
        elif last_was_label and _is_punct(tok, "|", "&"):
            expect_label = True
            last_was_label = False
            continue
        last_was_label = False
        if _is_punct(tok, ":") and not in_map:
            expect_label = True
            continue

        if _is_punct(tok, "."):
            if nxt is None or nxt.kind != WORD:
                add("'.' must be followed by a property name (no '.*' or float literals)")
            continue

        if tok.kind != WORD:
            continue

        # Property key: after '.' or as a map key inside {...}.
        if _is_punct(prev, ".") or (in_map and _is_punct(nxt, ":")):
            if tok.value not in schema.properties:
                add(f"unknown property '{_clip(tok.value, 40)}'")
            if _is_punct(prev, ".") and _is_punct(nxt, "("):
                add(f"namespaced function calls are not allowed ('...{_clip(tok.value, 40)}(')")
            continue

        word = tok.value.upper()
        if word in FORBIDDEN_KEYWORDS:
            add(f"forbidden keyword {word}")
        elif word in DISALLOWED_CLAUSES:
            add(f"clause or keyword {word} is not in the allow-list")

        if word == "ORDER" and not _is_word(nxt, "BY"):
            add("ORDER must be followed by BY")
        if word == "OPTIONAL" and not _is_word(nxt, "MATCH"):
            add("OPTIONAL must be followed by MATCH")
        if word in FORBIDDEN_FUNCTIONS and _is_punct(nxt, "("):
            add(f"function {word.lower()}() is not allowed")

        if not stack and word in CLAUSE_STARTERS and not _is_word(prev, "STARTS", "ENDS"):
            if return_idx is not None:
                add("RETURN must be the final clause; only ORDER BY, SKIP and LIMIT may follow")
            if word == "RETURN":
                return_idx = i

    if expect_label:
        add("malformed label expression")
    if stack:
        add("unbalanced brackets")

    _check_limit(tokens, depths, return_idx, max_limit, add)
    return list(reasons)


def _check_label(tok: Token, stack: list[str], schema: Schema, add) -> None:
    name = _clip(tok.value, 40)
    if stack and stack[-1] == "[":
        if tok.value not in schema.relationship_types:
            add(f"unknown relationship type '{name}'")
    elif tok.value not in schema.labels:
        add(f"unknown label '{name}'")


def _check_limit(
    tokens: list[Token], depths: list[int], return_idx: int | None, max_limit: int, add
) -> None:
    if return_idx is None:
        add("query must contain a top-level RETURN")
        return
    limit_idx = None
    for i in range(len(tokens) - 1, return_idx, -1):
        if depths[i] == 0 and _is_word(tokens[i], "LIMIT"):
            limit_idx = i
            break
    if limit_idx is None:
        add(f"missing LIMIT: the query must end with LIMIT n (max {max_limit})")
        return
    operand = tokens[limit_idx + 1 :]
    if (
        len(operand) != 1
        or operand[0].kind != NUMBER
        or not PLAIN_POSITIVE_INT.fullmatch(operand[0].value)
    ):
        add("LIMIT must be followed by one plain positive integer literal and end the query")
        return
    digits = operand[0].value
    if len(digits) > 18 or int(digits) > max_limit:
        add(f"LIMIT exceeds the maximum of {max_limit}")


def _validate(query: object, schema: Schema, max_limit: int | None) -> ValidationResult:
    if not isinstance(query, str):
        return _reject("query must be a string")
    if max_limit is None:
        try:
            max_limit = _load_max_limit(LIMITS_PATH)
        except (OSError, yaml.YAMLError, LookupError, TypeError, ValueError):
            return _reject("could not read a valid limits config (fail closed)")
    elif type(max_limit) is not int or max_limit <= 0:
        return _reject("invalid max_limit (fail closed)")

    try:
        tokens = tokenize(query)
    except LexError as exc:
        return _reject(str(exc))

    reasons = _analyze(tokens, schema, max_limit)[:MAX_REASONS]
    return ValidationResult(ok=not reasons, reasons=reasons)


def validate_cypher(
    query: str, *, schema: Schema = OFFICIAL_SCHEMA, max_limit: int | None = None
) -> ValidationResult:
    """Validate one generated Cypher query. Never raises.

    ``max_limit`` defaults to ``core1.cypher_limit_max`` in config/limits.yaml.
    """
    try:
        return _validate(query, schema, max_limit)
    except Exception:  # noqa: BLE001 - fail closed on anything unexpected
        return _reject("internal guardrail error (fail closed)")
