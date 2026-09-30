"""The gateway's word lists and the lookup tables built from them.

Data lives next to this file (``sms.yaml``, ``vocab.yaml``, ``intents.yaml``, ``variants.yaml``,
``spam.yaml``) plus the alias table ``graph/seed/aliases.yaml``; nothing here is model output.
``Lexicon`` turns them into the structures the normalizer, linker and intent detector use.
"""

from __future__ import annotations

from collections.abc import Hashable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from citizengraph.gateway.aliases import AliasTable
from citizengraph.gateway.text import apply_table, fold, is_word, tokenize

LEXICON_DIR = Path(__file__).resolve().parent


def read_yaml(name: str, directory: Path | None = None) -> Any:
    return yaml.safe_load(((directory or LEXICON_DIR) / name).read_text(encoding="utf-8"))


def _words(items: Iterable[str]) -> list[str]:
    out: list[str] = []
    for item in items:
        if not isinstance(item, str):  # YAML reads bare yes / no / on / off as booleans
            raise TypeError(f"lexicon word {item!r} must be a quoted string")
        out.extend(t for t in tokenize(fold(str(item))) if is_word(t))
    return out


@dataclass(frozen=True)
class Hit:
    """A phrase found in a token list: tokens[start:end] matched ``labels``."""

    start: int
    end: int
    labels: tuple[Hashable, ...]


class PhraseTable:
    """Multi-word phrases -> labels. ``scan`` returns non-overlapping hits, longest first."""

    def __init__(self) -> None:
        self._entries: dict[tuple[str, ...], list[Hashable]] = {}
        self._maxlen = 1

    def add(self, phrase: tuple[str, ...], label: Hashable) -> None:
        if not phrase:
            return
        labels = self._entries.setdefault(phrase, [])
        if label not in labels:
            labels.append(label)
        self._maxlen = max(self._maxlen, len(phrase))

    def __len__(self) -> int:
        return len(self._entries)

    def scan(self, tokens: list[str]) -> list[Hit]:
        hits: list[Hit] = []
        i, n = 0, len(tokens)
        while i < n:
            if not is_word(tokens[i]):
                i += 1
                continue
            for size in range(min(self._maxlen, n - i), 0, -1):
                window = tokens[i : i + size]
                if any(not is_word(t) for t in window):
                    continue
                labels = self._entries.get(tuple(window))
                if labels:
                    hits.append(Hit(i, i + size, tuple(labels)))
                    i += size
                    break
            else:
                i += 1
        return hits


class Lexicon:
    def __init__(self, table: AliasTable, directory: Path | None = None):
        self.table = table
        self.sms: dict[str, tuple[str, ...]] = {}
        for section in read_yaml("sms.yaml", directory).values():
            for key, value in section.items():
                self.sms[str(key)] = tuple(_words([value]))
        vocab = read_yaml("vocab.yaml", directory)
        self.stopwords = frozenset(_words(vocab["stopwords"]))
        self.conjunctions = frozenset(_words(vocab["conjunctions"]))
        self.greetings = frozenset(_words(vocab["greetings"]))
        self.confirm_yes = frozenset(_words(vocab["confirm_yes"]))
        self.confirm_no = frozenset(_words(vocab["confirm_no"]))
        self.other_services = PhraseTable()
        for text in vocab["other_services"]:
            self.other_services.add(self.phrase(str(text)), "other")

        en_words: set[str] = set(_words(vocab["en_function"])) | set(_words(vocab["en_common"]))
        fil_words: set[str] = set(_words(vocab["fil_function"])) | set(
            _words(vocab["fil_common"])
        )
        alias_en: set[str] = set()
        alias_fil: set[str] = set()
        self.alias_tokens: set[str] = set()
        for alias in table.aliases:
            words = set(self.phrase(alias.text))
            self.alias_tokens |= words
            (alias_en if alias.lang == "en" else alias_fil).update(words)
        for entry in table.services.values():
            for cue in entry.cues_en:
                alias_en.update(self.phrase(cue))
            for cue in entry.cues_fil:
                alias_fil.update(self.phrase(cue))

        self.intents = PhraseTable()
        for key, langs in read_yaml("intents.yaml", directory).items():
            intent, weak = (key[: -len("_weak")], True) if key.endswith("_weak") else (key, False)
            for lang, phrases in langs.items():
                for text in phrases:
                    words = self.phrase(text)
                    self.intents.add(words, (intent, weak))
                    (en_words if lang == "en" else fil_words).update(words)

        self.variant_cues = PhraseTable()
        self.unsupported_cues = PhraseTable()
        variants_raw = read_yaml("variants.yaml", directory)
        for section, cue_table in (
            ("cues", self.variant_cues),
            ("unsupported", self.unsupported_cues),
        ):
            for dimension, values in variants_raw[section].items():
                for value, langs in values.items():
                    for lang, phrases in langs.items():
                        for text in phrases or []:
                            words = self.phrase(text)
                            cue_table.add(words, (str(dimension), str(value)))
                            (en_words if lang == "en" else fil_words).update(words)

        # a word is evidence of a language only when the other language does not also use it
        en_all = en_words | alias_en
        fil_all = fil_words | (alias_fil - alias_en)
        self.lang_of: dict[str, str] = {}
        for word in en_all | fil_all:
            in_en, in_fil = word in en_all, word in fil_all
            if in_en != in_fil:
                self.lang_of[word] = "en" if in_en else "fil"

        en_words |= {t for p in vocab["other_services"] for t in self.phrase(str(p))}
        self.known: frozenset[str] = frozenset(
            en_words
            | fil_words
            | self.alias_tokens
            | self.stopwords
            | self.conjunctions
            | self.greetings
            | self.confirm_yes
            | self.confirm_no
            | {w for values in self.sms.values() for w in values}
        )
        self.fuzzy_words: list[str] = sorted(w for w in self.known if len(w) >= 5 and w.isalpha())

    def phrase(self, text: str) -> tuple[str, ...]:
        """A phrase from the data files as normalized words (same steps as citizen text)."""
        tokens = apply_table(tokenize(fold(text)), self.sms)
        return tuple(t for t in tokens if is_word(t))
