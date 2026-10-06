"""Variable rules for the guardrail (docs/specs.md section 4).

Purpose: the property allow-list only sees `variable.property`. A node, relationship or path
that leaves the query whole (`RETURN s`, `RETURN *`, `collect(s)`, `RETURN p`) carries every
stored property with it, bookkeeping ones included. So entities may not be used as values.

- An **entity variable** is a node, relationship or path variable of a pattern, or an alias of
  one made by `WITH s AS t`. It may appear only: before `.property`; as the variable of a node
  or relationship pattern; in `count(s)` or `count(DISTINCT s)`; before `IS NULL` or
  `IS NOT NULL`; in a label test `s:Label`; before a map projection `s {.name}`; and as a
  whole WITH item (`WITH s`, `WITH s AS t`). Anything else is refused, which covers RETURN,
  ORDER BY, function arguments, lists, maps, CASE and comparisons.
- `RETURN *` is refused (`WITH *` only passes variables on and is fine).
- Every other name must be bound: an alias (`AS x`) or the variable of a list comprehension,
  a quantifier or `reduce`. An unknown name is refused.
- No variable or alias may be named like a keyword or like a schema label, relationship type
  or property. The guardrail would read such a name as syntax, or as a map key, while the
  database reads a variable.

Names are tracked for the whole query, not per scope: a name that is an entity anywhere is an
entity everywhere. That over-rejects reuse of a name and never under-rejects.
"""

from collections.abc import Callable

from .keywords import FORBIDDEN_FUNCTIONS, KEYWORDS
from .lexer import PUNCT, WORD, Token
from .patterns import PatternInfo
from .schema import Schema

_SYNTAX = KEYWORDS - FORBIDDEN_FUNCTIONS
_ITEM_STARTS = ("WITH", "RETURN", "DISTINCT", "UNWIND")


def _is_punct(token: Token | None, *values: str) -> bool:
    return token is not None and token.kind == PUNCT and token.value in values


def _is_word(token: Token | None, *values: str) -> bool:
    return token is not None and token.kind == WORD and token.value.upper() in values


def _short(name: str) -> str:
    return name if len(name) <= 40 else name[:37] + "..."


def check_variables(
    tokens: list[Token],
    roles: list[str | None],
    info: PatternInfo,
    schema: Schema,
    add: Callable[[str], None],
) -> None:
    """Report entity variables used as values, unknown names and reserved names.

    ``roles[i]`` is set by the main pass for the words that are a property, a map key, a
    label or a relationship type; those are not names and are skipped here.
    """
    n = len(tokens)

    def at(i: int) -> Token | None:
        return tokens[i] if 0 <= i < n else None

    def is_name(i: int) -> bool:
        tok = at(i)
        return (
            tok is not None
            and tok.kind == WORD
            and roles[i] is None
            and (i in info.entity_vars or tok.value.upper() not in _SYNTAX)
        )

    # Where names are bound as values: `AS x`, `x IN` at the start of a comprehension or a
    # quantifier, and the accumulator of reduce(). The word itself may be anything here.
    aliases: dict[int, int | None] = {}  # alias index -> index of a one-word item, if it is one
    value_bindings: set[int] = set()
    for i, tok in enumerate(tokens):
        if tok.kind != WORD or roles[i] is not None or i in info.entity_vars:
            continue
        if _is_word(at(i - 1), "AS") and roles[i - 1] is None:
            source = None
            if is_name(i - 2) and (
                i - 3 < 0 or _is_punct(at(i - 3), ",") or _is_word(at(i - 3), *_ITEM_STARTS)
            ):
                source = i - 2
            aliases[i] = source
        elif (_is_word(at(i + 1), "IN") and _is_punct(at(i - 1), "[", "(", ",")) or (
            _is_punct(at(i + 1), "=")
            and _is_punct(at(i - 1), "(")
            and _is_word(at(i - 2), "REDUCE")
        ):
            value_bindings.add(i)

    entities = {tokens[i].value for i in info.entity_vars}
    changed = True
    while changed:
        changed = False
        for alias, source in aliases.items():
            name = tokens[alias].value
            if source is not None and tokens[source].value in entities and name not in entities:
                entities.add(name)
                changed = True
    values = {tokens[i].value for i in (*aliases, *value_bindings)} - entities

    reserved_schema = schema.properties | schema.labels | schema.relationship_types
    for i in sorted({*info.entity_vars, *aliases, *value_bindings}):
        name = tokens[i].value
        if name.upper() in KEYWORDS:
            add(f"variable or alias name '{_short(name)}' is a keyword")
        elif name in reserved_schema:
            add(
                f"variable or alias name '{_short(name)}' is a schema label, "
                "relationship type or property name"
            )

    for i, tok in enumerate(tokens):
        prev, nxt = at(i - 1), at(i + 1)
        if _is_punct(tok, "*") and (
            _is_word(prev, "RETURN")
            or _is_punct(prev, ",")
            or (_is_word(prev, "DISTINCT") and _is_word(at(i - 2), "RETURN"))
        ):
            add("RETURN * is not allowed: return named properties (s.name)")
            continue
        if tok.kind != WORD or roles[i] is not None:
            continue
        if i in info.entity_vars or i in aliases:
            continue  # a binding, or a variable inside its pattern
        if i in value_bindings and tok.value not in entities:
            continue
        if tok.value.upper() in _SYNTAX:
            continue
        name = tok.value
        if name not in entities:
            if _is_punct(nxt, "("):
                continue  # a function call
            if name not in values:
                add(f"unknown variable '{_short(name)}'")
            continue
        allowed = (
            _is_punct(nxt, ".", ":", "{")
            or (_is_word(nxt, "IS"))
            or i in info.with_items
            or (
                _is_punct(nxt, ")")
                and (
                    (_is_punct(prev, "(") and _is_word(at(i - 2), "COUNT"))
                    or (
                        _is_word(prev, "DISTINCT")
                        and _is_punct(at(i - 2), "(")
                        and _is_word(at(i - 3), "COUNT")
                    )
                )
            )
        )
        if not allowed:
            add(
                f"'{_short(name)}' is a node, relationship or path: it cannot be returned or "
                f"used as a value; name the properties ({_short(name)}.name)"
            )
