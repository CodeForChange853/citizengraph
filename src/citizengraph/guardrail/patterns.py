"""Pattern rules for the guardrail (docs/specs.md section 4).

Purpose: keep Core 1 queries inside the official charter graph. `MATCH (n) RETURN n` and
`MATCH ()-[r]->() RETURN r` would otherwise read whatever else is in the database.

- Every node pattern carries a label, except a bare variable that was bound with a label
  earlier and is still in scope, e.g. `(f)` after `MATCH (f:Fee)`. An anonymous `()` needs one.
- Every relationship pattern names a type. `[r]`, `[]`, `[*]`, `[:!T]`, `--`, `-->` and `<--`
  are refused.
- The rules apply everywhere patterns can appear: MATCH, WHERE predicates, EXISTS and COUNT
  subqueries, and pattern comprehensions.

Scope follows Cypher: `WITH` keeps only the variables it projects (`WITH s`, `WITH s AS t`,
`WITH *`), and variables bound inside a subquery or a `[...]` do not leak out of it.

Which parentheses are node patterns is decided from the tokens around them (after MATCH, `,`
or `=` in a MATCH clause, or `{` of a subquery; next to a `-` relationship link). Ordinary
expression parentheses are left alone. A bare variable in parentheses that touches a `-`, as in
`a - (b)`, is read as a node pattern and refused unless it is a labeled variable: this
over-rejects, which is the safe side.
"""

from collections.abc import Callable

from .lexer import PARAM, PUNCT, WORD, Token

_OPEN = {"(": ")", "[": "]", "{": "}"}
_CLOSE = {")": "(", "]": "[", "}": "{"}
# `{` after one of these opens a subquery whose variables stay inside it.
_SUBQUERY_WORDS = ("EXISTS", "COUNT", "COLLECT")
_CLAUSES = frozenset({"MATCH", "WHERE", "WITH", "UNWIND", "RETURN"})
_WITH_ENDS = frozenset(
    {"WHERE", "ORDER", "SKIP", "LIMIT", "MATCH", "OPTIONAL", "UNWIND", "RETURN", "WITH"}
)


def _is_punct(token: Token | None, *values: str) -> bool:
    return token is not None and token.kind == PUNCT and token.value in values


def _is_word(token: Token | None, *values: str) -> bool:
    return token is not None and token.kind == WORD and token.value.upper() in values


def _match_brackets(tokens: list[Token]) -> dict[int, int] | None:
    """Index of each opening bracket -> its closing bracket; None if unbalanced."""
    pairs: dict[int, int] = {}
    stack: list[int] = []
    for i, tok in enumerate(tokens):
        if tok.kind != PUNCT:
            continue
        if tok.value in _OPEN:
            stack.append(i)
        elif tok.value in _CLOSE:
            if not stack or tokens[stack[-1]].value != _CLOSE[tok.value]:
                return None
            pairs[stack.pop()] = i
    return None if stack else pairs


def _parse_node_body(body: list[Token]) -> tuple[str | None, bool] | None:
    """Read `[var] [:Label...] [{map} | $param] [WHERE ...]`.

    Returns (variable, has_label), or None when the tokens are not shaped like a node pattern.
    """
    n = len(body)
    i = 0
    var = None
    if i < n and body[i].kind == WORD and not _is_word(body[i], "WHERE"):
        var = body[i].value
        i += 1
    labeled = False
    if i < n and _is_punct(body[i], ":"):
        labeled = True
        i += 1
        while i < n:
            tok = body[i]
            if tok.kind == WORD and body[i - 1].kind == WORD:
                break  # a word right after a label word is a keyword (WHERE), not a label
            if tok.kind == WORD or _is_punct(tok, ":", "|", "&", "!"):
                i += 1
            else:
                break
    if i < n and _is_punct(body[i], "{"):
        depth = 0
        while i < n:
            if _is_punct(body[i], *_OPEN):
                depth += 1
            elif _is_punct(body[i], *_CLOSE):
                depth -= 1
            i += 1
            if depth == 0:
                break
        if depth != 0:
            return None
    elif i < n and body[i].kind == PARAM:
        i += 1
    if i < n and not _is_word(body[i], "WHERE"):
        return None
    return var, labeled


def _relationship_is_typed(body: list[Token]) -> bool:
    """`[:T]` or `[r:T]`; anything else (`[]`, `[r]`, `[*]`, `[r*1..3]`, `[:!T]`) is untyped."""
    j = 1 if len(body) > 1 and body[0].kind == WORD and _is_punct(body[1], ":") else 0
    return j + 1 < len(body) and _is_punct(body[j], ":") and body[j + 1].kind == WORD


