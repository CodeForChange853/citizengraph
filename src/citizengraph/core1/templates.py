"""Canonical read-only Cypher for Core 1: the ONE source of truth.

The same text is (1) the gold completion the model is trained on, (2) the parameterized
fallback when the model's query is rejected or fails, and (3) the "templates-only" baseline.
Every template passes ``validate_cypher``; ``tests/test_core1_templates.py`` enforces it.

Parameter contract
------------------
Ids are NEVER written into the query text, so the model never has to reproduce them. A query
uses only these parameters, passed to the driver next to the text:

``$sid``
    ``Service.id`` (string), e.g. ``"business_permit"``. Every template uses it.
``$variant_ids``
    List of ``Variant.id`` strings in the form ``dimension:value`` (the ids in
    ``graph/seed/variants.yaml``), e.g. ``["business_type:corporation", "applicant_type:new"]``.
    Used by the *filtered* templates only, which take at least one id. ``Slots.variant_ids``
    builds it (sorted).

Variant filtering
-----------------
The graph links a Requirement or Fee to the Variants it applies to (``APPLIES_WHEN``). The
filter keeps a record unless it links a variant in a dimension the citizen gave (some id of
``$variant_ids`` has that dimension) and none of its links in that dimension was asked for.
Values of one dimension are alternatives, different dimensions all have to hold, a dimension
the citizen did not give is unknown and filters nothing, and a record with no links is always
kept. This is exactly ``InMemoryGraph.requirements`` / ``fees``. Conditions the seed could not
structure (``condition_structured`` false) carry no links, so they are always returned with
their ``condition_text``. Steps, times, offices and "who may avail" have no variant links in the
graph, so their intents have no filtered template and variants are ignored there.

Shapes (per intent): ``list`` (every intent), ``count`` (requirements, steps), ``per_step``
(fees, through ``CHARGES``) and ``go_first`` (where_to_secure, cross-office through
``SATISFIED_BY`` / ``SECURED_AT`` + ``IS_OFFICE``). The shape is chosen from the citizen's
wording, not from a slot.

The allowed labels, relationship types and properties come from
``guardrail/schema.py`` at runtime: columns are dropped from the RETURN lists when the allow-list
no longer has them (see ``build_templates``). ``NODE_PROPERTIES`` and ``RELATIONSHIPS`` only say
which label owns which property and which way a relationship points (docs/specs.md section 1);
a test fails when the allow-list grows a property that nobody assigned to a label.

Known limits (guardrail trade-offs, see CLAUDE.md decisions log): every node carries a label and
every relationship a type; the ``EXISTS {}`` bodies use only ``MATCH ... WHERE`` with property
comparisons, never a bare ``WHERE x:Label``. The count shapes count leaf requirements
(``group = false``): groups such as "any two of" (``min_required``) and conditions the seed could
not structure make that number an upper bound, which the composer has to say.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from citizengraph.core1.slots import INTENTS, Slots
from citizengraph.guardrail.lexer import PUNCT, WORD, tokenize
from citizengraph.guardrail.schema import OFFICIAL_SCHEMA, Schema

ROW_LIMIT = 50  # must not exceed core1.cypher_limit_max (config/limits.yaml); a test checks it

CORE1_INTENTS = tuple(i for i in INTENTS if i != "status")
SHAPES = ("list", "count", "per_step", "go_first")

# Which label owns which property (docs/specs.md section 1). The allow-list itself is the
# guardrail's; this only assigns properties to labels for the prompt's schema slice.
NODE_PROPERTIES: dict[str, tuple[str, ...]] = {
    "Office": ("id", "name"),
    "Service": (
        "id",
        "name",
        "classification",
        "transaction_type",
        "who_may_avail",
        "total_fee_text",
        "total_time_text",
        "description",
    ),
    "Requirement": ("id", "text", "group", "parent_id", "min_required", "condition_text"),
    "Agency": ("id", "name"),
    "Step": (
        "id",
        "order",
        "citizen_action",
        "agency_action",
        "external_agency",
        "dur_min",
        "dur_max",
        "dur_unit",
        "minutes_min",
        "minutes_max",
        "day_type",
    ),
    "Role": ("id", "title"),
    "Fee": ("id", "label", "amount_min", "amount_max", "unit", "note", "condition_text"),
    "Variant": ("id", "dimension", "value"),
    "Alias": ("text", "lang"),
}

# (source label, relationship type, target label), docs/specs.md section 1.
RELATIONSHIPS: tuple[tuple[str, str, str], ...] = (
    ("Office", "OFFERS", "Service"),
    ("Service", "REQUIRES", "Requirement"),
    ("Requirement", "SECURED_AT", "Agency"),
    ("Requirement", "APPLIES_WHEN", "Variant"),
    ("Requirement", "PART_OF", "Requirement"),
    ("Service", "HAS_STEP", "Step"),
    ("Step", "NEXT", "Step"),
    ("Step", "PERFORMED_BY", "Role"),
    ("Service", "HAS_FEE", "Fee"),
    ("Step", "CHARGES", "Fee"),
    ("Fee", "APPLIES_WHEN", "Variant"),
    ("Requirement", "SATISFIED_BY", "Service"),
    ("Agency", "IS_OFFICE", "Office"),
    ("Service", "KNOWN_AS", "Alias"),
    ("Requirement", "KNOWN_AS", "Alias"),
    ("Agency", "KNOWN_AS", "Alias"),
    ("Office", "KNOWN_AS", "Alias"),
)


class NotCore1Intent(ValueError):
    """The intent is answered by another core (``status`` goes to Core 2), not by a query."""


@dataclass(frozen=True)
class Template:
    intent: str
    shape: str
    filtered: bool
    cypher: str
    params: tuple[str, ...]  # parameter names the text uses, sorted

    @property
    def key(self) -> tuple[str, str, bool]:
        return (self.intent, self.shape, self.filtered)


@dataclass(frozen=True)
class Query:
    cypher: str
    params: dict[str, object]


def _return(schema: Schema, var: str, props: Iterable[str]) -> list[str]:
    """``var.prop`` columns, leaving out properties the allow-list does not have."""
    return [f"{var}.{p}" for p in props if p in schema.properties]


def _variant_filter(var: str) -> str:
    """The variant filter as one WHERE condition on ``var`` (a Requirement or a Fee)."""
    return (
        "NOT EXISTS {\n"
        f"MATCH ({var})-[:APPLIES_WHEN]->(v:Variant)\n"
        "WHERE EXISTS { MATCH (x:Variant) WHERE x.id IN $variant_ids"
        " AND x.dimension = v.dimension }\n"
        f"AND NOT EXISTS {{ MATCH ({var})-[:APPLIES_WHEN]->(w:Variant)"
        " WHERE w.id IN $variant_ids AND w.dimension = v.dimension }\n"
        "}"
    )


def _query(*lines: str | None) -> str:
    return "\n".join(line for line in lines if line)


def _where(filtered: bool, var: str, *conditions: str) -> str | None:
    parts = list(conditions) + ([_variant_filter(var)] if filtered else [])
    return "WHERE " + " AND ".join(parts) if parts else None


def _sorted_params(cypher: str) -> tuple[str, ...]:
    return tuple(sorted({t.value.lstrip("$") for t in tokenize(cypher) if t.kind == "PARAM"}))


def build_templates(schema: Schema = OFFICIAL_SCHEMA) -> dict[tuple[str, str, bool], Template]:
    """All canonical templates, keyed by ``(intent, shape, filtered)``.

    Only RETURN columns follow the schema automatically; a label, relationship type or ordering
    property that the allow-list lost makes the guardrail reject the template, and the test fails.
    """
    out: dict[tuple[str, str, bool], Template] = {}
    limit = f"LIMIT {ROW_LIMIT}"

    def add(intent: str, shape: str, filtered: bool, cypher: str) -> None:
        out[(intent, shape, filtered)] = Template(
            intent, shape, filtered, cypher, _sorted_params(cypher)
        )

    service = "MATCH (s:Service {id: $sid})"
    req = f"{service}-[:REQUIRES]->(r:Requirement)"
    for filtered in (False, True):
        cols = _return(
            schema, "r", ("id", "text", "group", "parent_id", "min_required", "condition_text")
        )
        add(
            "requirements",
            "list",
            filtered,
            _query(req, _where(filtered, "r"), "RETURN " + ", ".join(cols), "ORDER BY r.id", limit),
        )
        add(
            "requirements",
            "count",
            filtered,
            _query(
                req,
                _where(filtered, "r", "r.group = false"),
                "RETURN count(r) AS n",
                "LIMIT 1",
            ),
        )

        fee = f"{service}-[:HAS_FEE]->(f:Fee)"
        fee_cols = _return(
            schema,
            "f",
            ("id", "label", "amount_min", "amount_max", "unit", "note", "condition_text"),
        )
        add(
            "fees",
            "list",
            filtered,
            _query(
                fee, _where(filtered, "f"), "RETURN " + ", ".join(fee_cols), "ORDER BY f.id", limit
            ),
        )
        per_step_cols = _return(schema, "st", ("id", "order", "citizen_action")) + fee_cols
        add(
            "fees",
            "per_step",
            filtered,
            _query(
                f"{service}-[:HAS_STEP]->(st:Step)-[:CHARGES]->(f:Fee)",
                _where(filtered, "f"),
                "RETURN " + ", ".join(per_step_cols),
                "ORDER BY st.order, f.id",
                limit,
            ),
        )

        secure_cols = _return(schema, "r", ("id", "text", "condition_text")) + _return(
            schema, "a", ("name",)
        )
        add(
            "where_to_secure",
            "list",
            filtered,
            _query(
                f"{req}-[:SECURED_AT]->(a:Agency)",
                _where(filtered, "r"),
                "RETURN " + ", ".join(secure_cols),
                "ORDER BY r.id",
                limit,
            ),
        )
        go_cols = (
            _return(schema, "r", ("id", "text"))
            + _return(schema, "d", ("name",))
            + _return(schema, "o1", ("name",))
            + _return(schema, "a", ("name",))
            + _return(schema, "o2", ("name",))
        )
        add(
            "where_to_secure",
            "go_first",
            filtered,
            _query(
                req,
                _where(filtered, "r"),
                "OPTIONAL MATCH (r)-[:SATISFIED_BY]->(d:Service)<-[:OFFERS]-(o1:Office)",
                "OPTIONAL MATCH (r)-[:SECURED_AT]->(a:Agency)-[:IS_OFFICE]->(o2:Office)",
                "WITH r, d, o1, a, o2",
                "WHERE d IS NOT NULL OR o2 IS NOT NULL",
                "RETURN " + ", ".join(go_cols),
                "ORDER BY r.id",
                limit,
            ),
        )

    steps = f"{service}-[:HAS_STEP]->(st:Step)"
    step_cols = _return(
        schema, "st", ("id", "order", "citizen_action", "agency_action", "external_agency")
    )
    add(
        "steps",
        "list",
        False,
        _query(steps, "RETURN " + ", ".join(step_cols), "ORDER BY st.order", limit),
    )
    add("steps", "count", False, _query(steps, "RETURN count(st) AS n", "LIMIT 1"))

    time_cols = _return(schema, "s", ("total_time_text",)) + _return(
        schema,
        "st",
        ("id", "order", "dur_min", "dur_max", "dur_unit", "day_type", "external_agency"),
    )
    add(
        "processing_time",
        "list",
        False,
        _query(steps, "RETURN " + ", ".join(time_cols), "ORDER BY st.order", limit),
    )

    who_cols = _return(schema, "s", ("id", "name", "who_may_avail"))
    add("who_may_avail", "list", False, _query(service, "RETURN " + ", ".join(who_cols), "LIMIT 1"))

    office_cols = _return(schema, "o", ("id", "name"))
    add(
        "office",
        "list",
        False,
        _query(
            "MATCH (o:Office)-[:OFFERS]->(s:Service {id: $sid})",
            "RETURN " + ", ".join(office_cols),
            "LIMIT 1",
        ),
    )
    return out


TEMPLATES: dict[tuple[str, str, bool], Template] = build_templates()


def shapes_for(intent: str) -> tuple[str, ...]:
    """Shapes that exist for an intent, in ``SHAPES`` order."""
    return tuple(s for s in SHAPES if (intent, s, False) in TEMPLATES)


def supports_variants(intent: str, shape: str = "list") -> bool:
    """True when a filtered template exists, i.e. the graph has variant links to filter on."""
    return (intent, shape, True) in TEMPLATES


def select_template(slots: Slots, shape: str = "list") -> Template:
    """The canonical template for these slots (filtered only when variants are given and the
    intent can be filtered; otherwise the variants are ignored)."""
    if slots.intent not in CORE1_INTENTS:
        raise NotCore1Intent(f"intent {slots.intent!r} is not answered by a Core 1 query")
    if (slots.intent, shape, False) not in TEMPLATES:
        raise ValueError(f"no {shape!r} template for intent {slots.intent!r}")
    filtered = bool(slots.variants) and supports_variants(slots.intent, shape)
    return TEMPLATES[(slots.intent, shape, filtered)]


def build_query(slots: Slots, shape: str = "list") -> Query:
    """Canonical query plus its parameters: the fallback and the templates-only baseline."""
    template = select_template(slots, shape)
    params: dict[str, object] = {"sid": slots.service_id}
    if template.filtered:
        params["variant_ids"] = slots.variant_ids
    return Query(template.cypher, params)


def usage(intent: str, schema: Schema = OFFICIAL_SCHEMA) -> tuple[set[str], set[str], set[str]]:
    """Labels, relationship types and properties the templates of one intent use, read from
    the query text with the guardrail's own tokenizer (so a prompt's schema slice cannot drift
    from the queries)."""
    templates = [t for t in build_templates(schema).values() if t.intent == intent]
    labels: set[str] = set()
    rels: set[str] = set()
    props: set[str] = set()
    for template in templates:
        tokens = tokenize(template.cypher)
        depth: list[str] = []
        for i, tok in enumerate(tokens):
            prev = tokens[i - 1] if i else None
            nxt = tokens[i + 1] if i + 1 < len(tokens) else None
            if tok.kind == PUNCT and tok.value in "([{":
                depth.append(tok.value)
            elif tok.kind == PUNCT and tok.value in ")]}":
                depth.pop()
            elif tok.kind == WORD:
                after_dot = prev is not None and prev.kind == PUNCT and prev.value == "."
                after_colon = prev is not None and prev.kind == PUNCT and prev.value == ":"
                if after_dot:
                    props.add(tok.value)
                elif after_colon and depth and depth[-1] == "(":
                    labels.add(tok.value)
                elif after_colon and depth and depth[-1] == "[":
                    rels.add(tok.value)
                elif (
                    depth
                    and depth[-1] == "{"
                    and nxt is not None
                    and nxt.kind == PUNCT
                    and nxt.value == ":"
                ):
                    props.add(tok.value)
    return labels, rels, props
