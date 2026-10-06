"""Pattern rules for the guardrail (docs/specs.md section 4).

Purpose: keep Core 1 queries inside the official charter graph. `MATCH (n) RETURN n` and
`MATCH ()-[r]->() RETURN r` would otherwise read whatever else is in the database.

- Every node pattern carries a label, except a bare variable that was bound with a label
  earlier and is still in scope, e.g. `(f)` after `MATCH (f:Fee)`. An anonymous `()` needs one.
- Every relationship pattern names a type. `[r]`, `[]`, `[*]`, `[:!T]`, `--`, `-->` and `<--`
  are refused.
- A relationship is one hop, written `[:TYPE]` or `[r:TYPE]` (alternatives and a property map
  are fine). Variable length (`[:T*]`, `[:T*1..3]`), quantifiers (`->+`, `->*`, `->{1,3}`,
  `((a)-[:T]->(b))+`), an inline WHERE and parenthesized path patterns are refused.
- A MATCH clause holds only patterns: `(...)`, relationships, commas and `name = (...)`.
  Path selectors and match modes (`ANY SHORTEST`, `REPEATABLE ELEMENTS`), `shortestPath(...)`
  and anything else between MATCH and the next clause are refused.
- The rules apply everywhere patterns can appear: MATCH, WHERE predicates, EXISTS and COUNT
  subqueries, and pattern comprehensions.
- Outside MATCH and subqueries a pattern is a predicate or the source of a comprehension and
  nothing else: it follows WHERE, AND, OR, XOR or NOT, or opens `[pattern | ...]`. As a value
  (`RETURN (s)-[:T]->(:X)`, in a list, a map, CASE or a function) it would be a list of whole
  paths, so it is refused. A predicate pattern cannot introduce a variable either.
- A node next to a `-` must have a relationship bracket on that side: `(a)-(b)`, `(a)->(b)`,
  `-(s)` and `<-[:T]->` are refused. A relationship bracket must have a node pattern on both
  sides: `(s.name)-[:T]->(:X)` and `(1)-[:T]->(:X)` are refused.

Scope follows Cypher: `WITH` keeps only the variables it projects (`WITH s`, `WITH s AS t`,
`WITH *`), and variables bound inside a subquery or a `[...]` do not leak out of it.

Which parentheses are node patterns is decided from the tokens around them (after MATCH, `,`
or `=` in a MATCH clause, or `{` of a subquery; next to a `-` relationship link). Ordinary
expression parentheses are left alone. A bare variable in parentheses that touches a `-`, as in
`a - (b)`, is read as a node pattern and refused unless it is a labeled variable: this
over-rejects, which is the safe side.

``check_patterns`` also reports where the pattern variables are (``PatternInfo``), which the
variable rules in ``variables.py`` build on.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from .keywords import SUBQUERY_WORDS
from .lexer import PUNCT, WORD, Token

_OPEN = {"(": ")", "[": "]", "{": "}"}
_CLOSE = {")": "(", "]": "[", "}": "{"}
_CLAUSES = frozenset({"MATCH", "WHERE", "WITH", "UNWIND", "RETURN"})
_WITH_ENDS = frozenset(
    {"WHERE", "ORDER", "SKIP", "LIMIT", "MATCH", "OPTIONAL", "UNWIND", "RETURN", "WITH"}
)
# Punctuation that may stand between the patterns of a MATCH clause.
_MATCH_PUNCT = ("-", "<", ">", ",", "=")

_BAD_MATCH = (
    "unsupported MATCH syntax: a MATCH clause may hold only node and relationship patterns, "
    "commas and 'name = (...)'"
)
_BAD_RELATIONSHIP = (
    "variable-length, quantified or filtered relationship patterns are not allowed: "
    "write one hop as [:TYPE] or [r:TYPE]"
)
_BAD_NODE = "unsupported node pattern syntax: write nodes as (var:Label {property: value})"
_BAD_LINK = "a relationship must be written -[:TYPE]->, <-[:TYPE]- or -[:TYPE]- between two nodes"
_BAD_PLACE = (
    "a pattern outside MATCH may only be a predicate (after WHERE, AND, OR, XOR, NOT) or the "
    "source of a pattern comprehension; it cannot be used as a value"
)
_PREDICATE_BEFORE = ("WHERE", "AND", "OR", "XOR", "NOT")
_PREDICATE_AFTER = (
    "AND",
    "OR",
    "XOR",
    "RETURN",
    "WITH",
    "MATCH",
    "OPTIONAL",
    "UNWIND",
    "ORDER",
    "SKIP",
    "LIMIT",
)


@dataclass
class PatternInfo:
    """Token indexes the variable rules need."""

    # A node, relationship or path variable, where a pattern binds or reuses it.
    entity_vars: set[int] = field(default_factory=set)
    # First token of a WITH item that is one bare word: `s` or `s AS t`.
    with_items: set[int] = field(default_factory=set)


def _is_punct(token: Token | None, *values: str) -> bool:
    return token is not None and token.kind == PUNCT and token.value in values


def _is_word(token: Token | None, *values: str) -> bool:
    return token is not None and token.kind == WORD and token.value.upper() in values


def opens_subquery(tokens: list[Token], i: int) -> bool:
    """The `{` at `i` follows EXISTS, COUNT or COLLECT used as a word, not as a label or key."""
    return (
        i >= 1
        and _is_word(tokens[i - 1], *SUBQUERY_WORDS)
        and not (i >= 2 and _is_punct(tokens[i - 2], ":", ".", "|", "&", "!"))
    )


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
    if i < n and not _is_word(body[i], "WHERE"):
        return None  # includes `(s:Service $props)`: a parameter in place of the property map
    return var, labeled


def _relationship_is_typed(body: list[Token]) -> bool:
    """`[:T]` or `[r:T]`; anything else (`[]`, `[r]`, `[*]`, `[r*1..3]`, `[:!T]`) is untyped."""
    j = 1 if len(body) > 1 and body[0].kind == WORD and _is_punct(body[1], ":") else 0
    return j + 1 < len(body) and _is_punct(body[j], ":") and body[j + 1].kind == WORD


def _relationship_is_one_hop(body: list[Token]) -> bool:
    """Nothing but `[var] [:Type...] [{map}]`: no `*`, range, quantifier or WHERE."""
    n = len(body)
    i = 1 if n and body[0].kind == WORD else 0
    while i < n and (body[i].kind == WORD or _is_punct(body[i], ":", "|", "&", "!")):
        if body[i].kind == WORD and body[i - 1].kind == WORD:
            return False  # two words in a row: an inline WHERE or IS
        i += 1
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
    return i == n


def _with_projection(
    tokens: list[Token], start: int, bound: set[str]
) -> tuple[int, set[str], set[int]]:
    """For a WITH whose items begin at `start`.

    Returns (index where the items end, variables kept, index of the first token of each item
    that is one bare word: `s` or `s AS t`).
    """
    items: list[list[int]] = [[]]
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
        items[-1].append(j)
        j += 1

    kept: set[str] = set()
    bare: set[int] = set()
    for k, item in enumerate(items):
        if k == 0 and item and _is_word(tokens[item[0]], "DISTINCT"):
            item = item[1:]
        words = [tokens[x] for x in item]
        if len(item) == 1 and _is_punct(words[0], "*"):
            kept |= bound
        elif len(item) == 1 and words[0].kind == WORD:
            bare.add(item[0])
            if words[0].value in bound:
                kept.add(words[0].value)
        elif (
            len(item) == 3
            and words[0].kind == WORD
            and _is_word(words[1], "AS")
            and words[2].kind == WORD
        ):
            bare.add(item[0])
            if words[0].value in bound:
                kept.add(words[2].value)
    return j, kept, bare


def _check_node(
    tokens: list[Token],
    i: int,
    close: int,
    clause: str,
    enclosing: str,
    bound: set[str],
    add: Callable[[str], None],
) -> int | None:
    """Check the parentheses opening at `i`; return the index of the node variable in them.

    `enclosing` is the bracket the parentheses stand in: "(", "[", "{" or "" at the top level.
    """
    prev = tokens[i - 1] if i else None
    after = tokens[close + 1] if close + 1 < len(tokens) else None
    after2 = tokens[close + 2] if close + 2 < len(tokens) else None
    definite = (
        _is_word(prev, "MATCH")
        or _is_punct(prev, "{")
        or (clause == "MATCH" and _is_punct(prev, "=", ","))
    )
    left = _is_punct(prev, "-") or (
        _is_punct(prev, ">") and i >= 2 and _is_punct(tokens[i - 2], "-")
    )
    right = _is_punct(after, "-") or (_is_punct(after, "<") and _is_punct(after2, "-"))
    linked = left or right
    if not (definite or linked):
        return None  # an expression, a function call or a label test, not a pattern
    body = tokens[i + 1 : close]
    if body and _is_word(body[0], "WHERE"):
        # `(where:Service)` would bind a variable that reads as a keyword.
        add(_BAD_NODE)
        return None
    parsed = _parse_node_body(body)
    if parsed is None:
        if definite:
            add(_BAD_NODE)
        return None
    var, labeled = parsed
    # The `-` beside a node belongs to a relationship bracket: no `(a)-(b)`, `(a)->(b)`, `-(s)`.
    before_link = i - 2 if _is_punct(prev, "-") else i - 3
    after_link = close + 2 if _is_punct(after, "-") else close + 3
    if (left and not (before_link >= 0 and _is_punct(tokens[before_link], "]"))) or (
        right and not (after_link < len(tokens) and _is_punct(tokens[after_link], "["))
    ):
        add(_BAD_LINK)
    predicate = clause != "MATCH"
    if predicate:
        # A pattern as an expression: where it starts and where it ends decide what it is.
        if not left:
            path_var = _is_punct(prev, "=") and i >= 3 and _is_punct(tokens[i - 3], "[")
            if not (
                _is_word(prev, *_PREDICATE_BEFORE)
                or (enclosing == "[" and (_is_punct(prev, "[") or path_var))
            ):
                add(_BAD_PLACE)
        if not right:
            comprehension = enclosing == "[" and (_is_word(after, "WHERE") or _is_punct(after, "|"))
            if not (
                after is None
                or comprehension
                or _is_word(after, *_PREDICATE_AFTER)
                or (enclosing in ("(", "{") and _is_punct(after, ")", "}"))
            ):
                add(_BAD_PLACE)
    if labeled:
        if var and predicate and enclosing != "[" and var not in bound:
            add(
                "a pattern predicate cannot introduce a new variable; "
                "use EXISTS { MATCH ... } or a pattern comprehension"
            )
        elif var:
            bound.add(var)
    elif var is None:
        add("anonymous node pattern () needs a label, e.g. (:Service)")
    elif var not in bound:
        name = var if len(var) <= 40 else var[:37] + "..."
        add(f"node pattern ({name}) has no label and '{name}' is not bound with a label earlier")
    return i + 1 if var is not None else None


def _wraps_a_pattern(tokens: list[Token], i: int, pairs: dict[int, int]) -> bool:
    """`((a)-[:T]->(b))`: the parentheses at `i` enclose a path pattern."""
    inner = i + 1
    if not _is_punct(tokens[inner], "("):
        return False
    close = pairs[inner]
    after = tokens[close + 1] if close + 1 < len(tokens) else None
    after2 = tokens[close + 2] if close + 2 < len(tokens) else None
    linked = _is_punct(after, "-") or (_is_punct(after, "<") and _is_punct(after2, "-"))
    return linked and _parse_node_body(tokens[inner + 1 : close]) is not None


def _check_relationship(
    tokens: list[Token],
    i: int,
    close: int,
    pairs: dict[int, int],
    starts: dict[int, int],
    info: PatternInfo,
    add: Callable[[str], None],
) -> None:
    """Check the relationship bracket at `i`. `starts` maps a closing bracket to its opener."""
    body = tokens[i + 1 : close]
    # Both neighbours are node patterns. `(s.name)-[:T]->(:X)` and `(1)-[:T]->(:X)` are not
    # shaped like nodes, so the node checks would pass over them in silence.
    left_close = i - 3 if i >= 3 and _is_punct(tokens[i - 2], "<") else i - 2
    left_open = starts.get(left_close) if left_close >= 0 else None
    if (
        left_open is None
        or not _is_punct(tokens[left_close], ")")
        or _parse_node_body(tokens[left_open + 1 : left_close]) is None
    ):
        add(_BAD_LINK)
    if not _relationship_is_typed(body):
        add("relationship pattern must specify a type, e.g. [:REQUIRES]")
    if not _relationship_is_one_hop(body):
        add(_BAD_RELATIONSHIP)
    if body and body[0].kind == WORD:
        info.entity_vars.add(i + 1)
    if (
        i >= 2
        and _is_punct(tokens[i - 2], "<")
        and close + 2 < len(tokens)
        and _is_punct(tokens[close + 2], ">")
    ):
        add(_BAD_LINK)  # `<-[:T]->`
    # `]-(` or `]->(`: anything else after the bracket is a quantifier (`->+`, `->{1,3}`).
    j = close + 1
    ok = j < len(tokens) and _is_punct(tokens[j], "-")
    j += 1
    if ok and j < len(tokens) and _is_punct(tokens[j], ">"):
        j += 1
    if not (ok and j < len(tokens) and _is_punct(tokens[j], "(")):
        add(_BAD_RELATIONSHIP)
    elif _parse_node_body(tokens[j + 1 : pairs[j]]) is None:
        add(_BAD_LINK)


def check_patterns(tokens: list[Token], add: Callable[[str], None]) -> PatternInfo | None:
    """Report node and relationship patterns that are not explicit. Never raises on tokens.

    Returns None when the brackets are unbalanced (the main pass reports that).
    """
    pairs = _match_brackets(tokens)
    if pairs is None:
        return None

    starts = {close: start for start, close in pairs.items()}
    info = PatternInfo()
    bound: set[str] = set()  # variables bound with a label and still in scope
    restore: dict[int, set[str]] = {}  # closing bracket index -> scope to return to
    resets: dict[int, set[str]] = {}  # index where a WITH ends -> scope after it
    clauses = [""]  # the clause word currently open at each bracket depth
    opens = [""]  # the bracket open at each depth

    for i, tok in enumerate(tokens):
        if i in resets:
            bound = resets.pop(i)
        if i in restore:
            bound = restore.pop(i)
        prev = tokens[i - 1] if i else None
        nxt = tokens[i + 1] if i + 1 < len(tokens) else None
        nxt2 = tokens[i + 2] if i + 2 < len(tokens) else None
        in_match = clauses[-1] == "MATCH"

        if tok.kind == PUNCT:
            if tok.value in _OPEN:
                close = pairs[i]
                if tok.value == "(":
                    if _is_punct(prev, ")"):
                        add("'(' directly after ')' is not allowed (quantified path patterns)")
                    elif in_match and not (
                        _is_word(prev, "MATCH")
                        or _is_punct(prev, ",", "=", "-", "{")
                        or (_is_punct(prev, ">") and i >= 2 and _is_punct(tokens[i - 2], "-"))
                    ):
                        add(_BAD_MATCH)
                    if _wraps_a_pattern(tokens, i, pairs):
                        add("parenthesized or quantified path patterns are not allowed")
                    var = _check_node(tokens, i, close, clauses[-1], opens[-1], bound, add)
                    if var is not None:
                        info.entity_vars.add(var)
                elif tok.value == "[":
                    if _is_punct(prev, "-"):
                        _check_relationship(tokens, i, close, pairs, starts, info, add)
                    else:
                        if in_match:
                            add(_BAD_MATCH)
                        restore[close] = set(bound)
                elif opens_subquery(tokens, i):
                    restore[close] = set(bound)
                    clauses.append("MATCH")  # a body without a clause word is a pattern list
                    opens.append("{")
                    continue
                elif in_match:
                    add(_BAD_MATCH)  # `->{1,3}`: a quantifier
                clauses.append("")
                opens.append(tok.value)
            elif tok.value in _CLOSE:
                clauses.pop()
                opens.pop()
            else:
                if tok.value == "-" and _is_punct(nxt, "-"):
                    add("untyped relationship shorthand (--, -->, <--) is not allowed; use [:TYPE]")
                if in_match and (
                    tok.value not in _MATCH_PUNCT
                    or (tok.value == "=" and (i - 1) not in info.entity_vars)
                ):
                    add(_BAD_MATCH)
            continue

        if tok.kind != WORD:
            if in_match:
                add(_BAD_MATCH)
            continue
        if _is_punct(prev, ".", ":"):
            continue
        word = tok.value.upper()
        if word == "WITH" and _is_word(prev, "STARTS", "ENDS"):
            continue
        # `p = (...)` where a pattern may start binds a path variable, whatever the word is.
        if (
            _is_punct(nxt, "=")
            and _is_punct(nxt2, "(")
            and (
                _is_punct(prev, "[")
                or (in_match and (_is_word(prev, "MATCH") or _is_punct(prev, ",", "{")))
            )
        ):
            info.entity_vars.add(i)
            continue
        if word in _CLAUSES:
            clauses[-1] = word
        elif in_match and word != "OPTIONAL":
            add(_BAD_MATCH)
        if word == "WITH":
            end, kept, bare = _with_projection(tokens, i + 1, bound)
            resets[end] = kept
            info.with_items |= bare
    return info
