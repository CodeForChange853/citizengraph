"""Alias linker: find service and office mentions anywhere in the cleaned text.

Three ways to match an alias phrase, all scanning the WHOLE accepted text (a request buried at the
end of a long noisy message is found like any other):

* exact phrase: the alias words appear next to each other (score 1.0 x kind weight);
* token set: all content words of a 2+ word alias appear within one extra word of each other, in
  any order ("certificate of birth" for "birth certificate"), never across "and"/"at"/"saka"
  (confidence 0.95, or 0.90 with one extra word);
* phrase-level fuzzy: a window of up to 3 words that holds an unrepaired word matches an alias
  with rapidfuzz ``ratio >= 90`` once spaces are removed (confidence 0.9 x ratio).

Overlaps are resolved greedily, best match first: matches that overlap the anchor and score within
``ambiguity_margin`` of it stay as candidates, unless another candidate's span strictly contains
theirs ("delayed birth registration" beats the shorter "birth registration" of another service).
Several services left standing means ambiguity. Ambiguity is then narrowed by cue words near the
mention (timely / delayed) and by a single office named elsewhere in the message. Nothing is
guessed: what is still ambiguous is returned as such and becomes a clarifying question.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from rapidfuzz import fuzz, process

from citizengraph.gateway.aliases import KIND_WEIGHT, AliasTable
from citizengraph.gateway.config import GatewayConfig
from citizengraph.gateway.lexicon import Lexicon
from citizengraph.gateway.normalize import Normalized

MAX_FUZZY_WINDOWS = 150
FUZZY_MIN_RATIO = 90.0
FUZZY_MIN_CHARS = 8
CUE_CONTEXT_WORDS = 6


@dataclass(frozen=True)
class Candidate:
    target: str
    is_office: bool
    score: float  # match confidence x kind weight
    confidence: float  # how the match was made: 1.0 exact, 0.95 / 0.90 token set, <= 0.9 fuzzy
    method: str  # exact | tokenset | fuzzy
    alias: str
    kind: str


@dataclass(frozen=True)
class _Match:
    start: int
    end: int
    cand: Candidate
    alias_idx: int = -1

    @property
    def score(self) -> float:
        return self.cand.score

    def contains(self, other: _Match) -> bool:
        return (
            self.start <= other.start
            and other.end <= self.end
            and (self.end - self.start) > (other.end - other.start)
        )


@dataclass
class Mention:
    start: int  # token indexes into Normalized.tokens, end exclusive
    end: int
    candidates: list[Candidate]  # one per target, best first
    resolved_by: str | None = None  # "cue" | "office" when ambiguity was narrowed
    notes: list[str] = field(default_factory=list)

    @property
    def ambiguous(self) -> bool:
        return len(self.candidates) > 1

    @property
    def is_office(self) -> bool:
        return self.candidates[0].is_office

    @property
    def best(self) -> Candidate:
        return self.candidates[0]

    @property
    def targets(self) -> list[str]:
        return [c.target for c in self.candidates]


@dataclass(frozen=True)
class _AliasEntry:
    target: str
    is_office: bool
    kind: str
    text: str
    words: tuple[str, ...]
    content: frozenset[str]


class Linker:
    def __init__(self, table: AliasTable, lexicon: Lexicon, cfg: GatewayConfig):
        self._cfg = cfg
        self._lex = lexicon
        self._table = table
        entries: list[_AliasEntry] = []
        for alias in table.aliases:
            words = lexicon.phrase(alias.text)
            if not words:
                continue
            content = frozenset(w for w in words if w not in lexicon.stopwords)
            entries.append(
                _AliasEntry(
                    alias.target,
                    table.is_office(alias.target),
                    alias.kind,
                    alias.text,
                    words,
                    content or frozenset(words),
                )
            )
        self._entries = entries
        self._exact: dict[tuple[str, ...], list[int]] = defaultdict(list)
        self._by_token: dict[str, list[int]] = defaultdict(list)
        self._fuzzy_by_len: dict[int, dict[str, list[int]]] = defaultdict(dict)
        self._maxlen = 1
        for idx, e in enumerate(entries):
            self._exact[e.words].append(idx)
            self._maxlen = max(self._maxlen, len(e.words))
            if len(e.content) >= 2:
                for w in e.content:
                    self._by_token[w].append(idx)
            joined = "".join(e.words)
            if len(joined) >= FUZZY_MIN_CHARS:
                self._fuzzy_by_len[len(joined)].setdefault(joined, []).append(idx)
        self._cues: dict[str, list[tuple[str, ...]]] = {}
        for entry in table.services.values():
            cues = [lexicon.phrase(c) for c in (*entry.cues_en, *entry.cues_fil)]
            self._cues[entry.id] = [c for c in cues if c]

    # ------------------------------------------------------------------ matching

    def _candidate(self, idx: int, method: str, confidence: float) -> Candidate:
        e = self._entries[idx]
        return Candidate(
            e.target, e.is_office, round(confidence * KIND_WEIGHT[e.kind], 4), confidence,
            method, e.text, e.kind,
        )  # fmt: skip

    def _runs(self, norm: Normalized) -> list[tuple[int, list[str], list[bool]]]:
        runs: list[tuple[int, list[str], list[bool]]] = []
        cur: tuple[int, list[str], list[bool]] | None = None
        for i, tok in enumerate(norm.tokens):
            if tok.is_word:
                if cur is None:
                    cur = (i, [], [])
                    runs.append(cur)
                cur[1].append(tok.text)
                cur[2].append(tok.known)
            else:
                cur = None
        return runs

    def _exact_matches(self, g: int, words: list[str]) -> list[_Match]:
        out: list[_Match] = []
        for i in range(len(words)):
            for size in range(min(self._maxlen, len(words) - i), 0, -1):
                for idx in self._exact.get(tuple(words[i : i + size]), ()):
                    out.append(
                        _Match(g + i, g + i + size, self._candidate(idx, "exact", 1.0), idx)
                    )
        return out

    def _tokenset_matches(
        self, g: int, words: list[str], exact_aliases: set[int]
    ) -> list[_Match]:
        positions: dict[str, list[int]] = defaultdict(list)
        for i, w in enumerate(words):
            positions[w].append(i)
        hits: dict[int, int] = defaultdict(int)
        for w in positions:
            for idx in self._by_token.get(w, ()):
                hits[idx] += 1
        out: list[_Match] = []
        for idx in sorted(hits):
            e = self._entries[idx]
            k = len(e.content)
            if hits[idx] != k or idx in exact_aliases:
                continue
            tokens = sorted(e.content, key=lambda t: (len(positions[t]), t))
            best: tuple[int, int, int] | None = None
            for anchor in positions[tokens[0]]:
                chosen = [anchor]
                for t in tokens[1:]:
                    chosen.append(min(positions[t], key=lambda q: (abs(q - anchor), q)))
                lo, hi = min(chosen), max(chosen)
                width = hi - lo + 1
                if width > k + 1 or len(set(chosen)) < k:
                    continue
                inner = {words[q] for q in range(lo, hi + 1) if q not in chosen}
                if inner & self._lex.conjunctions:
                    continue
                if best is None or (width, lo) < (best[0], best[1]):
                    best = (width, lo, hi)
            if best is not None:
                width, lo, hi = best
                conf = 0.95 if width == k else 0.90
                out.append(
                    _Match(g + lo, g + hi + 1, self._candidate(idx, "tokenset", conf), idx)
                )
        return out

    def _fuzzy_matches(
        self, g: int, words: list[str], known: list[bool], budget: int
    ) -> tuple[list[_Match], int]:
        out: list[_Match] = []
        n = len(words)
        for i in range(n):
            for size in (1, 2, 3):
                if i + size > n or budget <= 0:
                    continue
                if all(known[i : i + size]):
                    continue
                joined = "".join(words[i : i + size])
                if len(joined) < FUZZY_MIN_CHARS:
                    continue
                budget -= 1
                span = int(len(joined) * 0.11) + 1
                keys: list[str] = []
                for length in range(len(joined) - span, len(joined) + span + 1):
                    keys.extend(self._fuzzy_by_len.get(length, ()))
                if not keys:
                    continue
                found = process.extractOne(
                    joined, keys, scorer=fuzz.ratio, score_cutoff=FUZZY_MIN_RATIO
                )
                if found is None:
                    continue
                key, ratio, _ = found
                conf = round(0.9 * ratio / 100.0, 4)
                for idx in self._fuzzy_by_len[len(key)][key]:
                    out.append(
                        _Match(g + i, g + i + size, self._candidate(idx, "fuzzy", conf), idx)
                    )
        return out, budget

    def _all_matches(self, norm: Normalized) -> list[_Match]:
        matches: list[_Match] = []
        budget = MAX_FUZZY_WINDOWS
        for g, words, known in self._runs(norm):
            exact = self._exact_matches(g, words)
            matches.extend(exact)
            exact_aliases = {m.alias_idx for m in exact}
            matches.extend(self._tokenset_matches(g, words, exact_aliases))
            if not all(known):
                fuzzy, budget = self._fuzzy_matches(g, words, known, budget)
                matches.extend(fuzzy)
        return [m for m in matches if m.score >= self._cfg.link_min_score]

    # ---------------------------------------------------------------- resolution

    def _resolve(self, matches: list[_Match]) -> list[Mention]:
        margin = self._cfg.ambiguity_margin
        pool = sorted(
            matches,
            key=lambda m: (-m.score, -(m.end - m.start), m.start, m.cand.target, m.cand.alias),
        )
        mentions: list[Mention] = []
        while pool:
            anchor = pool[0]
            overlapping = [m for m in pool if m.start < anchor.end and anchor.start < m.end]
            near = [m for m in overlapping if m.score >= anchor.score - margin]
            alive = [
                m
                for m in near
                if not any(n.contains(m) and n.score >= m.score - margin for n in near)
            ]
            best_by_target: dict[str, _Match] = {}
            for m in alive:  # alive keeps the pool's best-first order
                best_by_target.setdefault(m.cand.target, m)
            chosen = list(best_by_target.values())
            if any(not m.cand.is_office for m in chosen):
                chosen = [m for m in chosen if not m.cand.is_office]
            start = min(m.start for m in chosen)
            end = max(m.end for m in chosen)
            mentions.append(Mention(start, end, [m.cand for m in chosen]))
            # drop everything that overlaps what was just decided, not what was merely considered
            pool = [m for m in pool if not (m.start < end and start < m.end)]
        mentions.sort(key=lambda m: m.start)
        return mentions

    def _cue_words(
        self, norm: Normalized, mention: Mention, others: list[Mention], alone: bool
    ) -> list[str]:
        """Words in and around the mention, stopping at the neighbouring mentions and, when the
        message names other services, at separators and conjunctions (a lone mention may take
        its cue from the other side of a comma)."""
        toks = norm.tokens
        words = [t.text for t in toks[mention.start : mention.end] if t.is_word]

        def walk(rng: range, limit: int) -> list[str]:
            out: list[str] = []
            for i in rng:
                t = toks[i]
                if any(o.start <= i < o.end for o in others):
                    break
                if not t.is_word or t.text in self._lex.conjunctions:
                    if alone:
                        continue
                    break
                out.append(t.text)
                if len(out) >= limit:
                    break
            return out

        right = walk(range(mention.end, len(toks)), CUE_CONTEXT_WORDS)
        left = walk(range(mention.start - 1, -1, -1), CUE_CONTEXT_WORDS)
        return left[::-1] + words + right

    @staticmethod
    def _has_phrase(words: list[str], phrase: tuple[str, ...]) -> bool:
        n = len(phrase)
        return any(tuple(words[i : i + n]) == phrase for i in range(len(words) - n + 1))

    def _narrow(self, norm: Normalized, mentions: list[Mention]) -> None:
        offices = sorted({m.best.target for m in mentions if m.is_office and not m.ambiguous})
        for mention in mentions:
            if mention.is_office or not mention.ambiguous:
                continue
            others = [m for m in mentions if m is not mention]
            alone = sum(1 for m in mentions if not m.is_office) == 1
            words = self._cue_words(norm, mention, others, alone)
            hits = {
                c.target: sum(
                    1 for cue in self._cues.get(c.target, ()) if self._has_phrase(words, cue)
                )
                for c in mention.candidates
            }
            top = max(hits.values())
            winners = [c for c in mention.candidates if hits[c.target] == top]
            if top > 0 and len(winners) == 1:
                mention.candidates, mention.resolved_by = winners, "cue"
                continue
            if len(offices) == 1:
                in_office = [
                    c
                    for c in mention.candidates
                    if self._table.services[c.target].office_id == offices[0]
                ]
                if in_office and len(in_office) < len(mention.candidates):
                    mention.candidates = in_office
                    if len(in_office) == 1:
                        mention.resolved_by = "office"

    def cue_winner(self, words: list[str], targets: list[str]) -> str | None:
        """The one target whose cue words (timely / delayed ...) occur in ``words``, if exactly
        one does; None when none or several do."""
        hits = {
            t: sum(1 for cue in self._cues.get(t, ()) if self._has_phrase(words, cue))
            for t in targets
        }
        top = max(hits.values(), default=0)
        winners = [t for t in targets if hits[t] == top]
        return winners[0] if top > 0 and len(winners) == 1 else None

    def link(self, norm: Normalized) -> list[Mention]:
        """Mentions of services and offices in the whole cleaned text, in text order."""
        mentions = self._resolve(self._all_matches(norm))
        self._narrow(norm, mentions)
        return mentions
