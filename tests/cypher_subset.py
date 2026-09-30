"""A small interpreter for the read-only Cypher subset the canonical Core 1 templates use.

Purpose: run the REAL template text (``core1/templates.py``) against the REAL seed without Neo4j,
so a change in what a query means (a dropped condition, a wrong match key, a lost LIMIT) fails a
test that needs no server. The graph is built from the loader's own plan (``graph/load.py``
``build_plan``), so its nodes, properties and relationships are what a load would write.

Supported: ``MATCH`` / ``OPTIONAL MATCH`` with node and relationship patterns (one type per
relationship, either direction, property maps), ``WHERE`` (on MATCH, OPTIONAL MATCH and WITH),
``WITH`` of plain variables, ``RETURN`` with ``count`` / ``min`` / ``max`` / ``sum``, ``COUNT { ... }``
subqueries, ``ORDER BY`` (ASC/DESC, nulls last when ascending), ``LIMIT``, and
``= <> < > <= >= IN CONTAINS IS [NOT] NULL AND OR NOT`` in Cypher's three-valued logic.
Anything else raises ``Unsupported``, so a query that grows new syntax cannot pass by accident.

NOT a Neo4j replacement: it was checked only against hand-made graphs (``test_cypher_subset.py``)
and against the expectations in ``test_core1_semantics.py``. It has never been compared with a real
Neo4j run here; the ``integration`` tests stay the authority on Neo4j's own behaviour.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


class Unsupported(Exception):
    """The query uses Cypher this interpreter does not implement."""


# ---- graph --------------------------------------------------------------------------------------


@dataclass(eq=False)
class Node:
    label: str
    props: dict[str, Any]


@dataclass
class PropertyGraph:
    nodes: dict[str, dict[str, Node]] = field(default_factory=lambda: defaultdict(dict))
    out: dict[tuple[str, int], list[Node]] = field(default_factory=lambda: defaultdict(list))
    inn: dict[tuple[str, int], list[Node]] = field(default_factory=lambda: defaultdict(list))

    def add_node(self, label: str, props: dict[str, Any]) -> Node:
        node = Node(label, dict(props))
        self.nodes[label][props["id"]] = node
        return node

    def add_rel(self, rel: str, a: Node, b: Node) -> None:
        if b not in self.out[(rel, id(a))]:  # MERGE: one relationship per pair and type
            self.out[(rel, id(a))].append(b)
            self.inn[(rel, id(b))].append(a)


_REL_NAME = re.compile(r"^rel:(?P<rel>[A-Z_]+)(?::(?P<src>\w+))?$")
_REL_NODES = re.compile(r"MATCH \(a:(?P<src>\w+) \{id: row\.a\}\)\nMATCH \(b:(?P<dst>\w+)")


def graph_from_plan(plan) -> PropertyGraph:
    """Replay a ``build_plan`` result: ``node:<Label>`` batches, then ``rel:<TYPE>`` batches."""
    g = PropertyGraph()
    for batch in plan:
        if batch.name.startswith("node:"):
            for row in batch.rows:
                g.add_node(batch.name.split(":", 1)[1], row["props"])
    for batch in plan:
        if not batch.name.startswith("rel:"):
            continue
        rel = _REL_NAME.match(batch.name).group("rel")
        ends = _REL_NODES.search(batch.cypher)
        src, dst = ends.group("src"), ends.group("dst")
        for row in batch.rows:
            g.add_rel(rel, g.nodes[src][row["a"]], g.nodes[dst][row["b"]])
    return g


# ---- tokens -------------------------------------------------------------------------------------

_TOKEN = re.compile(
    r"""\s*(?:
    (?P<param>\$\w+) |
    (?P<num>\d+(?:\.\d+)?) |
    (?P<str>'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*") |
    (?P<word>[A-Za-z_]\w*) |
    (?P<punct><>|<-|->|<=|>=|[()\[\]{}:,.=<>\-|*])
    )""",
    re.VERBOSE,
)


@dataclass
class Tok:
    kind: str
    text: str
    start: int
    end: int

    @property
    def up(self) -> str:
        return self.text.upper()


def _tokenize(text: str) -> list[Tok]:
    toks, pos = [], 0
    while pos < len(text):
        if not text[pos:].strip():
            break
        m = _TOKEN.match(text, pos)
        if not m or m.end() == pos:
            raise Unsupported(f"cannot tokenize at {text[pos : pos + 20]!r}")
        kind = m.lastgroup
        toks.append(Tok(kind, m.group(kind), m.start(kind), m.end(kind)))
        pos = m.end()
    return toks


# ---- parser -------------------------------------------------------------------------------------

CLAUSE_WORDS = {"MATCH", "OPTIONAL", "WHERE", "WITH", "RETURN", "ORDER", "LIMIT"}
AGGREGATES = {"COUNT", "MIN", "MAX", "SUM"}


@dataclass
class NodePat:
    var: str | None
    label: str | None
    props: dict[str, tuple]


@dataclass
class Hop:
    rel: str
    direction: str  # "out" or "in"
    node: NodePat


@dataclass
class Pattern:
    first: NodePat
    hops: list[Hop]

    def variables(self) -> list[str]:
        nodes = [self.first] + [h.node for h in self.hops]
        return [n.var for n in nodes if n.var]


class Parser:
    def __init__(self, text: str):
        self.text = text
        self.toks = _tokenize(text)
        self.i = 0

    # token helpers
    def peek(self, k: int = 0) -> Tok | None:
        j = self.i + k
        return self.toks[j] if j < len(self.toks) else None

    def at(self, *words: str) -> bool:
        t = self.peek()
        return t is not None and t.kind in ("word", "punct") and t.up in words

    def take(self) -> Tok:
        t = self.peek()
        if t is None:
            raise Unsupported("unexpected end of query")
        self.i += 1
        return t

    def expect(self, *words: str) -> Tok:
        t = self.take()
        if t.up not in words:
            raise Unsupported(f"expected {words}, got {t.text!r}")
        return t

    def eat(self, *words: str) -> bool:
        if self.at(*words):
            self.i += 1
            return True
        return False

    # patterns
    def node_pattern(self) -> NodePat:
        self.expect("(")
        var = label = None
        props: dict[str, tuple] = {}
        t = self.peek()
        if t.kind == "word":
            var = self.take().text
        if self.eat(":"):
            label = self.take().text
            if self.at("|"):
                raise Unsupported("label alternatives")
        if self.eat("{"):
            while True:
                key = self.take().text
                self.expect(":")
                props[key] = self.expr()
                if not self.eat(","):
                    break
            self.expect("}")
        self.expect(")")
        return NodePat(var, label, props)

    def pattern(self) -> Pattern:
        first = self.node_pattern()
        hops = []
        while self.at("-", "<-"):
            direction = "in" if self.take().text == "<-" else "out"
            self.expect("[")
            self.expect(":")
            rel = self.take().text
            if self.at("|", "*"):
                raise Unsupported("relationship alternatives or variable length")
            self.expect("]")
            if direction == "in":
                self.expect("-")
            else:
                self.expect("->")
            hops.append(Hop(rel, direction, self.node_pattern()))
        return Pattern(first, hops)

    # expressions: ("or", a, b) ("and", a, b) ("not", a) ("cmp", op, a, b) ("isnull", a, negate)
    # ("prop", var, name) ("var", name) ("lit", v) ("param", name) ("list", [..]) ("fn", name, arg)
    # ("count", pattern, where)
    def expr(self) -> tuple:
        left = self.and_expr()
        while self.eat("OR"):
            left = ("or", left, self.and_expr())
        return left

    def and_expr(self) -> tuple:
        left = self.not_expr()
        while self.eat("AND"):
            left = ("and", left, self.not_expr())
        return left

    def not_expr(self) -> tuple:
        if self.eat("NOT"):
            return ("not", self.not_expr())
        return self.comparison()

    def comparison(self) -> tuple:
        left = self.primary()
        t = self.peek()
        if t is None:
            return left
        if t.up in ("=", "<>", "<", ">", "<=", ">="):
            self.i += 1
            return ("cmp", t.up, left, self.primary())
        if t.up in ("IN", "CONTAINS"):
            self.i += 1
            return ("cmp", t.up, left, self.primary())
        if t.up == "IS":
            self.i += 1
            negate = self.eat("NOT")
            self.expect("NULL")
            return ("isnull", left, negate)
        return left

    def primary(self) -> tuple:
        t = self.take()
        if t.kind == "param":
            return ("param", t.text[1:])
        if t.kind == "num":
            return ("lit", float(t.text) if "." in t.text else int(t.text))
        if t.kind == "str":
            if "\\" in t.text:
                raise Unsupported("escapes in string literals")
            return ("lit", t.text[1:-1])
        if t.text == "(":
            inner = self.expr()
            self.expect(")")
            return inner
        if t.text == "[":
            items = []
            if not self.at("]"):
                while True:
                    items.append(self.expr())
                    if not self.eat(","):
                        break
            self.expect("]")
            return ("list", items)
        if t.kind == "word":
            up = t.up
            if up in ("TRUE", "FALSE"):
                return ("lit", up == "TRUE")
            if up == "NULL":
                return ("lit", None)
            if up == "COUNT" and self.at("{"):
                self.take()
                pat = self.pattern()
                where = self.expr() if self.eat("WHERE") else None
                self.expect("}")
                return ("count", pat, where)
            if self.at("("):
                if up not in AGGREGATES and up != "TOLOWER":
                    raise Unsupported(f"function {t.text}")
                self.take()
                arg = self.expr()
                self.expect(")")
                return ("fn", up, arg)
            if self.eat("."):
                return ("prop", t.text, self.take().text)
            return ("var", t.text)
        raise Unsupported(f"unexpected token {t.text!r}")

    # clauses
    def items(self) -> list[tuple[tuple, str]]:
        items = []
        while True:
            start = self.peek().start
            e = self.expr()
            end = self.toks[self.i - 1].end
            alias = self.take().text if self.eat("AS") else self.text[start:end]
            items.append((e, alias))
            if not self.eat(","):
                return items

    def query(self) -> list[tuple]:
        clauses: list[tuple] = []
        while self.peek() is not None:
            if self.eat("OPTIONAL"):
                self.expect("MATCH")
                pat = self.pattern()
                clauses.append(("match", True, pat, self.expr() if self.eat("WHERE") else None))
            elif self.eat("MATCH"):
                pat = self.pattern()
                clauses.append(("match", False, pat, self.expr() if self.eat("WHERE") else None))
            elif self.eat("WITH"):
                items = self.items()
                clauses.append(("with", items, self.expr() if self.eat("WHERE") else None))
            elif self.eat("RETURN"):
                items = self.items()
                order: list[tuple[tuple, bool]] = []
                if self.eat("ORDER"):
                    self.expect("BY")
                    while True:
                        e = self.expr()
                        desc = self.eat("DESC")
                        if not desc:
                            self.eat("ASC")
                        order.append((e, desc))
                        if not self.eat(","):
                            break
                limit = None
                if self.eat("LIMIT"):
                    limit = int(self.take().text)
                clauses.append(("return", items, order, limit))
                if self.peek() is not None:
                    raise Unsupported("tokens after RETURN")
            else:
                raise Unsupported(f"clause starting at {self.peek().text!r}")
        if not clauses or clauses[-1][0] != "return":
            raise Unsupported("a query must end with RETURN")
        return clauses


# ---- evaluation ---------------------------------------------------------------------------------


def _and(a: Any, b: Any) -> Any:
    if a is False or b is False:
        return False
    return None if a is None or b is None else True


def _or(a: Any, b: Any) -> Any:
    if a is True or b is True:
        return True
    return None if a is None or b is None else False


def _has_aggregate(e: tuple) -> bool:
    if e[0] == "fn" and e[1] in AGGREGATES:
        return True
    return any(_has_aggregate(x) for x in e[1:] if isinstance(x, tuple)) or any(
        _has_aggregate(y) for x in e[1:] if isinstance(x, list) for y in x
    )


class Runner:
    def __init__(self, graph: PropertyGraph, params: dict[str, Any]):
        self.g = graph
        self.params = params

    # expressions
    def ev(self, e: tuple, env: dict[str, Any], group: list[dict] | None = None) -> Any:
        kind = e[0]
        if kind == "lit":
            return e[1]
        if kind == "param":
            return self.params[e[1]]  # a missing parameter is a test error, not a null
        if kind == "var":
            return env[e[1]]
        if kind == "prop":
            node = env[e[1]]
            return None if node is None else node.props.get(e[2])
        if kind == "list":
            return [self.ev(x, env, group) for x in e[1]]
        if kind == "and":
            return _and(self.ev(e[1], env, group), self.ev(e[2], env, group))
        if kind == "or":
            return _or(self.ev(e[1], env, group), self.ev(e[2], env, group))
        if kind == "not":
            v = self.ev(e[1], env, group)
            return None if v is None else not v
        if kind == "isnull":
            return (self.ev(e[1], env, group) is None) != e[2]
        if kind == "cmp":
            return self.compare(e[1], self.ev(e[2], env, group), self.ev(e[3], env, group))
        if kind == "count":
            return sum(
                1 for ext in self.match(e[1], env) if e[2] is None or self.ev(e[2], ext) is True
            )
        if kind == "fn":
            if e[1] == "TOLOWER":
                v = self.ev(e[2], env, group)
                return None if v is None else v.lower()
            if group is None:
                raise Unsupported("aggregate outside RETURN")
            values = [self.ev(e[2], g) for g in group]
            values = [v for v in values if v is not None]
            if e[1] == "COUNT":
                return len(values)
            if not values:
                return None
            return {"MIN": min, "MAX": max, "SUM": sum}[e[1]](values)
        raise Unsupported(f"expression {kind}")

    @staticmethod
    def compare(op: str, a: Any, b: Any) -> Any:
        if op == "IN":
            if b is None or a is None:
                return None
            if a in b:
                return True
            return None if None in b else False
        if a is None or b is None:
            return None
        if op == "CONTAINS":
            return b in a
        return {
            "=": a == b,
            "<>": a != b,
            "<": a < b,
            ">": a > b,
            "<=": a <= b,
            ">=": a >= b,
        }[op]

    # patterns
    def accepts(self, node: Node | None, pat: NodePat, env: dict[str, Any]) -> bool:
        if node is None:
            return False
        if pat.label and node.label != pat.label:
            return False
        return all(node.props.get(k) == self.ev(v, env) for k, v in pat.props.items())

    def candidates(self, pat: NodePat, env: dict[str, Any]):
        if pat.var and pat.var in env:
            yield env[pat.var]
        elif pat.label:
            yield from self.g.nodes[pat.label].values()
        else:
            raise Unsupported("a node pattern without a label")

    def match(self, pattern: Pattern, env: dict[str, Any]):
        def walk(node: Node, hops: list[Hop], cur: dict[str, Any]):
            if not hops:
                yield cur
                return
            hop, rest = hops[0], hops[1:]
            table = self.g.out if hop.direction == "out" else self.g.inn
            for nxt in table.get((hop.rel, id(node)), []):
                if not self.accepts(nxt, hop.node, cur):
                    continue
                var = hop.node.var
                if var and var in cur:
                    if cur[var] is not nxt:
                        continue
                    yield from walk(nxt, rest, cur)
                else:
                    yield from walk(nxt, rest, {**cur, var: nxt} if var else cur)

        for start in self.candidates(pattern.first, env):
            if not self.accepts(start, pattern.first, env):
                continue
            var = pattern.first.var
            yield from walk(start, pattern.hops, {**env, var: start} if var else env)

    # clauses
    def run(self, clauses: list[tuple]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = [{}]
        for clause in clauses:
            kind = clause[0]
            if kind == "match":
                _, optional, pat, where = clause
                out = []
                for env in rows:
                    found = [
                        ext
                        for ext in self.match(pat, env)
                        if where is None or self.ev(where, ext) is True
                    ]
                    if found or not optional:
                        out += found
                    else:
                        out.append({**env, **{v: None for v in pat.variables() if v not in env}})
                rows = out
            elif kind == "with":
                _, items, where = clause
                if any(_has_aggregate(e) for e, _ in items):
                    raise Unsupported("aggregation in WITH")
                rows = [{a: self.ev(e, env) for e, a in items} for env in rows]
                if where is not None:
                    rows = [env for env in rows if self.ev(where, env) is True]
            else:
                return self.project(rows, *clause[1:])
        raise Unsupported("no RETURN")

    def project(self, rows, items, order, limit) -> list[dict[str, Any]]:
        aggregating = any(_has_aggregate(e) for e, _ in items)
        produced: list[tuple[dict[str, Any], dict[str, Any], list[dict]]] = []
        if aggregating:
            keys = [(e, a) for e, a in items if not _has_aggregate(e)]
            groups: dict[tuple, list[dict]] = {}
            for env in rows:
                groups.setdefault(
                    tuple(self._hashable(self.ev(e, env)) for e, _ in keys), []
                ).append(env)
            if not keys and not groups:
                groups[()] = []
            for members in groups.values():
                env0 = members[0] if members else {}
                produced.append(({a: self.ev(e, env0, members) for e, a in items}, env0, members))
        else:
            for env in rows:
                produced.append(({a: self.ev(e, env) for e, a in items}, env, [env]))
        for e, desc in reversed(order):  # stable sorts, last key first
            produced.sort(
                key=lambda p, e=e: self._sort_key(
                    self.ev(e, {**p[1], **p[0]}, p[2] if aggregating else None)
                ),
                reverse=desc,
            )
        result = [row for row, _, _ in produced]
        return result if limit is None else result[:limit]

    @staticmethod
    def _hashable(v: Any) -> Any:
        return id(v) if isinstance(v, Node) else v

    @staticmethod
    def _sort_key(v: Any) -> tuple:
        return (v is None, v if v is not None else 0)  # nulls last ascending, first descending


def run_cypher(graph: PropertyGraph, cypher: str, params: dict[str, Any] | None = None):
    """Rows as dicts keyed by the column text (``"s.id"``) or the ``AS`` alias."""
    return Runner(graph, params or {}).run(Parser(cypher).query())
