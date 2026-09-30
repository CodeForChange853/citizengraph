"""The completion format of prompt v2, and the check that turns a completion into a query.

The model answers with three header lines and then the Cypher::

    intent: fees+processing_time
    shape: fee_time
    variants: business_type:corporation
    MATCH (s:Service {id: $sid})-[:HAS_STEP]->(st:Step)
    ...

* ``intent``: one of the seven Core 1 intents, or two joined with ``+`` (primary first). This is
  how the composer learns which question was understood (it cannot read that off the Cypher).
* ``shape``: the query family (``list``, ``count``, ``fees_total``, ...); with the intent it names
  the row layout the composer renders.
* ``variants``: the ``dimension:value`` ids (``graph/seed/variants.yaml``) the citizen's wording
  stated, or ``none``. Non-empty exactly when the query is a filtered one; the ids become the
  ``$variant_ids`` parameter. The closed vocabulary is checked here, so a made-up value cannot
  reach the graph.

The header lines can never be mistaken for Cypher (a query starts with MATCH, OPTIONAL, WITH,
UNWIND or RETURN), so the format is parseable line by line. ``check_completion`` never raises: a
bad completion comes back with ``ok=False``, a list of problems and no parameters.

Policy: any completion whose Cypher passes the guardrail and whose parameters the targets can
supply may run. ``canonical`` says whether the query is exactly the template for its header; only
then may the composer trust the shape. A novel query (a shape the model generalised to) runs and is
rendered generically.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field

from citizengraph.core1.slots import check_variants, known_variants
from citizengraph.core1.targets import Request, params_for
from citizengraph.core1.templates import (
    CORE1_INTENTS,
    PARAMETERS,
    TEMPLATES,
    MissingTarget,
    Template,
)
from citizengraph.guardrail.lexer import PARAM, LexError, tokenize
from citizengraph.guardrail.validator import validate_cypher

HEADER_KEYS = ("intent", "shape", "variants")
_FENCE = re.compile(r"^```[A-Za-z]*\s*\n(.*?)\n?```\s*$", re.DOTALL)
_VARIANT_ID = re.compile(r"^[a-z][a-z0-9_]*:[A-Za-z0-9_]+$")


def format_completion(template: Template, variant_ids: Sequence[str] = ()) -> str:
    """The gold completion for a template (variants are written only when it is filtered)."""
    ids = sorted(variant_ids) if template.filtered else []
    return (
        f"intent: {template.intent_header}\n"
        f"shape: {template.shape}\n"
        f"variants: {', '.join(ids) if ids else 'none'}\n"
        f"{template.cypher}"
    )


@dataclass(frozen=True)
class Parsed:
    intents: tuple[str, ...]
    shape: str
    variant_ids: tuple[str, ...]
    cypher: str
    problems: tuple[str, ...] = ()

    @property
    def intent_header(self) -> str:
        return "+".join(self.intents)


def _unfence(text: str) -> str:
    text = text.strip()
    match = _FENCE.match(text)
    return match.group(1).strip() if match else text


def parse_completion(text: object) -> Parsed:
    """Split a completion into header fields and Cypher. Never raises."""
    if not isinstance(text, str) or not text.strip():
        return Parsed((), "", (), "", ("empty completion",))
    lines = _unfence(text).splitlines()
    fields: dict[str, str] = {}
    problems: list[str] = []
    index = 0
    for key in HEADER_KEYS:
        if index >= len(lines) or not lines[index].startswith(f"{key}:"):
            problems.append(f"missing header line '{key}:' (expected in order {HEADER_KEYS})")
            break
        fields[key] = lines[index].partition(":")[2].strip()
        if not fields[key]:
            problems.append(f"header line '{key}:' is empty")
        index += 1
    cypher = "\n".join(lines[index:]).strip()
    if not cypher:
        problems.append("no Cypher after the header")
    intents = tuple(p.strip() for p in fields.get("intent", "").split("+") if p.strip())
    variants: tuple[str, ...] = ()
    raw = fields.get("variants", "none")
    if raw not in ("", "none"):
        variants = tuple(v.strip() for v in raw.split(",") if v.strip())
    return Parsed(intents, fields.get("shape", ""), variants, cypher, tuple(problems))


@dataclass(frozen=True)
class Checked:
    ok: bool
    parsed: Parsed
    canonical: bool = False
    template: Template | None = None
    params: dict[str, object] = field(default_factory=dict)
    problems: tuple[str, ...] = ()

    @property
    def intents(self) -> tuple[str, ...]:
        return self.parsed.intents

    @property
    def shape(self) -> str:
        return self.parsed.shape

    @property
    def variant_ids(self) -> tuple[str, ...]:
        return self.parsed.variant_ids

    @property
    def cypher(self) -> str:
        return self.parsed.cypher


def _normalize(query: str) -> str:
    return " ".join(query.split())


def _params_used(cypher: str) -> set[str]:
    try:
        return {t.value.lstrip("$") for t in tokenize(cypher) if t.kind == PARAM}
    except LexError:
        return set()


def check_completion(
    text: object,
    request: Request,
    *,
    known: Mapping[str, Collection[str]] | None = None,
    service_variants: Mapping[str, Mapping[str, Collection[str]]] | None = None,
) -> Checked:
    """Validate a model completion against the request's targets. Never raises.

    ``known`` is the variant vocabulary (default: ``graph/seed/variants.yaml``);
    ``service_variants`` (service id -> dimension -> values, e.g. the gateway's catalog) also
    restricts the variants to what the first service target offers.
    """
    parsed = parse_completion(text)
    problems = list(parsed.problems)

    def fail() -> Checked:
        return Checked(False, parsed, problems=tuple(problems))

    if parsed.problems:
        return fail()

    for intent in parsed.intents:
        if intent not in CORE1_INTENTS:
            problems.append(f"intent {intent!r} is not a Core 1 intent")
    template = TEMPLATES.get((parsed.intents[0], parsed.shape, False)) if parsed.intents else None
    if template is None and not problems:
        problems.append(f"unknown intent/shape pair {parsed.intent_header}/{parsed.shape}")

    # variants: closed vocabulary, at most one value per dimension, only what the service offers
    by_dimension: dict[str, list[str]] = defaultdict(list)
    for vid in parsed.variant_ids:
        if not _VARIANT_ID.match(vid):
            problems.append(f"malformed variant id {vid[:40]!r}")
            continue
        dimension, _, value = vid.partition(":")
        by_dimension[dimension].append(value)
        problems += check_variants(
            {dimension: value}, known if known is not None else known_variants()
        )
    for dimension, values in by_dimension.items():
        if len(values) > 1:
            problems.append(f"two values for the variant dimension {dimension!r}")
    services = request.of_kind("service")
    if service_variants is not None and services:
        offered = service_variants.get(services[0], {})
        for dimension, values in by_dimension.items():
            if not set(values) <= set(offered.get(dimension, ())):
                problems.append(f"service {services[0]} has no variant {dimension}={values[0]}")

    # the Cypher: guardrail, then parameters the targets can supply
    verdict = validate_cypher(parsed.cypher)
    if not verdict.ok:
        problems.append("guardrail: " + "; ".join(verdict.reasons[:3]))
    used = _params_used(parsed.cypher)
    unknown = used - set(PARAMETERS)
    if unknown:
        problems.append("unknown parameter(s): " + ", ".join(sorted(unknown)))
    if ("variant_ids" in used) != bool(parsed.variant_ids):
        problems.append("the variants line and the variant filter in the query disagree")
    if problems:
        return fail()

    try:
        params = params_for(request, sorted(used - {"variant_ids"}), parsed.variant_ids)
    except MissingTarget as exc:
        problems.append(str(exc))
        return fail()
    exact = None
    if template is not None:
        exact = TEMPLATES.get((template.intent, template.shape, bool(parsed.variant_ids)))
    canonical = exact is not None and _normalize(exact.cypher) == _normalize(parsed.cypher)
    return Checked(
        True,
        parsed,
        canonical=canonical,
        template=exact if canonical else None,
        params=params,
    )
