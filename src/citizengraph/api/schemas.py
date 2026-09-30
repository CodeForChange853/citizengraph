"""API contract. The frontend is built against these models (see docs/api_contract.md)."""

from typing import Literal

from pydantic import BaseModel, Field

Lang = Literal["en", "fil"]


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


class Section(BaseModel):
    service_id: str
    service_name: str
    office: str
    checklist: list[str] = []
    fees: list[FeeItem] = []
    steps: list[StepItem] = []
    notes: list[str] = []


class ChatResponse(BaseModel):
    session_id: str
    language: Lang
    kind: Literal["answer", "clarify", "refusal", "status", "fallback"]
    text: str
    sections: list[Section] = []
    clarify_options: list[str] = []
    meta: dict = {}
