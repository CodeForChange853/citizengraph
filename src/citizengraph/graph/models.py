"""Strict models for the curated seed files in ``graph/seed/`` (schema: docs/specs.md section 1).

Every record says where it came from (``source``: file, sheet, row range of its service block)
and carries a ``review_status``. Nothing here is charter data; it only checks the shape.

Staff names live in ``Step.internal_person_raw`` only. The field is excluded from every dump, so
serializing a model, building loader rows or answering from the in-memory graph cannot leak it.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ReviewStatus = Literal["needs_review", "reviewed"]
Unit = Literal["minute", "hour", "day", "week"]
DayType = Literal["working", "calendar", "unknown"]
Classification = Literal["SIMPLE", "COMPLEX"]

_SNAKE = r"^[a-z][a-z0-9_]*$"

# Numbers from the charter must be real numbers, never numeric-looking text.
Number = Annotated[float, Field(strict=True)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceRef(_Strict):
    """A service block in a source spreadsheet: file, sheet and first/last row."""

    file: str = Field(min_length=1)
    sheet: str = Field(min_length=1)
    rows: list[int]

    @field_validator("rows")
    @classmethod
    def _ordered_pair(cls, rows: list[int]) -> list[int]:
        if len(rows) != 2 or rows[0] < 1 or rows[0] > rows[1]:
            raise ValueError("rows must be [first_row, last_row] with 1 <= first <= last")
        return rows


class ReviewFlag(_Strict):
    """Something a human must look at, or a fact the charter left blank."""

    code: str = Field(pattern=_SNAKE)
    message: str = Field(min_length=1)


class _Record(_Strict):
    id: str = Field(min_length=1)
    review_status: ReviewStatus
    flags: list[ReviewFlag] = Field(default_factory=list)


class Office(_Record):
    name: str = Field(min_length=1)
    sources: Annotated[list[SourceRef], Field(min_length=1)]


class Variant(_Record):
    """One value of a condition dimension, e.g. ``taxpayer:company``."""

    dimension: str = Field(pattern=_SNAKE)
    value: str = Field(min_length=1)
    sources: Annotated[list[SourceRef], Field(min_length=1)]

    @model_validator(mode="after")
    def _id_is_dimension_and_value(self) -> Variant:
        if self.id != f"{self.dimension}:{self.value}":
            raise ValueError(f"id must be '{self.dimension}:{self.value}', got {self.id!r}")
        return self


HeldBackField = Literal["requirements", "who_may_avail"]


class HeldBack(_Strict):
    """A citizen-visible part of a service that is not shown until the LGU confirms it.

    ``requirements``: the whole checklist is untrusted or incomplete (an empty or partial list
    would read as "nothing else is needed"). ``who_may_avail``: that text is suspect.
    """

    field: HeldBackField
    reason: str = Field(min_length=1)

    @field_validator("reason")
    @classmethod
    def _reason_says_something(cls, reason: str) -> str:
        if not reason.strip():
            raise ValueError("reason must not be blank")
        return reason


class Service(_Record):
    office_id: str
    charter_ref: str = Field(min_length=1)  # e.g. BPLO-01, the draft id of this block
    name: str = Field(min_length=1)
    classification: Classification
    transaction_type: str | None = None
    who_may_avail: str | None = None
    total_fee_text: str | None = None
    total_time_text: str | None = None
    description: str | None = None
    source: SourceRef
    total_source_row: int | None = None
    held_back: list[HeldBack] = Field(default_factory=list)  # data marker; never stored

    @model_validator(mode="after")
    def _held_back_fields_are_distinct(self) -> Service:
        fields = [h.field for h in self.held_back]
        if len(fields) != len(set(fields)):
            raise ValueError("held_back lists a field more than once")
        if "who_may_avail" in fields and self.who_may_avail is None:
            raise ValueError("held_back who_may_avail needs a who_may_avail text to hold")
        return self


class _Conditional(_Record):
    """Shared rules for requirements and fees that only apply in some cases.

    ``condition_text`` keeps the charter's own wording. ``variant_ids`` are the structured links
    (same dimension: any of; different dimensions: all of). ``condition_structured`` says whether
    those links capture the whole condition (True) or not (False); null means no condition.
    """

    condition_text: str | None = None
    condition_structured: bool | None = None
    variant_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _condition_is_consistent(self) -> _Conditional:
        if self.condition_text is None:
            if self.variant_ids or self.condition_structured is not None:
                raise ValueError("variant links need the charter's condition wording")
            return self
        if self.condition_structured is None:
            raise ValueError("condition_structured must be true or false when there is a condition")
        if self.condition_structured and not self.variant_ids:
            raise ValueError("a condition without variant links cannot be structured")
        return self


class Requirement(_Conditional):
    service_id: str
    key: str | None = None  # the sheet's own number or letter, when it has one
    text: str = Field(min_length=1)
    group: bool = False
    parent_id: str | None = None
    min_required: int | None = None
    secured_at: str | None = None  # Agency name exactly as the charter says
    source: SourceRef
    source_row: int = Field(ge=1)
    suspect: bool = Field(default=False, strict=True)  # data marker; never stored
    suspect_reason: str | None = None  # required when suspect

    @model_validator(mode="after")
    def _suspect_needs_a_reason(self) -> Requirement:
        if self.suspect and not (self.suspect_reason or "").strip():
            raise ValueError("a suspect requirement needs a suspect_reason")
        if not self.suspect and self.suspect_reason is not None:
            raise ValueError("suspect_reason is only for a suspect requirement")
        return self

    @model_validator(mode="after")
    def _min_required_is_for_groups(self) -> Requirement:
        if self.min_required is not None:
            if not self.group:
                raise ValueError("min_required belongs on a group")
            if self.min_required < 1:
                raise ValueError("min_required must be at least 1")
        return self


class Duration(_Strict):
    """A parsed processing time: (value_min, value_max, unit) plus the raw text."""

    status: Literal["stated", "not_stated", "unparsed"]
    value_min: Number | None = None
    value_max: Number | None = None
    unit: Unit | None = None
    minutes_min: Number | None = None  # derived (day = 1,440 min); for benchmarking only
    minutes_max: Number | None = None
    day_type: DayType = "unknown"
    raw: str | None = None

    @model_validator(mode="after")
    def _shape_matches_status(self) -> Duration:
        numbers = (self.value_min, self.value_max, self.unit, self.minutes_min, self.minutes_max)
        if self.status == "stated":
            if None in (self.value_min, self.value_max, self.unit):
                raise ValueError("a stated duration needs value_min, value_max and unit")
            assert self.value_min is not None and self.value_max is not None
            if self.value_min < 0 or self.value_min > self.value_max:
                raise ValueError("duration range must satisfy 0 <= value_min <= value_max")
        elif any(n is not None for n in numbers):
            raise ValueError(f"a {self.status} duration must not carry numbers")
        return self


class Step(_Record):
    service_id: str
    order: int = Field(ge=1, strict=True)
    label: str | None = None  # the sheet's step number, e.g. "1.1." or "F.2."
    citizen_step_group: int | None = None
    citizen_action: str | None = None
    agency_action: str | None = None
    external_agency: str | None = None  # step belongs to another agency
    duration: Duration
    role: str | None = None  # only when the charter itself gives a role title
    internal_person_raw: str | None = Field(default=None, exclude=True)  # names: never shown
    next_id: str | None = None
    duration_shared_from: str | None = None  # time cell merged with an earlier step
    source: SourceRef
    source_row: int = Field(ge=1)


class Fee(_Conditional):
    service_id: str
    step_id: str | None = None
    label: str | None = None
    amount_min: Annotated[float, Field(ge=0, strict=True)]
    amount_max: Annotated[float, Field(ge=0, strict=True)]
    unit: str | None = None
    note: str | None = None
    source: SourceRef
    source_row: int = Field(ge=1)

    @model_validator(mode="after")
    def _range_is_ordered(self) -> Fee:
        if self.amount_min > self.amount_max:
            raise ValueError("amount_min must not exceed amount_max")
        return self


LinkKind = Literal["requirement_satisfied_by", "agency_is_office"]


class Link(_Record):
    """A cross-office (or cross-service) link. Every link starts as a suggestion.

    ``requirement_satisfied_by``: the requirement is obtained by using another charter service
    (needs ``requirement_id`` and ``service_id``). ``agency_is_office``: the Agency named exactly
    ``agency`` is one of the scoped offices (needs ``agency`` and ``office_id``);
    ``requirement_id`` may name the requirement that made the link worth suggesting.
    """

    kind: LinkKind
    requirement_id: str | None = None
    agency: str | None = None
    service_id: str | None = None
    office_id: str | None = None
    sources: Annotated[list[SourceRef], Field(min_length=1)]

    @model_validator(mode="after")
    def _fields_match_the_kind(self) -> Link:
        if self.kind == "requirement_satisfied_by":
            if self.requirement_id is None or self.service_id is None:
                raise ValueError("requirement_satisfied_by needs requirement_id and service_id")
            if self.agency is not None or self.office_id is not None:
                raise ValueError("requirement_satisfied_by takes no agency or office_id")
        else:
            if self.agency is None or self.office_id is None:
                raise ValueError("agency_is_office needs agency and office_id")
            if self.service_id is not None:
                raise ValueError("agency_is_office takes no service_id")
        return self


class Seed(_Strict):
    offices: list[Office]
    services: list[Service]
    requirements: list[Requirement]
    steps: list[Step]
    fees: list[Fee]
    variants: list[Variant]
    links: list[Link] = Field(default_factory=list)
