"""Data types of the gateway: what goes in (session) and what comes out (result).

The model never sees raw citizen text. The only citizen-derived text that leaves the gateway is
``SubRequest.phrase``: lowercase ASCII words, no punctuation, at most ``max_phrase_chars`` long.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

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
Status = Literal[
    "ok", "clarify", "echo_confirm", "refuse", "fallback", "rate_limited", "out_of_scope"
]
ClarifyKind = Literal["service", "intent", "confirm"]

STATUSES = ("ok", "clarify", "echo_confirm", "refuse", "fallback", "rate_limited", "out_of_scope")


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SubRequest(_Model):
    """One (service, intent) question, ready for Core 1 or Core 2.

    ``service_id`` is None only for ``status`` questions that name no (single) service; Core 2
    works from the application reference instead.
    """

    service_id: str | None
    intent: Intent
    variants: dict[str, str] = Field(default_factory=dict)
    phrase: str
    language: Language
    office_id: str | None = None


class ClarifyOption(_Model):
    """A tappable answer. ``id`` is what the UI sends back as the next message."""

    id: str
    kind: ClarifyKind
    label: str  # service name from the graph, the intent name, or "yes" / "no"
    service_id: str | None = None
    intent: Intent | None = None
    in_graph: bool | None = None  # services only: False means "not available yet"
    office_id: str | None = None


class EchoItem(_Model):
    service_id: str | None
    service_name: str | None
    intent: Intent
    variants: dict[str, str] = Field(default_factory=dict)


class Echo(_Model):
    """What the gateway understood, to be confirmed by the citizen (structured, plus a plain
    English draft line; the composer owns the final wording in both languages)."""

    items: list[EchoItem]
    text: str


class Unavailable(_Model):
    """A service the citizen asked about that the graph cannot answer yet."""

    service_id: str
    name: str | None
    office_id: str
    office_name: str | None
    reason: Literal["not_in_graph", "withheld"]


class GatewayResult(_Model):
    status: Status
    sub_requests: list[SubRequest] = Field(default_factory=list)
    clarify_options: list[ClarifyOption] = Field(default_factory=list)
    clarify_kind: ClarifyKind | None = None
    echo: Echo | None = None
    unavailable: list[Unavailable] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    language: Language | None = None
    retry_after_s: float | None = None
    timings_ms: dict[str, float] = Field(default_factory=dict)


# ------------------------------------------------------------------------------ session state


class Draft(BaseModel):
    """A sub-request that is not complete yet: it waits for a service or an intent."""

    service_id: str | None = None
    candidates: list[str] = Field(default_factory=list)  # service ids when ambiguous
    intent: str | None = None
    cues: list[tuple[str, str]] = Field(default_factory=list)  # (dimension, value) cue hits
    unsupported: list[tuple[str, str]] = Field(default_factory=list)
    phrase: str = ""
    language: Language = "en"
    office_id: str | None = None
    low_confidence: bool = False


class Pending(BaseModel):
    """The one question the gateway is waiting on (clarify or echo)."""

    kind: ClarifyKind
    drafts: list[Draft] = Field(default_factory=list)
    options: list[ClarifyOption] = Field(default_factory=list)
    needs_echo: bool = False
    sub_requests: list[SubRequest] = Field(default_factory=list)  # kind == "confirm"
    reasons: list[str] = Field(default_factory=list)


@dataclass
class SessionState:
    """Everything the gateway remembers about one citizen session (inference is stateless; this
    lives in code). Hold one per session and pass it to every ``process`` call."""

    session_id: str = ""
    pending: Pending | None = None
    resolved_service_id: str | None = None
    resolved_variants: dict[str, str] = field(default_factory=dict)
    last_intent: str | None = None
    # (timestamp, digest) of recent messages; digests only, never the text
    recent_hashes: list[tuple[float, str]] = field(default_factory=list)
    # timestamps of recent messages, for the per-minute rate limit
    rate_window: list[float] = field(default_factory=list)
