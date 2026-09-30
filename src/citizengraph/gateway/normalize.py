"""Normalizer: citizen text -> cleaned, repaired tokens. Deterministic, no model.

Steps: NFKC + lowercase + accent and invisible-character removal, apostrophes dropped, hyphens to
spaces, runs of 3+ identical letters collapsed (``pleaseee``), SMS and Taglish expansions from
``lexicon/sms.yaml``, then typo repair with rapidfuzz against the lexicon.

Repair is conservative on purpose (a wrong repair could send a citizen to the wrong service):

* a word already in the lexicon is never touched;
* words shorter than 5 letters and words containing digits are never repaired;
* the edit distance is at most 1 for 5 to 7 letters and 2 for longer words (transpositions count
  as one edit), and the first letter must match unless the distance is 1;
* if two different lexicon words are equally close, the word stays as typed ("unknown" beats a
  wrong repair);
* an unknown word of 8+ letters that is exactly two lexicon words run together
  (``businesspermit``) is split.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from rapidfuzz import process
from rapidfuzz.distance import OSA

from citizengraph.gateway.lexicon import Lexicon
from citizengraph.gateway.text import apply_table, fold, is_word, tokenize

_DOUBLES = re.compile(r"(.)\1")


@dataclass(frozen=True)
class Token:
    text: str
    start: int  # offsets into ``Normalized.cleaned``
    end: int
    known: bool  # in the lexicon (after any repair), a number, or a separator
    repaired: bool = False
    original: str = ""  # the word as typed (after folding), when repaired

    @property
    def is_word(self) -> bool:
        return is_word(self.text)


@dataclass(frozen=True)
class Normalized:
    cleaned: str
    tokens: list[Token]
    repairs: list[tuple[str, str]] = field(default_factory=list)

    @property
    def words(self) -> list[Token]:
        return [t for t in self.tokens if t.is_word]

    @property
    def texts(self) -> list[str]:
        return [t.text for t in self.tokens]

    def unknown_ratio(self) -> float:
        words = self.words
        if not words:
            return 0.0
        return sum(1 for t in words if not t.known) / len(words)


def _max_distance(length: int) -> int:
    if length < 5:
        return 0
    return 1 if length <= 7 else 2


class Normalizer:
    def __init__(self, lexicon: Lexicon, cache_size: int = 4096):
        self._lex = lexicon
        self._known = lexicon.known
        self._fuzzy = lexicon.fuzzy_words
        self._cache: dict[str, str | None] = {}
        self._cache_size = cache_size

    def repair(self, word: str) -> str | list[str] | None:
        """The lexicon word(s) ``word`` was probably meant to be, or None. Cached."""
        if word in self._known or len(word) < 5 or any(c.isdigit() for c in word):
            return None
        if word in self._cache:
            cached = self._cache[word]
            return cached.split(" ") if cached and " " in cached else cached
        found = self._repair_uncached(word)
        if len(self._cache) >= self._cache_size:
            self._cache.clear()
        self._cache[word] = " ".join(found) if isinstance(found, list) else found
        return found

    def _repair_uncached(self, word: str) -> str | list[str] | None:
        collapsed = _DOUBLES.sub(r"\1", word)
        if collapsed != word and collapsed in self._known and len(collapsed) >= 4:
            return collapsed
        limit = _max_distance(len(word))
        matches = process.extract(
            word, self._fuzzy, scorer=OSA.distance, score_cutoff=limit, limit=3
        )
        usable = [(w, d) for w, d, _ in matches if d == 1 or w[0] == word[0]]
        if usable:
            best = usable[0][1]
            top = [w for w, d in usable if d == best]
            return top[0] if len(top) == 1 else None
        if len(word) >= 8:
            for cut in range(4, len(word) - 3):
                left, right = word[:cut], word[cut:]
                if left in self._known and right in self._known:
                    return [left, right]
        return None

    def __call__(self, text: str) -> Normalized:
        raw_tokens = apply_table(tokenize(fold(text)), self._lex.sms)
        texts: list[str] = []
        flags: list[tuple[bool, bool, str]] = []  # known, repaired, original
        repairs: list[tuple[str, str]] = []
        for tok in raw_tokens:
            if not is_word(tok):
                texts.append(tok)
                flags.append((True, False, ""))
                continue
            if tok in self._known or any(c.isdigit() for c in tok):
                texts.append(tok)
                flags.append((True, False, ""))
                continue
            fixed = self.repair(tok)
            if fixed is None:
                texts.append(tok)
                flags.append((False, False, ""))
            elif isinstance(fixed, list):
                for part in fixed:
                    texts.append(part)
                    flags.append((True, True, tok))
                repairs.append((tok, " ".join(fixed)))
            else:
                texts.append(fixed)
                flags.append((True, True, tok))
                repairs.append((tok, fixed))
        tokens: list[Token] = []
        pos = 0
        for text_, (known, repaired, original) in zip(texts, flags, strict=True):
            tokens.append(Token(text_, pos, pos + len(text_), known, repaired, original))
            pos += len(text_) + 1
        return Normalized(" ".join(texts), tokens, repairs)
