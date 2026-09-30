"""Spam gate: rate limit, repeated messages, length caps, gibberish score, and a detector for
instruction-like or mutating text. Deterministic; no model.

What is refused here never reaches any other stage (no normalizing, no linking, no echo of the
text). Patterns live in ``lexicon/spam.yaml``. Thresholds live in ``config/limits.yaml``
(``gateway:``). The clock is injected, so tests do not sleep.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from citizengraph.gateway.config import GatewayConfig
from citizengraph.gateway.lexicon import read_yaml
from citizengraph.gateway.text import fold, is_word, scripts_in, tokenize
from citizengraph.gateway.types import SessionState

RATE_WINDOW_S = 60.0
_SPACED_LETTERS = re.compile(r"\b(?:[a-z0-9]\s+){2,}[a-z0-9]\b")
_WORD = re.compile(r"\w+")
_RUN4 = re.compile(r"(.)\1{3,}")
_KEYBOARD_ROWS = ("qwertyuiop", "asdfghjkl", "zxcvbnm")
_VOWELS = frozenset("aeiouy")


@dataclass(frozen=True)
class ScreenResult:
    """Outcome of the content checks: ``status`` is ``ok``, ``refuse`` or ``fallback``."""

    status: str
    reasons: list[str] = field(default_factory=list)
    long_input: bool = False


class SpamPatterns:
    """Compiled patterns and word lists from ``lexicon/spam.yaml``."""

    def __init__(self, directory=None):
        raw = read_yaml("spam.yaml", directory)
        self.injection = [re.compile(p) for ps in raw["injection"].values() for p in ps]
        self.code = {
            kind: [re.compile(p) for p in patterns] for kind, patterns in raw["code"].items()
        }
        mutation = raw["mutation"]
        self.strong = self._words(mutation["strong"].values())
        self.weak = self._words(mutation["weak"].values())
        self.targets = self._words([mutation["targets"]])
        self.window = int(mutation["window"])

    @staticmethod
    def _words(groups) -> frozenset[str]:
        out: set[str] = set()
        for group in groups:
            for item in group:
                out.update(t for t in tokenize(fold(str(item))) if is_word(t))
        return frozenset(out)


def digest(message: str) -> str:
    """Stable short digest of a message (case and spacing ignored). The text is never stored."""
    words = " ".join(t for t in tokenize(fold(message)) if is_word(t))
    return hashlib.sha256(words.encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------- rate and repeats


def check_rate(session: SessionState, now: float, cfg: GatewayConfig) -> tuple[str, float] | None:
    """``("rate_limit", retry_after_s)`` when the session sent too many messages in the last
    minute, else None. Does not record the message; call ``note_message`` for that."""
    window = [t for t in session.rate_window if now - t < RATE_WINDOW_S]
    session.rate_window = window
    if len(window) >= cfg.rate_limit_per_minute:
        blocking = window[len(window) - cfg.rate_limit_per_minute]
        return "rate_limit", max(0.0, round(RATE_WINDOW_S - (now - blocking), 3))
    return None


def check_repeat(session: SessionState, now: float, cfg: GatewayConfig, dig: str) -> bool:
    """True when this would be the ``repeat_limit``-th identical message inside the window."""
    same = sum(1 for t, d in session.recent_hashes if d == dig and now - t < cfg.repeat_window_s)
    return same + 1 >= cfg.repeat_limit


def note_message(session: SessionState, now: float, cfg: GatewayConfig, dig: str | None) -> None:
    """Record a message for the rate window (and its digest, for repeat detection)."""
    session.rate_window.append(now)
    del session.rate_window[: max(0, len(session.rate_window) - 4 * cfg.rate_limit_per_minute)]
    if dig is not None:
        session.recent_hashes.append((now, dig))
        keep = max(20, 4 * cfg.repeat_limit)
        del session.recent_hashes[: max(0, len(session.recent_hashes) - keep)]
    session.recent_hashes[:] = [
        (t, d) for t, d in session.recent_hashes if now - t < cfg.repeat_window_s
    ]


# ------------------------------------------------------------------------- suspicious text


def _despace(text: str) -> str:
    return _SPACED_LETTERS.sub(lambda m: re.sub(r"\s+", "", m.group()), text)


def detect_suspicious(message: str, patterns: SpamPatterns) -> list[str]:
    """Reasons the message looks like an instruction to the system, a mutation request or code.
    Empty means nothing suspicious was found. Reasons are codes, never pieces of the text."""
    folded = fold(message)
    reasons: list[str] = []
    for word in _WORD.findall(folded):
        scripts = scripts_in(word)
        if "LATIN" in scripts and len(scripts) > 1:
            reasons.append("mixed_script")
            break
    views = [folded]
    despaced = _despace(folded)
    if despaced != folded:
        views.append(despaced)
    if any(p.search(v) for p in patterns.injection for v in views):
        reasons.append("prompt_injection")
    for kind, compiled in patterns.code.items():
        if any(p.search(v) for p in compiled for v in views):
            reasons.append(f"{kind}_fragment")
    for v in views:
        if _mutation(tokenize(v), patterns):
            reasons.append("mutation_attempt")
            break
    return reasons


def _mutation(tokens: Sequence[str], patterns: SpamPatterns) -> bool:
    words = [t for t in tokens if is_word(t)]
    for i, word in enumerate(words):
        if word in patterns.strong:
            return True
        # "change of first name" and "update on my permit" use the word as a noun
        noun_use = words[i + 1 : i + 2] in (["of"], ["on"])
        if (
            word in patterns.weak
            and not noun_use
            and any(w in patterns.targets for w in words[i + 1 : i + 1 + patterns.window])
        ):
            return True
    return False


def screen_text(message: str, cfg: GatewayConfig, patterns: SpamPatterns) -> ScreenResult:
    """Length caps and suspicious-text check (rate and repeats are checked separately)."""
    if not message.strip():
        return ScreenResult("fallback", ["empty"])
    if len(message) > cfg.hard_max_chars:
        return ScreenResult("refuse", ["too_long"])
    reasons = detect_suspicious(message, patterns)
    if reasons:
        return ScreenResult("refuse", reasons)
    return ScreenResult("ok", [], long_input=len(message) > cfg.max_chars)


# ------------------------------------------------------------------------------ gibberish


def _is_mash(word: str, known: bool) -> bool:
    if len(word) < 4 or known or not word.isalpha():
        return False
    if not any(c in _VOWELS for c in word):
        return True
    for row in _KEYBOARD_ROWS:
        for seq in (row, row[::-1]):
            if any(word[i : i + 4] in seq for i in range(len(word) - 3)):
                return True
    return False


def gibberish_score(words: Sequence[tuple[str, bool]], message: str) -> float:
    """0 (ordinary text) to 1 (noise), from the share of unknown words, keyboard-mash words
    and character repetition. ``words`` are (word, known) pairs from the normalizer."""
    text = fold(message)
    squeezed = "".join(text.split())
    if not squeezed:
        return 0.0
    alpha = [(w, k) for w, k in words if w.isalpha()]
    rep_chars = sum(len(m.group()) for m in _RUN4.finditer(squeezed))
    rep_ratio = rep_chars / len(squeezed)
    if not alpha:
        return 1.0
    unknown = sum(1 for _, k in alpha if not k) / len(alpha)
    mash = sum(1 for w, k in alpha if _is_mash(w, k)) / len(alpha)
    base = 0.6 * unknown + 0.4 * max(mash, rep_ratio)
    return round(min(1.0, max(base, rep_ratio)), 4)
