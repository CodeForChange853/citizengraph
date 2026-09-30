"""Curated seed data: strict models, a cross-validating loader and an in-memory graph.

Read-only. Writing the seed into Neo4j is the job of ``graph/load.py`` (an offline admin script);
nothing under ``src/citizengraph/`` may import it or start a write transaction.
"""

from citizengraph.graph.loader import (
    DEFAULT_SEED_DIR,
    SeedError,
    SeedIssue,
    load_seed,
    parse_seed,
    validate_seed,
)
from citizengraph.graph.memory import InMemoryGraph, UnknownServiceError
from citizengraph.graph.models import Seed

__all__ = [
    "DEFAULT_SEED_DIR",
    "InMemoryGraph",
    "Seed",
    "SeedError",
    "SeedIssue",
    "UnknownServiceError",
    "load_seed",
    "parse_seed",
    "validate_seed",
]
