"""Noise injection for the synthetic citizen phrases (our own code, no model, no API).

``add_noise(text, level, rng)`` perturbs each eligible word with probability ``level`` percent,
using one of: keyboard-adjacent typos, dropped vowels, doubled letters, c/k swaps, ph/f swaps
and SMS spellings; then, with the same probability for the whole message, changes the casing.
Levels used for the dataset: 0 (clean), 10 and 30.

Words containing digits or ``$`` (ids, parameters, "2C") and very short words are left alone,
except that the SMS table also applies to short words such as "to" and "ng". Punctuation around
a word stays. Everything is driven by the ``random.Random`` you pass, so a seed reproduces the
text exactly; level 0 returns the text unchanged without drawing a random number.

The SMS table entries in ``SMS_FIL`` are Filipino and unverified: NEEDS-NATIVE-REVIEW.
"""

from __future__ import annotations

import random
import re
import string

NOISE_LEVELS = (0, 10, 30)

_ROWS = ("qwertyuiop", "asdfghjkl", "zxcvbnm")


def _neighbours() -> dict[str, frozenset[str]]:
    out: dict[str, set[str]] = {c: set() for c in string.ascii_lowercase}
    for r, row in enumerate(_ROWS):
        for i, ch in enumerate(row):
            for dr in (-1, 0, 1):
                rr = r + dr
                if not 0 <= rr < len(_ROWS):
                    continue
                for di in (-1, 0, 1):
                    j = i + di
                    if (dr, di) != (0, 0) and 0 <= j < len(_ROWS[rr]):
                        out[ch].add(_ROWS[rr][j])
    return {k: frozenset(v) for k, v in out.items()}


KEYBOARD_NEIGHBOURS = _neighbours()
VOWELS = "aeiou"

SMS_EN = {
    "you": "u",
    "your": "ur",
    "are": "r",
    "please": "pls",
    "thanks": "tnx",
    "thank": "tnk",
    "requirements": "reqs",
    "requirement": "req",
    "documents": "docs",
    "document": "doc",
    "registration": "reg",
    "information": "info",
    "how": "hw",
    "what": "wat",
    "where": "wer",
    "need": "nid",
    "before": "b4",
    "for": "4",
    "to": "2",
    "be": "b",
    "with": "w",
    "without": "w/o",
    "because": "coz",
    "and": "n",
    "tomorrow": "tom",
    "much": "mch",
    "long": "lng",
    "about": "abt",
    "office": "ofc",
}
# NEEDS-NATIVE-REVIEW: Filipino SMS spellings, unverified.
SMS_FIL = {
    "magkano": "mgkano",
    "ano": "anu",
    "saan": "san",
    "paano": "pano",
    "para": "pra",
    "kailangan": "kelangan",
    "pwede": "pwd",
    "hindi": "di",
    "kasi": "ksi",
    "naman": "nmn",
    "lang": "lng",
    "yung": "yng",
    "bayad": "byad",
    "nasaan": "nasan",
    "ba": "b",
    "po": "p",
}
SMS = {**SMS_EN, **SMS_FIL}

_WORD = re.compile(r"^(\W*)(.*?)(\W*)$", re.DOTALL)


def _letter_positions(word: str) -> list[int]:
    return [i for i, ch in enumerate(word) if ch.isalpha() and ch.lower() in KEYBOARD_NEIGHBOURS]


def _same_case(original: str, new: str) -> str:
    return new.upper() if original.isupper() else new


def keyboard_typo(word: str, rng: random.Random) -> str:
    """Replace one letter by a key next to it on a QWERTY keyboard."""
    spots = _letter_positions(word)
    if not spots:
        return word
    i = rng.choice(spots)
    near = sorted(KEYBOARD_NEIGHBOURS[word[i].lower()])
    return word[:i] + _same_case(word[i], rng.choice(near)) + word[i + 1 :]


