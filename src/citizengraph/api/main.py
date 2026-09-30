"""FastAPI app. /chat is a MOCK until the real pipeline is wired in."""

import uuid

from fastapi import FastAPI

from citizengraph.api.schemas import ChatRequest, ChatResponse, FeeItem, Section, StepItem

app = FastAPI(title="Citizen Graph API", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "mock": True}


@app.get("/languages")
def languages() -> list[str]:
    return ["en", "fil"]


# --- MOCK DATA (from BPLO-CC.xlsx, Business Permit; replace with graph rows) ---
_BUSINESS_PERMIT = Section(
    service_id="bplo-business-permit",
    service_name="Business Permit",
    office="Business Permits & Licensing Office",
    checklist=[
        "Duly accomplished Mayor's Permit Application Form",
        "Barangay Business Clearance & Solid Waste Certification",
        "City Solid Waste Certification",
        "Fire Safety Inspection Certification",
        "Sanitary Permit to Operate",
        "Locational Clearance (subject to assessment of location)",
    ],
    fees=[
        FeeItem(label="Zoning", amount_text="P30.00"),
        FeeItem(label="Sanitary Services", amount_text="P100.00"),
    ],
    steps=[
        StepItem(order=1, text="Approach the receiving employee", time_text="2 minutes"),
        StepItem(order=2, text="Submit complete requirements", time_text="2 minutes"),
    ],
    notes=["MOCK DATA: partial list for UI development only."],
)

_TEXT = {
    "en": {
        "answer": "Here is what you need for a Business Permit (mock data).",
        "clarify": "Which service do you need? (mock)",
    },
    # NEEDS-NATIVE-REVIEW
    "fil": {
        "answer": "Narito ang kailangan para sa Business Permit (mock na datos).",
        "clarify": "Anong serbisyo ang kailangan mo? (mock)",
    },
}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    sid = req.session_id or str(uuid.uuid4())
    msg = req.message.lower()
    if any(k in msg for k in ("business", "negosyo", "permit")):
        return ChatResponse(
            session_id=sid,
            language=req.lang,
            kind="answer",
            text=_TEXT[req.lang]["answer"],
            sections=[_BUSINESS_PERMIT],
            meta={"mock": True},
        )
    return ChatResponse(
        session_id=sid,
        language=req.lang,
        kind="clarify",
        text=_TEXT[req.lang]["clarify"],
        clarify_options=["Business Permit", "Birth Certificate", "Marriage License"],
        meta={"mock": True},
    )
