"""Ids for nodes the seed does not list as records (Agency and Role), derived from their names."""

from __future__ import annotations

import re

_APOSTROPHES = re.compile(r"[’'`]")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def clean_name(name: str) -> str:
    """Collapse whitespace; the wording itself is never changed."""
    return " ".join(name.split())


def slug(name: str) -> str:
    """Lowercase ASCII slug: ``City Treasurer’s Office`` -> ``city-treasurers-office``."""
    return _NON_ALNUM.sub("-", _APOSTROPHES.sub("", clean_name(name)).lower()).strip("-")
