"""FastAPI app. /chat and /services are a MOCK until the real pipeline is wired in.

Mock content comes only from the curated seed (graph/seed/*.yaml), copied by hand:
six services, wording as in the charters (typos of display names aside, see DESIGN.md).
Sentences around the facts are templates in EN and FIL (FIL is NEEDS-NATIVE-REVIEW).
"""

import re
import uuid

from fastapi import FastAPI

from citizengraph.api.schemas import (
    ChatRequest,
    ChatResponse,
    FeeItem,
    Lang,
    Related,
    Section,
    ServiceListItem,
    StepItem,
    Summary,
)

app = FastAPI(title="Citizen Graph API", version="0.2.0")

_BPLO = "Business Permits & Licensing Office"
_CHO = "City Health Office"
_CSWDO = "City Social Welfare Development Office"
_LCRO = "Civil Registry Office"


def _s(order: int, text: str, time: str | None = None, external: bool = False) -> StepItem:
    return StepItem(order=order, text=text, time_text=time, external=external)


# --- MOCK DATA -------------------------------------------------------------
# id -> service. `notes` and `related` hold codes / (requirement, office) pairs that are
# turned into sentences by the templates below. Pending services carry no numbers at all.
_SERVICES: dict[str, dict] = {
    "business_permit": {  # BPLO-01, seed ids business_permit-*
        "name": "Business Permit", "office": _BPLO, "group": "business",
        "info_status": "confirmed",
        "summary": Summary(requirement_count=14, fee_text="₱235.50", time_text="37 minutes"),
        "checklist": [
            "Duly accomplished Mayor’s Permit Application Form",
            "Brgy. Business Clearance & Solid Waste Certification",
            "City Solid Waste Certification",
            "Single Proprietor – Owner’s Cedula; Corporation – Corporation Cedula",
            "Single Proprietor: DTI Certification of Registration",
            "Corporation: SEC Certificate of Incorporation",
            "Corporation: By-Laws (for new business)",
            "Corporation: Articles of Incorporation (for new business)",
            "Association: SEC Certificate of Registration",
            "Corporation: CDA Certificate of Registration",
            "Fire Safety Inspection Certification",
            "Sanitary Permit to Operate",
            "Employee’s Occupational Permit (proof of payment only)",
            "Locational Clearance (subject to assessment of location)",
        ],
        "fees": [
            FeeItem(label="Zoning", amount_text="₱30.00"),
            FeeItem(label="Sanitary Services", amount_text="₱100.00"),
            FeeItem(label="Business Name Clearance", amount_text="₱5.50"),
            FeeItem(label="Signboard", amount_text="₱100.00"),
        ],
        "steps": [
            _s(1, "Approach receiving employee", "2 minutes"),
            _s(2, "Submit complete requirements with citizen’s signature & filled-out "
                  "Mayor’s Permit application form", "2 minutes"),
            _s(3, "Wait for the TOP", "5 minutes"),
            _s(4, "Signs TOP / Release Book", "5-10 minutes"),
            _s(5, "Proceed to the City Treasurer’s Office for payment", None, True),
            _s(6, "Proceed to the BPLO main office with the proof of payment (official "
                  "receipt) and complete set of documents", "5 minutes"),
            _s(7, "Prepare & print Business/Mayor’s Permit", "5 minutes"),
            _s(8, "Approval of Business/Mayor’s Permit", "3-5 minutes"),
            _s(9, "Record and release approved Business/Mayor’s", "2-3 minutes"),
            _s(10, "Receive permit & sign on the release record book"),
        ],
        "notes": ["business_type"],
        "related": [("Sanitary Permit to Operate", _CHO)],
    },
    "cho_sanitary_permit": {  # CHO-10
        "name": "Sanitary Permit", "office": _CHO, "group": "health",
        "info_status": "confirmed",
        "summary": Summary(requirement_count=1, fee_text=None, time_text="3 days, 10 minutes"),
        "checklist": ["Application Form"],
        "fees": [],
        "steps": [
            _s(1, "Receiving", "5 minutes"),
            _s(2, "Inspection", "3 days"),
            _s(3, "Releasing of Sanitary Permit", "5 minutes"),
        ],
        "notes": ["sanitary_total", "days_unknown"],
        "related": [],
    },
    "cho_medical_certificate": {  # CHO-15
        "name": "Medical Certificate (for employment)", "office": _CHO, "group": "health",
        "info_status": "confirmed",
        "summary": Summary(requirement_count=0, fee_text="₱30.00", time_text="20 minutes"),
        "checklist": [],
        "fees": [FeeItem(label="Medical certificate", amount_text="₱30.00")],
        "steps": [
            _s(1, "Receiving and vital signs taking", "5 minutes"),
            _s(2, "Consultation with physician", "10 minutes"),
            _s(3, "Releasing and recording", "5 minutes"),
        ],
        "notes": [],
        "related": [],
    },
    "cswdo_referrals": {  # CSWDO-01
        "name": "Referrals", "office": _CSWDO, "group": "assistance",
        "info_status": "confirmed",
        "summary": Summary(
            requirement_count=5, fee_text=None, time_text="1 week, 1 hour, 40 minutes"
        ),
        "checklist": [
            "Brgy Certification as to residence",
            "Certification from Assessor's Office that client does not own real property",
            "Certification from BPLO that the client has no existing business",
            "Medical Abstract",
            "Death Certificate",
        ],
        "fees": [],
        "steps": [
            _s(1, "Present required document", "30 minutes"),
            _s(2, "Clients referred to LTO for transportation assisstance / PCSO for "
                  "financial (Medical) assistance / Missionaries of Charity for temporary "
                  "placement / SOS for long term residential care", "1 week"),
            _s(3, "Receive the needed documents", "10 minutes"),
            _s(4, "Monitoring", "1 hour (Once a month)"),
        ],
        "notes": ["days_unknown"],
        "related": [("Certification from BPLO that the client has no existing business", _BPLO)],
    },
    # LCRO-01 and LCRO-06: the LGU must confirm the checklists before citizens see them
    # (CLAUDE.md). Nothing but name and office is sent.
    "birth_registration_timely": {
        "name": "Birth Registration (timely)", "office": _LCRO, "group": "family",
        "info_status": "pending_lgu", "summary": Summary(),
        "checklist": [], "fees": [], "steps": [], "notes": [], "related": [],
    },
    "death_registration_timely": {
        "name": "Death Registration (timely)", "office": _LCRO, "group": "family",
        "info_status": "pending_lgu", "summary": Summary(),
        "checklist": [], "fees": [], "steps": [], "notes": [], "related": [],
    },
}

