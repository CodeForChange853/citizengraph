"""Text primitives shared by the normalizer, the lexicon and the spam screen.

Everything here is pure and deterministic. ``fold`` makes text comparable (NFKC, lowercase,
accents and invisible characters removed, apostrophes dropped so "mayor's" is "mayors");
``tokenize`` turns folded text into ASCII words and a handful of separator tokens that the
splitter needs ("," ";" "&" "+" "/" "." "?" "!"). Letters outside ASCII become separators, so the
cleaned text can never carry unusual characters to later stages.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping

SEPARATORS = frozenset(",;&+/.?!")

_APOSTROPHES = str.maketrans({"‘": "'", "’": "'", "´": "'", "`": "'"})
_DOTTED = re.compile(r"\b(?:[a-z]\.){2,}")
_TOKEN = re.compile(r"[a-z0-9]+|[,;&+/.?!]")
_RUN3 = re.compile(r"([a-z])\1{2,}")


def fold(text: str) -> str:
    """NFKC, lowercase, strip accents and invisible characters, drop apostrophes."""
    text = unicodedata.normalize("NFKC", text).translate(_APOSTROPHES)
    out: list[str] = []
    for ch in text:
        if ch == "'":
            continue
        if ch in "\t\r\n\v\f":
            out.append(" ")
        elif unicodedata.category(ch)[0] == "C":
            continue  # control, format (zero-width), private use, unassigned
        else:
            out.append(ch)
    text = unicodedata.normalize("NFD", "".join(out).lower())
    return unicodedata.normalize("NFC", "".join(c for c in text if unicodedata.category(c) != "Mn"))


def tokenize(folded: str) -> list[str]:
    """Words (ASCII letters and digits) and separator tokens; runs of 3+ letters collapse to 1."""
    folded = _DOTTED.sub(lambda m: m.group().replace(".", ""), folded).replace("-", " ")
    return [t if t in SEPARATORS else _RUN3.sub(r"\1", t) for t in _TOKEN.findall(folded)]


def apply_table(tokens: Iterable[str], table: Mapping[str, tuple[str, ...]]) -> list[str]:
    """Replace whole tokens using ``table`` (a value may be several words)."""
    out: list[str] = []
    for tok in tokens:
        out.extend(table.get(tok, (tok,)))
    return out


def is_word(token: str) -> bool:
    return token not in SEPARATORS


def scripts_in(word: str) -> set[str]:
    """Unicode script names (first word of the character name) of the letters in ``word``."""
    names: set[str] = set()
    for ch in word:
        if ch.isalpha():
            try:
                names.add(unicodedata.name(ch).split()[0])
            except ValueError:
                names.add("UNKNOWN")
    return names
