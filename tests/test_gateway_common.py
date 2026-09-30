"""Helpers shared by the gateway tests (no tests here). Every message below is invented for the
tests; nothing comes from eval/heldout/."""

from __future__ import annotations

import random

from citizengraph.gateway import GatewayResult, SessionState, default_gateway

STEP_S = 10.0  # seconds between messages, so the per-minute limit never gets in the way


def run(*messages: str, session: SessionState | None = None, start: float = 10_000.0):
    """Send the messages one after another in one session; return every result."""
    session = session or SessionState(session_id="test")
    gateway = default_gateway()
    return [
        gateway.process(m, session, now=start + i * STEP_S) for i, m in enumerate(messages)
    ]


def ask(message: str) -> GatewayResult:
    """One message in a fresh session."""
    return run(message)[0]


def triples(result: GatewayResult) -> list[tuple[str | None, str, dict[str, str]]]:
    return [(s.service_id, s.intent, s.variants) for s in result.sub_requests]


def option_ids(result: GatewayResult) -> list[str]:
    return [o.id for o in result.clarify_options]


def noise(n_chars: int, seed: int = 7) -> str:
    """Pronounceable nonsense words (not words of any lexicon here), ``n_chars`` long."""
    rng = random.Random(seed)
    consonants, vowels = "bcdfghjklmnpqrstvwxz", "aeiou"
    words: list[str] = []
    while sum(len(w) + 1 for w in words) < n_chars:
        words.append(
            "".join(
                rng.choice(consonants if i % 2 == 0 else vowels)
                for i in range(rng.randint(4, 9))
            )
        )
    return " ".join(words)[:n_chars]