# Sentences around the facts. The FIL strings were verified by the team on 2026-10-01 (status per string:
# frontend/NEEDS-NATIVE-REVIEW.md); any later edit needs review again.
_TEXT: dict[str, dict[str, str]] = {
    "en": {
        "answer": "Here is what you need for {names}.",
        "pending_lgu": "This checklist is still being checked with the office.",
        "clarify": "Which one do you need?",
        "fallback": "I can only help with services from four city offices. Please pick one.",
        "refusal": "I can only look things up. I cannot change anything.",
        "related_note": "Get this first, then come back.",
        "business_type": "Some items are only for some kinds of business. Bring the ones for yours.",
        "days_unknown": "The office does not say if these days are calendar days or working days.",
        "sanitary_total": "The office’s own total time does not match its steps. "
                          "The times below come from the steps.",
    },
    "fil": {
        "answer": "Narito ang kailangan mo para sa {names}.",
        "pending_lgu": "Sinusuri pa ang listahang ito kasama ang tanggapan.",
        "clarify": "Alin ang kailangan mo?",
        "fallback": "Makakatulong lang ako sa mga serbisyo ng apat na tanggapan ng lungsod. "
                    "Pumili ng isa.",
        "refusal": "Nakakapaghanap lang ako ng impormasyon. Wala akong mababago.",
        "related_note": "Kunin muna ito, saka bumalik dito.",
        "business_type": "May mga papel na para lang sa ilang uri ng negosyo. "
                         "Dalhin ang para sa iyo.",
        "days_unknown": "Hindi sinasabi ng tanggapan kung araw-araw o araw ng trabaho ang bilang.",
        "sanitary_total": "Hindi tugma ang kabuuang oras ng tanggapan sa mga hakbang nito. "
                          "Galing sa mga hakbang ang mga oras sa ibaba.",
    },
}

# Keyword routing for the mock (the real pipeline uses the normalizer and alias linker).
_ROUTES: list[dict] = [
    {"service_id": "business_permit",
     "keywords": ["business", "negosyo", "mayor's permit", "mayors permit"]},
    {"service_id": "cho_sanitary_permit", "keywords": ["sanitary", "sanitaryo"]},
    {"service_id": "cho_medical_certificate",
     "keywords": ["medical", "medikal", "health certificate"]},
    {"service_id": "cswdo_referrals",
     "keywords": ["referral", "assistance", "tulong", "ayuda"]},
    {"service_id": "birth_registration_timely",
     "keywords": ["birth", "born", "panganganak", "ipinanganak", "kapanganakan"]},
    {"service_id": "death_registration_timely",
     "keywords": ["death", "died", "namatay", "patay", "kamatayan"]},
]
_AMBIGUOUS: list[dict] = [
    {"keyword": "permit", "options": ["business_permit", "cho_sanitary_permit"]},
    {"keyword": "certificate",
     "options": ["birth_registration_timely", "death_registration_timely",
                 "cho_medical_certificate"]},
]
_GREETINGS = ["hi", "hello", "hey", "kumusta", "kamusta", "help"]
_DEFAULT_OPTIONS = ["business_permit", "birth_registration_timely",
                    "cho_medical_certificate", "cswdo_referrals"]