def drop_vowel(word: str, rng: random.Random) -> str:
    """Drop one interior vowel, or (one time in three) all of them, as in text messages."""
    spots = [i for i in range(1, len(word)) if word[i].lower() in VOWELS]
    if not spots or len(word) < 3:
        return word
    if len(spots) > 1 and rng.random() < 1 / 3:
        return "".join(ch for i, ch in enumerate(word) if i not in spots)
    i = rng.choice(spots)
    return word[:i] + word[i + 1 :]


def double_letter(word: str, rng: random.Random) -> str:
    """Type one letter twice."""
    spots = [i for i, ch in enumerate(word) if ch.isalpha()]
    if not spots:
        return word
    i = rng.choice(spots)
    return word[: i + 1] + word[i:]


def swap_ck(word: str, rng: random.Random) -> str:
    """c -> k (not in "ch") or k -> c, at one random place."""
    spots = [
        i
        for i, ch in enumerate(word)
        if (ch.lower() == "c" and word[i + 1 : i + 2].lower() != "h") or ch.lower() == "k"
    ]
    if not spots:
        return word
    i = rng.choice(spots)
    flipped = "k" if word[i].lower() == "c" else "c"
    return word[:i] + _same_case(word[i], flipped) + word[i + 1 :]


def swap_ph_f(word: str, rng: random.Random) -> str:
    """ph -> f, or f -> ph, at one random place."""
    lower = word.lower()
    spots = [(i, 2) for i in range(len(word) - 1) if lower[i : i + 2] == "ph"]
    spots += [(i, 1) for i, ch in enumerate(lower) if ch == "f"]
    if not spots:
        return word
    i, width = rng.choice(spots)
    new = "f" if width == 2 else "ph"
    return word[:i] + _same_case(word[i], new) + word[i + width :]


def sms_spelling(word: str, rng: random.Random) -> str:
    """Text-message spelling from the table; a word that is not in it stays as it is."""
    return SMS.get(word.lower(), word)


_OPERATIONS = (keyboard_typo, drop_vowel, double_letter, swap_ck, swap_ph_f, sms_spelling)


def _eligible(token: str, core: str) -> bool:
    """Plain alphabetic words only: no ids, parameters, numbers or paths."""
    return core.isalpha() and not any(ch.isdigit() or ch in "$@/_" for ch in token)


def _perturb(core: str, rng: random.Random) -> str:
    """Apply one randomly chosen operation that applies to the word (each one that applies
    changes it, so the word always comes out different)."""
    options = [op for op in _OPERATIONS if op(core, random.Random(0)) != core]
    return rng.choice(options)(core, rng) if options else core


def _recase(text: str, rng: random.Random) -> str:
    style = rng.choice(("lower", "upper", "title", "random"))
    if style == "lower":
        return text.lower()
    if style == "upper":
        return text.upper()
    if style == "title":
        return text.title()
    return " ".join(w.upper() if rng.random() < 0.3 else w.lower() for w in text.split(" "))


def add_noise(
    text: str, level: float, rng: random.Random, protect: frozenset[str] = frozenset()
) -> str:
    """Return ``text`` with noise at ``level`` percent (0 = unchanged).

    ``protect`` holds lowercase words that are never changed: the entity words (service, office,
    agency, document and variant names) that the gateway's lexicon would repair before the model
    sees them (casing noise still applies to the whole message; the dataset lower-cases it again
    when it cleans the phrase like the gateway).
    """
    if isinstance(level, bool) or not isinstance(level, (int, float)) or not 0 <= level <= 100:
        raise ValueError(f"noise level must be a percentage between 0 and 100, got {level!r}")
    if level == 0:
        return text
    p = level / 100
    out: list[str] = []
    for token in re.split(r"(\s+)", text):
        if not token or token.isspace():
            out.append(token)
            continue
        lead, core, trail = _WORD.match(token).groups()  # type: ignore[union-attr]
        if _eligible(token, core) and rng.random() < p and core.lower() not in protect:
            core = _perturb(core, rng)
        out.append(lead + core + trail)
    noisy = "".join(out)
    if rng.random() < p:
        noisy = _recase(noisy, rng)
    return noisy
