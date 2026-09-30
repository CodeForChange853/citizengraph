"""API contract. The frontend is built against these models (see docs/api_contract.md)."""

from typing import Literal

from pydantic import BaseModel, Field

Lang = Literal["en", "fil"]
InfoStatus = Literal["confirmed", "pending_lgu"]
Group = Literal["business", "family", "health", "assistance"]


class ChatRequest(BaseModel):
    message: str = Field(..., max_length=2000)  # gateway enforces the real cap
    lang: Lang = "en"                           # reply language (UI toggle)
    session_id: str | None = None


class FeeItem(BaseModel):
    label: str
    amount_text: str


class StepItem(BaseModel):
    order: int
    text: str
    time_text: str | None = None
    external: bool = False


class Summary(BaseModel):
    """The "information scent" line. Null means the charter does not say (or is being verified)."""

    requirement_count: int | None = None
    fee_text: str | None = None
    time_text: str | None = None


class Related(BaseModel):
    """Something the citizen must get at another office first, then come back."""

    label: str
    office: str
    note: str


class Section(BaseModel):
    service_id: str
    service_name: str
    office: str
    info_status: InfoStatus = "confirmed"
    summary: Summary = Summary()
    checklist: list[str] = []
    fees: list[FeeItem] = []
    steps: list[StepItem] = []
    notes: list[str] = []
    related: list[Related] = []


class ServiceListItem(BaseModel):
    id: str
    name: str
    office: str
    group: Group
    summary: Summary = Summary()
    info_status: InfoStatus = "confirmed"


class ChatResponse(BaseModel):
    session_id: str
    language: Lang
    kind: Literal["answer", "clarify", "refusal", "status", "fallback"]
    text: str
    sections: list[Section] = []
    clarify_options: list[str] = []
    meta: dict = {}