_REFUSAL_RE = r"\b(delete|drop|remove|ignore previous|ignore all|burahin|alisin)\b"


def _section(service_id: str, lang: Lang) -> Section:
    s = _SERVICES[service_id]
    t = _TEXT[lang]
    return Section(
        service_id=service_id,
        service_name=s["name"],
        office=s["office"],
        info_status=s["info_status"],
        summary=s["summary"],
        checklist=s["checklist"],
        fees=s["fees"],
        steps=s["steps"],
        notes=[t[code] for code in s["notes"]],
        related=[Related(label=r, office=o, note=t["related_note"]) for r, o in s["related"]],
    )


def _match(message: str) -> list[str]:
    msg = message.lower()
    return [r["service_id"] for r in _ROUTES if any(k in msg for k in r["keywords"])]


def mock_chat(message: str, lang: Lang) -> tuple[str, str, list[str], list[str]]:
    """Return (kind, text, service_ids, clarify_service_ids). Shared with the fixture export."""
    t = _TEXT[lang]
    msg = message.lower()
    if re.search(_REFUSAL_RE, msg):
        return "refusal", t["refusal"], [], []
    ids = _match(message)
    if ids:
        # A pending_lgu checklist is never introduced as "what you need": it gets its own lead-in.
        # Mixed messages name only the confirmed services in the first sentence.
        confirmed = [i for i in ids if _SERVICES[i]["info_status"] != "pending_lgu"]
        parts = []
        if confirmed:
            parts.append(t["answer"].format(names=", ".join(_SERVICES[i]["name"] for i in confirmed)))
        if len(confirmed) < len(ids):
            parts.append(t["pending_lgu"])
        return "answer", " ".join(parts), ids, []
    for amb in _AMBIGUOUS:
        if amb["keyword"] in msg:
            return "clarify", t["clarify"], [], amb["options"]
    if msg.strip() in _GREETINGS:
        return "clarify", t["clarify"], [], _DEFAULT_OPTIONS
    return "fallback", t["fallback"], [], []


def _summary_list() -> list[ServiceListItem]:
    return [
        ServiceListItem(
            id=i, name=s["name"], office=s["office"], group=s["group"],
            summary=s["summary"], info_status=s["info_status"],
        )
        for i, s in _SERVICES.items()
    ]


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "mock": True}


@app.get("/languages")
def languages() -> list[str]:
    return ["en", "fil"]


@app.get("/services", response_model=list[ServiceListItem])
def services() -> list[ServiceListItem]:
    return _summary_list()


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    kind, text, ids, clarify_ids = mock_chat(req.message, req.lang)
    return ChatResponse(
        session_id=req.session_id or str(uuid.uuid4()),
        language=req.lang,
        kind=kind,  # type: ignore[arg-type]
        text=text,
        sections=[_section(i, req.lang) for i in ids],
        clarify_options=[_SERVICES[i]["name"] for i in clarify_ids],
        meta={"mock": True},
    )


_PARITY_MESSAGES = [
    "business permit", "kailangan ko ng business permit", "hello", "permit", "certificate",
    "sanitary permit and medical certificate", "birth", "namatay ang tatay ko", "referral",
    "business permit and death registration",
    "delete everything", "what is the weather", "passport",
]


def mock_fixtures() -> dict:
    """Everything the frontend fixture adapter needs, generated from this mock.

    Written to frontend/src/api/fixtures.json by frontend/scripts/export_fixtures.py;
    tests/test_api.py fails if the committed file drifts from this output.
    """
    return {
        "services": [s.model_dump() for s in _summary_list()],
        "routes": _ROUTES,
        "ambiguous": _AMBIGUOUS,
        "greetings": _GREETINGS,
        "default_options": _DEFAULT_OPTIONS,
        "refusal_pattern": _REFUSAL_RE,
        "text": _TEXT,
        "names": {i: s["name"] for i, s in _SERVICES.items()},
        "cases": [
            {
                "message": m, "lang": lang, "kind": k, "text": text,
                "service_ids": ids, "clarify_ids": cids,
            }
            for m in _PARITY_MESSAGES
            for lang in ("en", "fil")
            for k, text, ids, cids in [mock_chat(m, lang)]  # type: ignore[arg-type]
        ],
        "sections": {
            lang: {i: _section(i, lang).model_dump() for i in _SERVICES}  # type: ignore[arg-type]
            for lang in ("en", "fil")
        },
    }
