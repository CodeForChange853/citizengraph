"""Targets: what the gateway linked for one sub-request, and the query parameters they become.

The redesigned Core 1 (prompt v2) receives the LINKED TARGETS, the language and the cleaned phrase;
it is not told the intent or the variants. A target is one of:

* ``service:<Service.id>``: the gateway's ``SubRequest.service_id`` (two of them for a comparison);
* ``office:<Office.id>``: ``SubRequest.office_id`` (a service-linked request carries its office);
* ``agency:<Agency.id>``: an Agency node id (the slug of the agency name);
* ``document:<words>``: lowercase words matched inside requirement text (``$doc``).

The gateway of session 4 links services and offices only. Linking an agency, a document, or a
second service in one request is a front-end addition this design needs; see
``docs/training_notes.md`` ("What the gateway must add").

Parameter names (``templates.PARAMETERS``): the first service is ``$sid``, the second ``$sid2``,
the office ``$oid``, the agency ``$aid``, the document ``$doc``. ``$variant_ids`` comes from the
variants line of the model's completion, not from a target.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from citizengraph.core1.slots import Language
from citizengraph.core1.templates import (
    CORE1_INTENTS,
    TEMPLATES,
    MissingTarget,
    NotCore1Intent,
    Query,
)

TARGET_KINDS = ("service", "office", "agency", "document")
_ID = re.compile(r"^[a-z][a-z0-9_-]{0,99}$")
_DOCUMENT = re.compile(r"^[a-z0-9][a-z0-9 ]{0,58}[a-z0-9]$|^[a-z0-9]$")
MAX_SERVICES = 2

TargetKind = Literal["service", "office", "agency", "document"]


class Target(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: TargetKind
    id: str

    @model_validator(mode="after")
    def _id_fits_the_kind(self) -> Target:
        pattern = _DOCUMENT if self.kind == "document" else _ID
        if not pattern.match(self.id):
            raise ValueError(f"bad {self.kind} target {self.id!r}")
        return self

    def __str__(self) -> str:
        return f"{self.kind}:{self.id}"


def _sorted_targets(targets: Iterable[Target]) -> tuple[Target, ...]:
    order = {k: i for i, k in enumerate(TARGET_KINDS)}
    return tuple(sorted(targets, key=lambda t: order[t.kind]))  # stable: services keep order


def render_targets(targets: Iterable[Target]) -> str:
    """``service:a, service:b, office:x`` (services, office, agency, document), or ``none``."""
    parts = [str(t) for t in _sorted_targets(targets)]
    return ", ".join(parts) if parts else "none"


def parse_targets(text: str) -> tuple[Target, ...]:
    text = text.strip()
    if text in ("", "none"):
        return ()
    out = []
    for part in text.split(", "):
        kind, _, ident = part.partition(":")
        out.append(Target(kind=kind, id=ident))  # type: ignore[arg-type]
    return tuple(out)


class Request(BaseModel):
    """What prompt v2 is built from: linked targets, the language and the cleaned phrase."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    targets: tuple[Target, ...] = ()
    phrase: str
    language: Language

    @field_validator("targets", mode="before")
    @classmethod
    def _as_tuple(cls, value: Any) -> Any:
        return tuple(value) if isinstance(value, (list, tuple)) else value

    @model_validator(mode="after")
    def _shape(self) -> Request:
        if not self.phrase.strip():
            raise ValueError("phrase must not be blank")
        counts = {k: sum(1 for t in self.targets if t.kind == k) for k in TARGET_KINDS}
        if counts["service"] > MAX_SERVICES:
            raise ValueError("at most two service targets")
        for kind in ("office", "agency", "document"):
            if counts[kind] > 1:
                raise ValueError(f"at most one {kind} target")
        services = [t.id for t in self.targets if t.kind == "service"]
        if len(set(services)) != len(services):
            raise ValueError("the two services must differ")
        object.__setattr__(self, "targets", _sorted_targets(self.targets))
        return self

    def of_kind(self, kind: str) -> list[str]:
        return [t.id for t in self.targets if t.kind == kind]

    @classmethod
    def from_sub_request(cls, sub: Any) -> Request:
        """From the gateway's ``SubRequest`` (duck-typed: service_id, office_id, phrase, language).
        The intent and variants the gateway found are deliberately not passed on."""
        targets = []
        if getattr(sub, "service_id", None):
            targets.append(Target(kind="service", id=sub.service_id))
        if getattr(sub, "office_id", None):
            targets.append(Target(kind="office", id=sub.office_id))
        return cls(targets=targets, phrase=sub.phrase, language=sub.language)


def params_for(
    request: Request, needs: Sequence[str], variant_ids: Sequence[str] = ()
) -> dict[str, object]:
    """The parameters of a query that needs ``needs`` (plus ``variant_ids`` when given)."""
    services = request.of_kind("service")
    available = {
        "sid": services[0] if services else None,
        "sid2": services[1] if len(services) > 1 else None,
        "oid": next(iter(request.of_kind("office")), None),
        "aid": next(iter(request.of_kind("agency")), None),
        "doc": next(iter(request.of_kind("document")), None),
    }
    params: dict[str, object] = {}
    for name in needs:
        if available.get(name) is None:
            raise MissingTarget(f"the query needs ${name}, which no target supplies")
        params[name] = available[name]
    if variant_ids:
        params["variant_ids"] = list(variant_ids)
    return params


def build_request_query(
    request: Request, intent: str, shape: str, variant_ids: Sequence[str] = ()
) -> Query:
    """The canonical query for (intent, shape) with its parameters: the filtered template when
    variants are given and the shape can be filtered, else the plain one."""
    if intent not in CORE1_INTENTS:
        raise NotCore1Intent(f"intent {intent!r} is not answered by a Core 1 query")
    plain = TEMPLATES.get((intent, shape, False))
    if plain is None:
        raise ValueError(f"no {shape!r} template for intent {intent!r}")
    filtered = TEMPLATES.get((intent, shape, True))
    template = filtered if (filtered is not None and variant_ids) else plain
    ids = variant_ids if template.filtered else ()
    return Query(template.cypher, params_for(request, template.needs, ids))


__all__ = [
    "MissingTarget",
    "Request",
    "Target",
    "build_request_query",
    "params_for",
    "parse_targets",
    "render_targets",
]
