"""Splitter: one citizen message -> drafts, one per (service mention, intent).

A message names one or more services. Between two service mentions the splitter looks for a
boundary: the last sentence end (". ? ! ;") or, failing that, the last joining word or mark
("and", "at", "saka", "tapos", "&", "+", "/", ","), failing that the end of the last intent
phrase in the gap (it belongs to the left mention), failing that the start of the next mention.
Each part gets its own intents and variant cues; a part with no intent of its own takes the
nearest part's ("fees for X and Y", "X and Y fees"). A part with several intents gives several
drafts ("fees and requirements of X").

Office mentions never split a message: they only help pick a service (see the linker).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise

from citizengraph.gateway.config import GatewayConfig
from citizengraph.gateway.intents import IntentHit
from citizengraph.gateway.lexicon import Lexicon
from citizengraph.gateway.linker import Mention
from citizengraph.gateway.normalize import Normalized
from citizengraph.gateway.types import Draft, Language

STRONG_SEPARATORS = frozenset(".?!;")
JOINING_MARKS = frozenset(",&+/")
PHRASE_WINDOW_WORDS = 8
MERGE_MAX_GAP_WORDS = 3


@dataclass(frozen=True)
class _Cue:
    start: int
    dimension: str
    value: str


def _segments(
    norm: Normalized,
    service_mentions: Sequence[Mention],
    intents: Sequence[IntentHit],
    lexicon: Lexicon,
) -> list[tuple[int, int]]:
    """Token ranges [start, end), one per service mention; skipped separator tokens belong to no
    range."""
    tokens = norm.tokens
    cuts: list[tuple[int, int]] = []  # (left_end, right_start) between neighbouring mentions
    for prev, nxt in pairwise(service_mentions):
        gap = range(prev.end, nxt.start)
        strong = [i for i in gap if tokens[i].text in STRONG_SEPARATORS]
        joiners = [
            i
            for i in gap
            if tokens[i].text in JOINING_MARKS or tokens[i].text in lexicon.conjunctions
        ]
        if strong:
            cuts.append((strong[-1], strong[-1] + 1))
        elif joiners:
            cuts.append((joiners[-1], joiners[-1] + 1))
        else:
            in_gap = [h for h in intents if prev.end <= h.start and h.end <= nxt.start]
            edge = max((h.end for h in in_gap), default=nxt.start)
            cuts.append((edge, edge))
    bounds: list[tuple[int, int]] = []
    start = 0
    for left_end, right_start in cuts:
        bounds.append((start, left_end))
        start = right_start
    bounds.append((start, len(tokens)))
    return bounds


def _merge_adjacent(
    norm: Normalized,
    mentions: list[Mention],
    intents: Sequence[IntentHit],
    lexicon: Lexicon,
) -> tuple[list[Mention], bool]:
    """ "change of first name in birth certificate" names two services in ONE request. When two
    mentions are joined only by a few stop words (no joining word, no mark, no intent between
    them) and either both mean the same service ("business permit for a new business"), one says
    more than the other ("birth certificate newborn"), or exactly one is ambiguous and a word sits
    between them, keep the clear one."""
    merged = False
    out: list[Mention] = []
    for mention in mentions:
        if out:
            prev = out[-1]
            gap = norm.tokens[prev.end : mention.start]
            gap_words = [t.text for t in gap]
            joined_loosely = (
                len(gap) <= MERGE_MAX_GAP_WORDS
                and all(t.is_word and t.text in lexicon.stopwords for t in gap)
                and not any(w in lexicon.conjunctions for w in gap_words)
                and not any(prev.end <= h.start and h.end <= mention.start for h in intents)
            )
            a, b = set(prev.targets), set(mention.targets)
            same = a == b
            refines = a < b or b < a  # "birth certificate newborn": the clear one says more
            one_clear = prev.ambiguous != mention.ambiguous and len(gap) > 0
            if joined_loosely and (same or refines or one_clear):
                if len(a) > len(b):
                    out[-1] = mention
                merged = True
                continue
        out.append(mention)
    return out, merged


def _phrase(
    norm: Normalized, lo: int, hi: int, mention: Mention, cfg: GatewayConfig, drop_unknown: bool
) -> str:
    """Cleaned words of the part, limited to a window around the mention."""
    lo = max(lo, mention.start - PHRASE_WINDOW_WORDS)
    hi = min(hi, mention.end + PHRASE_WINDOW_WORDS)
    words = [t.text for t in norm.tokens[lo:hi] if t.is_word and (t.known or not drop_unknown)]
    out = ""
    for w in words:
        candidate = f"{out} {w}".strip()
        if len(candidate) > cfg.max_phrase_chars:
            break
        out = candidate
    return out


def split(
    norm: Normalized,
    mentions: list[Mention],
    intents: list[IntentHit],
    cues: list[tuple[int, str, str]],
    unsupported: list[tuple[int, str, str]],
    lexicon: Lexicon,
    cfg: GatewayConfig,
    language: Language,
    drop_unknown: bool,
) -> tuple[list[Draft], list[str]]:
    """Drafts for every service mention, in text order, plus reason codes."""
    service_mentions = [m for m in mentions if not m.is_office]
    if not service_mentions:
        return [], []
    service_mentions, merged = _merge_adjacent(norm, service_mentions, intents, lexicon)
    bounds = _segments(norm, service_mentions, intents, lexicon)
    reasons: list[str] = []
    if merged:
        reasons.append("merged_adjacent_mentions")
    if len({tuple(m.targets) for m in service_mentions}) > 1:
        reasons.append("multi_request")

    def in_part(index: int, part: tuple[int, int]) -> bool:
        return part[0] <= index < part[1]

    part_intents: list[list[str]] = []
    for part in bounds:
        seen: list[str] = []
        for hit in intents:
            if in_part(hit.start, part) and hit.intent not in seen:
                seen.append(hit.intent)
        part_intents.append(seen)
    for i, found in enumerate(part_intents):
        if found:
            continue
        donors = [j for j, other in enumerate(part_intents) if other]
        if donors:
            nearest = min(donors, key=lambda j: (abs(j - i), j))
            part_intents[i] = list(part_intents[nearest])

    drafts: list[Draft] = []
    seen_keys: set[tuple] = set()
    for mention, part, found in zip(service_mentions, bounds, part_intents, strict=True):
        part_cues = sorted({(d, v) for s, d, v in cues if in_part(s, part)})
        part_unsupported = sorted({(d, v) for s, d, v in unsupported if in_part(s, part)})
        phrase = _phrase(norm, part[0], part[1], mention, cfg, drop_unknown)
        targets = mention.targets
        for intent in found or [None]:
            key = (tuple(targets), intent, tuple(part_cues), tuple(part_unsupported))
            if key in seen_keys:
                continue
            seen_keys.add(key)
            drafts.append(
                Draft(
                    service_id=targets[0] if len(targets) == 1 else None,
                    candidates=targets if len(targets) > 1 else [],
                    intent=intent,
                    cues=part_cues,
                    unsupported=part_unsupported,
                    phrase=phrase,
                    language=language,
                    low_confidence=mention.best.confidence < cfg.echo_min_score,
                )
            )
    if len(drafts) > cfg.max_sub_requests:
        drafts = drafts[: cfg.max_sub_requests]
        reasons.append("sub_requests_truncated")
    return drafts, reasons