def _with_projection(tokens: list[Token], start: int, bound: set[str]) -> tuple[int, set[str]]:
    """For a WITH whose items begin at `start`: (index where the items end, variables kept)."""
    items: list[list[Token]] = [[]]
    depth = 0
    j = start
    while j < len(tokens):
        tok = tokens[j]
        if tok.kind == PUNCT and tok.value in _OPEN:
            depth += 1
        elif tok.kind == PUNCT and tok.value in _CLOSE:
            if depth == 0:
                break
            depth -= 1
        elif depth == 0:
            if (
                tok.kind == WORD
                and tok.value.upper() in _WITH_ENDS
                and not _is_punct(tokens[j - 1], ".", ":")
                and not (_is_word(tok, "WITH") and _is_word(tokens[j - 1], "STARTS", "ENDS"))
            ):
                break
            if _is_punct(tok, ","):
                items.append([])
                j += 1
                continue
        items[-1].append(tok)
        j += 1

    kept: set[str] = set()
    for k, item in enumerate(items):
        if k == 0 and item and _is_word(item[0], "DISTINCT"):
            item = item[1:]
        if len(item) == 1 and _is_punct(item[0], "*"):
            kept |= bound
        elif len(item) == 1 and item[0].kind == WORD:
            if item[0].value in bound:
                kept.add(item[0].value)
        elif (
            len(item) == 3
            and item[0].kind == WORD
            and _is_word(item[1], "AS")
            and item[2].kind == WORD
            and item[0].value in bound
        ):
            kept.add(item[2].value)
    return j, kept


def _check_node(
    tokens: list[Token],
    i: int,
    close: int,
    clause: str,
    bound: set[str],
    add: Callable[[str], None],
) -> None:
    prev = tokens[i - 1] if i else None
    after = tokens[close + 1] if close + 1 < len(tokens) else None
    after2 = tokens[close + 2] if close + 2 < len(tokens) else None
    definite = (
        _is_word(prev, "MATCH")
        or _is_punct(prev, "{")
        or (clause == "MATCH" and _is_punct(prev, "=", ","))
    )
    linked = (
        _is_punct(prev, "-")
        or (_is_punct(prev, ">") and i >= 2 and _is_punct(tokens[i - 2], "-"))
        or _is_punct(after, "-")
        or (_is_punct(after, "<") and _is_punct(after2, "-"))
    )
    if not (definite or linked):
        return  # an expression, a function call or a label test, not a pattern
    parsed = _parse_node_body(tokens[i + 1 : close])
    if parsed is None:
        if definite:
            add("unsupported node pattern syntax: write nodes as (var:Label {property: value})")
        return
    var, labeled = parsed
    if labeled:
        if var:
            bound.add(var)
    elif var is None:
        add("anonymous node pattern () needs a label, e.g. (:Service)")
    elif var not in bound:
        name = var if len(var) <= 40 else var[:37] + "..."
        add(f"node pattern ({name}) has no label and '{name}' is not bound with a label earlier")


def check_patterns(tokens: list[Token], add: Callable[[str], None]) -> None:
    """Report node and relationship patterns that are not explicit. Never raises on tokens."""
    pairs = _match_brackets(tokens)
    if pairs is None:
        return  # unbalanced brackets are reported by the main pass

    bound: set[str] = set()  # variables bound with a label and still in scope
    restore: dict[int, set[str]] = {}  # closing bracket index -> scope to return to
    resets: dict[int, set[str]] = {}  # index where a WITH ends -> scope after it
    clauses = [""]  # the clause word currently open at each bracket depth

    for i, tok in enumerate(tokens):
        if i in resets:
            bound = resets.pop(i)
        if i in restore:
            bound = restore.pop(i)
        prev = tokens[i - 1] if i else None
        nxt = tokens[i + 1] if i + 1 < len(tokens) else None

        if tok.kind == PUNCT:
            if tok.value in _OPEN:
                close = pairs[i]
                if tok.value == "(":
                    _check_node(tokens, i, close, clauses[-1], bound, add)
                elif tok.value == "[":
                    if _is_punct(prev, "-"):
                        if not _relationship_is_typed(tokens[i + 1 : close]):
                            add("relationship pattern must specify a type, e.g. [:REQUIRES]")
                    else:
                        restore[close] = set(bound)
                elif _is_word(prev, *_SUBQUERY_WORDS):
                    restore[close] = set(bound)
                    clauses.append("MATCH")  # a body without a clause word is a pattern list
                    continue
                clauses.append("")
            elif tok.value in _CLOSE:
                clauses.pop()
            elif tok.value == "-" and _is_punct(nxt, "-"):
                add("untyped relationship shorthand (--, -->, <--) is not allowed; use [:TYPE]")
            continue

        if tok.kind != WORD or _is_punct(prev, ".", ":"):
            continue
        word = tok.value.upper()
        if word == "WITH" and _is_word(prev, "STARTS", "ENDS"):
            continue
        if word in _CLAUSES:
            clauses[-1] = word
        if word == "WITH":
            end, kept = _with_projection(tokens, i + 1, bound)
            resets[end] = kept
