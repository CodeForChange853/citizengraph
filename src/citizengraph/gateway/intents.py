"""Rule-based intent detection and variant extraction. No model.

Intents come from phrase lists in ``lexicon/intents.yaml`` (English and Filipino, longest phrase
first). Variant cues come from ``lexicon/variants.yaml`` and count only for variants that exist
in ``graph/seed/variants.yaml`` AND are used by the linked service (its requirements or fees link
to them). A question with no recognizable intent has no intent: the pipeline asks, it does not
guess.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from citizengraph.gateway.lexicon import Hit, Lexicon
from citizengraph.gateway.linker import Mention
from citizengraph.gateway.normalize import Normalized
from citizengraph.graph import InMemoryGraph

WEAK_NEAR_WORDS = 5


@dataclass(frozen=True)
class IntentHit:
    start: int  # token indexes, end exclusive
    end: int
    intent: str


def _blank(norm: Normalized, mentions: list[Mention]) -> list[str]:
    """Token texts with service and office mentions turned into separators, so an intent phrase
    can never be taken from inside an alias ("BREQS processing")."""
    texts = norm.texts
    for m in mentions:
        for i in range(m.start, m.end):
            texts[i] = ","
    return texts


class IntentDetector:
    def __init__(self, lexicon: Lexicon):
        self._lex = lexicon

    def detect(self, norm: Normalized, mentions: list[Mention] | None = None) -> list[IntentHit]:
        texts = _blank(norm, mentions or [])
        hits = self._lex.intents.scan(texts)
        parsed: list[tuple[Hit, str, bool]] = []
        for hit in hits:
            intent, weak = hit.labels[0]  # type: ignore[misc]
            parsed.append((hit, intent, bool(weak)))
        strong_time = [h for h, i, w in parsed if i == "processing_time"]
        out: list[IntentHit] = []
        for hit, intent, weak in parsed:
            if weak and any(
                abs(hit.start - t.end) <= WEAK_NEAR_WORDS or abs(t.start - hit.end) <= WEAK_NEAR_WORDS
                for t in strong_time
            ):
                continue
            out.append(IntentHit(hit.start, hit.end, intent))
        return out

    def variant_cues(
        self, norm: Normalized
    ) -> tuple[list[tuple[int, str, str]], list[tuple[int, str, str]]]:
        """(start, dimension, value) for supported cues and for cues the graph has no variant for.
        Words inside a service mention count too ("new business" names the service and says new)."""
        texts = norm.texts
        supported = [
            (h.start, dim, val)
            for h in self._lex.variant_cues.scan(texts)
            for dim, val in h.labels  # type: ignore[misc]
        ]
        unsupported = [
            (h.start, dim, val)
            for h in self._lex.unsupported_cues.scan(texts)
            for dim, val in h.labels  # type: ignore[misc]
        ]
        return supported, unsupported


class VariantCatalog:
    """Which variant values each service can be narrowed by, read from the graph."""

    def __init__(self, graph: InMemoryGraph):
        known = {(v.dimension, v.value) for v in graph.seed.variants}
        dims: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        for record in (*graph.seed.requirements, *graph.seed.fees):
            for vid in record.variant_ids:
                dimension, _, value = vid.partition(":")
                if (dimension, value) in known:
                    dims[record.service_id][dimension].add(value)
        self._dims = {sid: {d: frozenset(v) for d, v in by.items()} for sid, by in dims.items()}

    def dimensions(self, service_id: str) -> dict[str, frozenset[str]]:
        return self._dims.get(service_id, {})

    def resolve(
        self,
        service_id: str,
        cues: list[tuple[str, str]],
        unsupported: list[tuple[str, str]],
    ) -> tuple[dict[str, str], list[str]]:
        """Turn cue hits into ``variants`` for this service, plus reason codes for what was left
        out: a conflict (two values of one dimension) or a value the graph does not have."""
        dims = self.dimensions(service_id)
        found: dict[str, set[str]] = defaultdict(set)
        for dimension, value in cues:
            if value in dims.get(dimension, ()):
                found[dimension].add(value)
        reasons: list[str] = []
        blocked = {d for d, _ in unsupported if d in dims}
        for dimension, value in sorted(set(unsupported)):
            if dimension in dims:
                reasons.append(f"variant_unavailable:{dimension}={value}")
        variants: dict[str, str] = {}
        for dimension in sorted(found):
            values = found[dimension]
            if len(values) == 1 and dimension not in blocked:
                variants[dimension] = next(iter(values))
            else:
                reasons.append(f"variant_conflict:{dimension}")
        return variants, reasons
