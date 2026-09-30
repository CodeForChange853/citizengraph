"""Slots: one sub-request after the deterministic front end (linker, intent, splitter).

The field names are the vocabulary every session shares: ``service_id``, ``intent``,
``variants`` (dimension -> value, using the dimensions and values in ``graph/seed/variants.yaml``),
``phrase`` (the cleaned citizen text) and ``language``. Core 1 turns one ``Slots`` into one
read-only Cypher query (``templates.py`` is the canonical form, ``prompt.py`` the model input).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

INTENTS = (
    "requirements",
    "fees",
    "steps",
    "processing_time",
    "where_to_secure",
    "who_may_avail",
    "office",
    "status",
)
LANGUAGES = ("en", "fil", "mixed")

Intent = Literal[
    "requirements",
    "fees",
    "steps",
    "processing_time",
    "where_to_secure",
    "who_may_avail",
    "office",
    "status",
]
Language = Literal["en", "fil", "mixed"]

_SERVICE_ID = r"^[a-z][a-z0-9_]*$"
_DIMENSION = re.compile(r"^[a-z][a-z0-9_]*$")
_VALUE = re.compile(r"^[A-Za-z0-9_]+$")  # no ':' (it separates dimension and value in an id)

_VARIANTS_PATH = Path(__file__).resolve().parents[3] / "graph" / "seed" / "variants.yaml"


class Slots(BaseModel):
    """Everything Core 1 needs to build a query for one (service, intent) request."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    service_id: Annotated[str, Field(pattern=_SERVICE_ID)]
    intent: Intent
    variants: dict[str, str] = Field(default_factory=dict)
    phrase: str
    language: Language

    @field_validator("variants")
    @classmethod
    def _variants_are_plain(cls, variants: dict[str, str]) -> dict[str, str]:
        for dimension, value in variants.items():
            if not _DIMENSION.match(dimension):
                raise ValueError(f"bad variant dimension {dimension!r}")
            if not _VALUE.match(value):
                raise ValueError(f"bad variant value {value!r} for {dimension!r}")
        return variants

    @field_validator("phrase")
    @classmethod
    def _phrase_is_not_blank(cls, phrase: str) -> str:
        if not phrase.strip():
            raise ValueError("phrase must not be blank")
        return phrase

    @property
    def variant_ids(self) -> list[str]:
        """Variant node ids (``dimension:value``), sorted: the ``$variant_ids`` query parameter."""
        return sorted(f"{d}:{v}" for d, v in self.variants.items())


@lru_cache(maxsize=4)
def _read_known(path: Path) -> dict[str, frozenset[str]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    known: dict[str, set[str]] = {}
    for record in data["variants"]:
        known.setdefault(record["dimension"], set()).add(str(record["value"]))
    return {d: frozenset(v) for d, v in known.items()}


def known_variants(path: Path | None = None) -> dict[str, frozenset[str]]:
    """Dimension -> values, read from the curated seed (``graph/seed/variants.yaml``)."""
    return dict(_read_known(path or _VARIANTS_PATH))


def check_variants(
    variants: Mapping[str, str], known: Mapping[str, frozenset[str] | set[str]] | None = None
) -> list[str]:
    """Problems with a variant selection against the seed vocabulary (empty list: all fine)."""
    vocabulary = known if known is not None else known_variants()
    problems = []
    for dimension, value in variants.items():
        if dimension not in vocabulary:
            problems.append(f"unknown variant dimension {dimension!r}")
        elif value not in vocabulary[dimension]:
            problems.append(f"unknown value {value!r} for variant dimension {dimension!r}")
    return problems
