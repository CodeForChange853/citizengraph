"""Core 1 model input. ONE format, used to build the training examples and at inference.

``build_prompt(slots, schema_slice)`` returns a system message (a short fixed instruction plus the
schema slice) and a user message (the slots). The model answers with the Cypher query only.

* The system message never changes except for the schema slice, which lists only the labels,
  relationship types and properties the intent's templates use (read from the templates with the
  guardrail tokenizer and from ``guardrail/schema.py`` at runtime, so it cannot drift).
* The user message is fixed-shape lines; the citizen phrase is last, JSON-quoted on one line, so
  text inside it (newlines, quotes, "intent: office") cannot fake a slot line.
* There are no few-shot examples: the model is fine-tuned on this exact format, and examples would
  only spend the context budget (docs/specs.md section 5 trims them first anyway).

Token budget: ``prompt.max_prompt_tokens`` (1,000) in ``config/limits.yaml`` is a ceiling, and a
prompt is expected to use well under half of it. ``estimate_tokens`` is a deliberately simple,
conservative estimate (no tokenizer, no model file needed): ``ceil(characters / 3)``, and never
fewer than one token per whitespace-separated word. Llama-3 averages about 4 characters per token
on English prose and about 3 on Filipino text, identifiers and Cypher, so this over-counts a
little on purpose.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from citizengraph.core1.slots import Slots
from citizengraph.core1.templates import (
    CORE1_INTENTS,
    NODE_PROPERTIES,
    RELATIONSHIPS,
    NotCore1Intent,
    usage,
)
from citizengraph.guardrail.schema import OFFICIAL_SCHEMA, Schema

INSTRUCTION = (
    "Translate the citizen request into ONE read-only Cypher query for the charter graph.\n"
    "Output only the query.\n"
    "Write the service id as $sid and variant ids as $variant_ids; never write ids or names "
    "as literals.\n"
    "Use $variant_ids only when variants are given and the graph can filter on them.\n"
    "Use only the labels, relationship types and properties in the schema.\n"
    "End with LIMIT."
)

_LIMITS_PATH = Path(__file__).resolve().parents[3] / "config" / "limits.yaml"
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f  ]")


def _read_limits() -> tuple[int, int]:
    """(gateway.max_chars, prompt.max_prompt_tokens); the documented defaults if unreadable."""
    try:
        cfg = yaml.safe_load(_LIMITS_PATH.read_text(encoding="utf-8"))
        chars, tokens = cfg["gateway"]["max_chars"], cfg["prompt"]["max_prompt_tokens"]
        if type(chars) is int and type(tokens) is int and chars > 0 and tokens > 0:
            return chars, tokens
    except (OSError, yaml.YAMLError, LookupError, TypeError):
        pass
    return 500, 1000


MAX_PHRASE_CHARS, MAX_PROMPT_TOKENS = _read_limits()


def estimate_tokens(text: str) -> int:
    """Conservative token estimate, see the module docstring."""
    if not text:
        return 0
    return max(math.ceil(len(text) / 3), len(text.split()))


@dataclass(frozen=True)
class SchemaSlice:
    """The part of the graph schema one intent needs: label -> properties, and the
    (source label, relationship type, target label) triples between them."""

    labels: dict[str, tuple[str, ...]]
    relationships: tuple[tuple[str, str, str], ...]


def schema_slice(intent: str, schema: Schema = OFFICIAL_SCHEMA) -> SchemaSlice:
    """Labels, properties and relationships the templates of ``intent`` use, nothing more."""
    if intent not in CORE1_INTENTS:
        raise NotCore1Intent(f"intent {intent!r} is not answered by a Core 1 query")
    used_labels, used_rels, used_props = usage(intent, schema)
    labels = {
        label: tuple(p for p in props if p in used_props and p in schema.properties)
        for label, props in NODE_PROPERTIES.items()
        if label in used_labels and label in schema.labels
    }
    relationships = tuple(
        (src, rel, dst)
        for src, rel, dst in RELATIONSHIPS
        if rel in used_rels and rel in schema.relationship_types and src in labels and dst in labels
    )
    return SchemaSlice(labels, relationships)


_slice_for = schema_slice  # build_prompt's parameter of the same name shadows the function


def render_schema(slice_: SchemaSlice) -> str:
    lines = ["Schema:"]
    for label, props in slice_.labels.items():
        lines.append(f"{label} {{{', '.join(props)}}}")
    for src, rel, dst in slice_.relationships:
        lines.append(f"({src})-[:{rel}]->({dst})")
    return "\n".join(lines)


@dataclass(frozen=True)
class Prompt:
    system: str
    user: str

    def messages(self) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": self.system},
            {"role": "user", "content": self.user},
        ]

    @property
    def text(self) -> str:
        """Both messages as one string, for clients that take a plain prompt (``LLMClient``)."""
        return f"{self.system}\n\n{self.user}"

    @property
    def tokens(self) -> int:
        return estimate_tokens(self.system) + estimate_tokens(self.user)


def clean_phrase(phrase: str, max_chars: int = MAX_PHRASE_CHARS) -> str:
    """One line, no control characters, cut to ``max_chars``."""
    one_line = " ".join(_CONTROL.sub(" ", phrase).split())
    return one_line[:max_chars].rstrip()


def build_prompt(slots: Slots, schema_slice: SchemaSlice | None = None) -> Prompt:
    """The model input for one sub-request. Raises ``NotCore1Intent`` for ``status``.

    The phrase is cut further if the prompt would still exceed ``MAX_PROMPT_TOKENS``.
    """
    slice_ = schema_slice if schema_slice is not None else _slice_for(slots.intent)
    system = f"{INSTRUCTION}\n{render_schema(slice_)}"
    variants = ", ".join(f"{d}={slots.variants[d]}" for d in sorted(slots.variants)) or "none"
    head = (
        f"service: {slots.service_id}\nintent: {slots.intent}\n"
        f"variants: {variants}\nlanguage: {slots.language}\nrequest: "
    )
    phrase = clean_phrase(slots.phrase)
    while True:
        user = head + json.dumps(phrase, ensure_ascii=False)
        prompt = Prompt(system, user)
        if prompt.tokens <= MAX_PROMPT_TOKENS or not phrase:
            return prompt
        phrase = phrase[: max(0, len(phrase) - 50)].rstrip()
