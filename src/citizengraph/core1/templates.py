"""Canonical read-only Cypher for Core 1: the ONE source of truth.

The same text is (1) the gold completion the model is trained on, (2) the parameterized
fallback when the model's query is rejected or fails, and (3) the "templates-only" baseline.
Every template passes ``validate_cypher``; ``tests/test_core1_templates.py`` enforces it.

Parameter contract
------------------
Ids are NEVER written into the query text, so the model never has to reproduce them. A query
uses only these parameters, passed to the driver next to the text:

``$sid``
    ``Service.id`` (string), e.g. ``"business_permit"``. Used by every service-level template.
``$sid2``
    A second ``Service.id``, used only by the comparison shapes (``compare_*``).
``$oid``
    ``Office.id`` (``bplo``, ``lcro``, ``cho``, ``cswdo``), used by the office-level shapes.
``$aid``
    ``Agency.id`` (the slug of the agency name, e.g. ``"civil-registry-office"``), used by the
    agency lookup.
``$doc``
    Document words, lowercase (e.g. ``"barangay clearance"``): a requirement mentions the document
    when ``toLower(r.text) CONTAINS $doc``. Used by the document lookups.
``$variant_ids``
    List of ``Variant.id`` strings in the form ``dimension:value`` (the ids in
    ``graph/seed/variants.yaml``), e.g. ``["business_type:corporation", "applicant_type:new"]``.
    Used by the *filtered* templates only, which take at least one id. ``Slots.variant_ids``
    builds it (sorted).

The parameters come from the "targets" the gateway found (``core1/targets.py`` maps a target
list to these names); a template's ``needs`` says which it cannot run without. The model never
writes a parameter's value, only its name.

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

Shapes. The four session-5 shapes: ``list`` (every intent), ``count`` (requirements, steps),
``per_step`` (fees, through ``CHARGES``) and ``go_first`` (where_to_secure, cross-office through
``SATISFIED_BY`` / ``SECURED_AT`` + ``IS_OFFICE``). Session 5b adds ``NEW_SHAPES``: reverse lookups
by document or agency, office listings and counts, cross-office prerequisites of an office,
cheapest services and services with no fee rows, fee totals, fee plus time in one query, longest
and external steps, and comparisons of two services. The shape (and the intent) is chosen from the
citizen's wording, not from a slot. A few shapes answer two intents at once (``fee_time`` is fees
plus processing_time); ``Template.intents`` lists them, primary first.

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

Limits of the new shapes (the composer has to respect them):

* ``fees_total`` sums the fee rows the filter keeps. Fee rows can be alternatives or ranges, so it
  is NOT the charter's stated total: it also returns ``total_fee_text`` and ``n_unresolved`` (fee
  rows whose condition is text only and could not be filtered) next to the sums; a partly
  structured condition cannot be told apart through the allow-list.
* ``cheapest`` is the lowest ``amount_min`` of a service's fee rows; ``no_fee_rows`` lists services
  with no fee row. Neither means "free": the charter's blank and "None" are both "no row".
* ``longest_step`` orders by the derived ``minutes_max`` (a day is 1,440 minutes, working or
  calendar unknown), so the comparison across units is approximate; the step is returned with its
  own value and unit.
* ``office_prereqs`` drops prerequisites that point back at the same office.
* the ``doc_*`` shapes match the document words inside free requirement text (substring, lowercase).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from citizengraph.core1.slots import INTENTS, Slots
from citizengraph.guardrail.lexer import PUNCT, WORD, tokenize
from citizengraph.guardrail.schema import OFFICIAL_SCHEMA, Schema

ROW_LIMIT = 50  # must not exceed core1.cypher_limit_max (config/limits.yaml); a test checks it

CORE1_INTENTS = tuple(i for i in INTENTS if i != "status")
LEGACY_SHAPES = ("list", "count", "per_step", "go_first")  # session 5
NEW_SHAPES = (
    "doc_services",
    "doc_where",
    "doc_in_service",
    "agency_services",
    "office_services",
    "office_count",
    "office_req_counts",
    "office_who",
    "office_prereqs",
    "cheapest",
    "no_fee_rows",
    "fees_total",
    "fee_time",
    "longest_step",
    "external_steps",
    "compare_fees",
    "compare_requirements",
    "compare_time",
)
SHAPES = LEGACY_SHAPES + NEW_SHAPES

# Parameter name <- what the target list supplies (core1/targets.py).
PARAMETERS = ("sid", "sid2", "oid", "aid", "doc", "variant_ids")

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


class MissingTarget(ValueError):
    """The template needs a parameter (office, agency, document, second service) that was not
    given."""


@dataclass(frozen=True)
class Template:
    intent: str  # primary intent (the key)
    shape: str
    filtered: bool
    cypher: str
    params: tuple[str, ...]  # parameter names the text uses, sorted
    intents: tuple[str, ...] = ()  # every intent the answer serves, primary first

    @property
    def needs(self) -> tuple[str, ...]:
        """Parameters that come from targets (everything but ``variant_ids``)."""
        return tuple(p for p in self.params if p != "variant_ids")

    @property
    def intent_header(self) -> str:
        """``fees`` or ``fees+processing_time``: what the completion's intent line says."""
        return "+".join(self.intents or (self.intent,))

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

    def add(intent: str, shape: str, filtered: bool, cypher: str, *also: str) -> None:
        out[(intent, shape, filtered)] = Template(
            intent, shape, filtered, cypher, _sorted_params(cypher), (intent, *also)
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
    _add_new_shapes(add, schema, limit)
    return out


def _add_new_shapes(add, schema: Schema, limit: str) -> None:
    """Session 5b shapes (see NEW_SHAPES and the module docstring)."""
    service = "MATCH (s:Service {id: $sid})"
    office = "MATCH (o:Office {id: $oid})-[:OFFERS]->(s:Service)"
    doc_match = "toLower(r.text) CONTAINS $doc"

    # reverse lookups by document or agency
    add(
        "requirements",
        "doc_services",
        False,
        _query(
            "MATCH (s:Service)-[:REQUIRES]->(r:Requirement)",
            f"WHERE {doc_match}",
            "RETURN "
            + ", ".join(
                _return(schema, "s", ("id", "name")) + _return(schema, "r", ("id", "text"))
            ),
            "ORDER BY s.id, r.id",
            limit,
        ),
    )
    add(
        "where_to_secure",
        "doc_where",
        False,
        _query(
            "MATCH (s:Service)-[:REQUIRES]->(r:Requirement)-[:SECURED_AT]->(a:Agency)",
            f"WHERE {doc_match}",
            "RETURN s.id, r.id, r.text, a.name",
            "ORDER BY s.id, r.id",
            limit,
        ),
    )
    for filtered in (False, True):
        add(
            "requirements",
            "doc_in_service",
            filtered,
            _query(
                f"{service}-[:REQUIRES]->(r:Requirement)",
                _where(filtered, "r", doc_match),
                "RETURN " + ", ".join(_return(schema, "r", ("id", "text", "condition_text"))),
                "ORDER BY r.id",
                limit,
            ),
        )
    add(
        "where_to_secure",
        "agency_services",
        False,
        _query(
            "MATCH (s:Service)-[:REQUIRES]->(r:Requirement)-[:SECURED_AT]->(a:Agency {id: $aid})",
            "RETURN s.id, s.name, a.name, count(r) AS n",
            "ORDER BY s.id",
            limit,
        ),
    )

    # office-level listings, counts and prerequisites
    add(
        "office",
        "office_services",
        False,
        _query(office, "RETURN o.name, s.id, s.name", "ORDER BY s.id", limit),
    )
    add(
        "office",
        "office_count",
        False,
        _query(office, "RETURN o.name, count(s) AS n", "LIMIT 1"),
    )
    add(
        "requirements",
        "office_req_counts",
        False,
        _query(
            office,
            "RETURN s.id, s.name, COUNT { (s)-[:REQUIRES]->(r:Requirement) WHERE r.group = false } AS n",
            "ORDER BY n DESC, s.id",
            limit,
        ),
    )
    add(
        "who_may_avail",
        "office_who",
        False,
        _query(office, "RETURN s.id, s.name, s.who_may_avail", "ORDER BY s.id", limit),
    )
    add(
        "where_to_secure",
        "office_prereqs",
        False,
        _query(
            f"{office}-[:REQUIRES]->(r:Requirement)",
            "OPTIONAL MATCH (r)-[:SATISFIED_BY]->(d:Service)<-[:OFFERS]-(o1:Office)",
            "OPTIONAL MATCH (r)-[:SECURED_AT]->(a:Agency)-[:IS_OFFICE]->(o2:Office)",
            "WITH s, r, d, o1, a, o2",
            "WHERE (d IS NOT NULL AND o1.id <> $oid) OR (o2 IS NOT NULL AND o2.id <> $oid)",
            "RETURN s.id, r.id, r.text, d.name, o1.name, a.name, o2.name",
            "ORDER BY s.id, r.id",
            limit,
        ),
    )

    # cheapest services and services with no fee row (never "free": a blank is not a zero)
    add(
        "fees",
        "cheapest",
        False,
        _query(
            f"{office}-[:HAS_FEE]->(f:Fee)",
            "RETURN s.id, s.name, min(f.amount_min) AS lowest",
            "ORDER BY lowest, s.id",
            "LIMIT 5",
        ),
    )
    add(
        "fees",
        "no_fee_rows",
        False,
        _query(
            office,
            "WHERE NOT EXISTS { MATCH (s)-[:HAS_FEE]->(:Fee) }",
            "RETURN s.id, s.name",
            "ORDER BY s.id",
            limit,
        ),
    )

    # fee totals and fee plus time, with the variant filter
    unresolved = (
        "count(CASE WHEN f.condition_text IS NOT NULL "
        "AND NOT EXISTS { MATCH (f)-[:APPLIES_WHEN]->(:Variant) } THEN 1 END) AS n_unresolved"
    )
    time_cols = _return(schema, "s", ("total_time_text",)) + _return(
        schema,
        "st",
        ("id", "order", "dur_min", "dur_max", "dur_unit", "day_type", "external_agency"),
    )
    fee_cols = _return(
        schema, "f", ("id", "label", "amount_min", "amount_max", "unit", "note", "condition_text")
    )
    for filtered in (False, True):
        add(
            "fees",
            "fees_total",
            filtered,
            _query(
                f"{service}-[:HAS_FEE]->(f:Fee)",
                _where(filtered, "f"),
                "RETURN s.total_fee_text, sum(f.amount_min) AS total_min, "
                "sum(f.amount_max) AS total_max, count(f) AS n_fees, " + unresolved,
                "LIMIT 1",
            ),
        )
        add(
            "fees",
            "fee_time",
            filtered,
            _query(
                f"{service}-[:HAS_STEP]->(st:Step)",
                "OPTIONAL MATCH (st)-[:CHARGES]->(f:Fee)",
                _where(filtered, "f"),
                "RETURN " + ", ".join(time_cols + fee_cols),
                "ORDER BY st.order, f.id",
                limit,
            ),
            "processing_time",
        )

    # steps
    step_cols = _return(
        schema,
        "st",
        (
            "id",
            "order",
            "citizen_action",
            "agency_action",
            "dur_min",
            "dur_max",
            "dur_unit",
            "day_type",
            "external_agency",
        ),
    )
    add(
        "processing_time",
        "longest_step",
        False,
        _query(
            f"{service}-[:HAS_STEP]->(st:Step)",
            "WHERE st.minutes_max IS NOT NULL",
            "RETURN " + ", ".join(step_cols),
            "ORDER BY st.minutes_max DESC, st.order",
            "LIMIT 1",
        ),
    )
    add(
        "steps",
        "external_steps",
        False,
        _query(
            f"{service}-[:HAS_STEP]->(st:Step)",
            "WHERE st.external_agency IS NOT NULL",
            "RETURN "
            + ", ".join(
                _return(
                    schema,
                    "st",
                    ("id", "order", "citizen_action", "agency_action", "external_agency"),
                )
            ),
            "ORDER BY st.order",
            limit,
        ),
    )

    # comparing two services
    two = "MATCH (s:Service)\nWHERE s.id IN [$sid, $sid2]"
    add(
        "fees",
        "compare_fees",
        False,
        _query(
            two,
            "OPTIONAL MATCH (s)-[:HAS_FEE]->(f:Fee)",
            "RETURN s.id, s.name, s.total_fee_text, count(f) AS n_fees, "
            "min(f.amount_min) AS lowest, max(f.amount_max) AS highest",
            "ORDER BY s.id",
            "LIMIT 2",
        ),
    )
    add(
        "requirements",
        "compare_requirements",
        False,
        _query(
            two,
            "RETURN s.id, s.name, "
            "COUNT { (s)-[:REQUIRES]->(r:Requirement) WHERE r.group = false } AS n_requirements, "
            "COUNT { (s)-[:HAS_STEP]->(:Step) } AS n_steps",
            "ORDER BY s.id",
            "LIMIT 2",
        ),
    )
    add(
        "processing_time",
        "compare_time",
        False,
        _query(
            "MATCH (s:Service)-[:HAS_STEP]->(st:Step)",
            "WHERE s.id IN [$sid, $sid2]",
            "RETURN s.id, s.name, s.total_time_text, st.id, st.order, st.dur_min, st.dur_max, "
            "st.dur_unit, st.day_type",
            "ORDER BY s.id, st.order",
            limit,
        ),
    )


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
    """Canonical query plus its parameters for a service-level request (``$sid`` only): the
    fallback and the templates-only baseline. A shape that needs an office, agency, document or
    second service raises ``MissingTarget``; build those with ``targets.build_request_query``."""
    template = select_template(slots, shape)
    missing = [p for p in template.needs if p != "sid"]
    if missing:
        raise MissingTarget(f"{shape!r} needs {', '.join('$' + p for p in missing)}")
    params: dict[str, object] = {"sid": slots.service_id}
    if template.filtered:
        params["variant_ids"] = slots.variant_ids
    return Query(template.cypher, params)


def usage(
    intent: str | None,
    schema: Schema = OFFICIAL_SCHEMA,
    shapes: Iterable[str] | None = None,
) -> tuple[set[str], set[str], set[str]]:
    """Labels, relationship types and properties the templates of one intent (all intents when
    ``intent`` is None) use, read from the query text with the guardrail's own tokenizer (so a
    prompt's schema slice cannot drift from the queries). ``shapes`` limits it to some shapes."""
    wanted = set(shapes) if shapes is not None else None
    templates = [
        t
        for t in build_templates(schema).values()
        if (intent is None or t.intent == intent) and (wanted is None or t.shape in wanted)
    ]
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
