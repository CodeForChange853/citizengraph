"""Render an ``AgentResult`` as the API's ``kind = "status"`` response (docs/api_contract.md).

Templates only. The status words come from the agent's final answer, the service, office, agency
and role names from graph rows; the citizen text never contains a staff name, a raw timestamp or
the statutory cap (which is unverified and must not be shown as law). The module is not wired into
the API: it only builds a ``ChatResponse``.

Every Filipino string is a DRAFT marked ``# NEEDS-NATIVE-REVIEW`` and listed in
``FILIPINO_STRINGS`` (also in docs/core2_notes.md).
"""

from __future__ import annotations

from citizengraph.api.schemas import ChatResponse, Section
from citizengraph.core2.runtime import AgentResult
from citizengraph.core2.sla import workflow_state
from citizengraph.core2.tools import Toolbox

# status -> (English, Filipino draft). {ref} = reference code, {agency} = external agency.
_LINE: dict[str, tuple[str, str]] = {
    "on_track": (
        "Application {ref}: on track. It is being processed within the expected time.",
        "Aplikasyon {ref}: maayos ang takbo. Pinoproseso ito sa loob ng inaasahang oras.",  # NEEDS-NATIVE-REVIEW
    ),
    "minor_delay": (
        "Application {ref}: a little over the usual time for this step, still being processed.",
        "Aplikasyon {ref}: bahagyang lampas sa karaniwang oras sa hakbang na ito, pinoproseso pa rin.",  # NEEDS-NATIVE-REVIEW
    ),
    "delayed": (
        "Application {ref}: taking longer than the charter time for this step. We are sorry.",
        "Aplikasyon {ref}: mas matagal kaysa sa itinakdang oras sa hakbang na ito. Paumanhin po.",  # NEEDS-NATIVE-REVIEW
    ),
    "overdue_statutory": (
        "Application {ref}: in process for longer than expected. We are sorry for the delay.",
        "Aplikasyon {ref}: mas matagal na kaysa inaasahan ang pagproseso. Paumanhin po sa pagkaantala.",  # NEEDS-NATIVE-REVIEW
    ),
    "external_waiting": (
        (
            "Application {ref}: waiting at another agency ({agency}). This step is outside our "
            "office's processing."
        ),
        (  # NEEDS-NATIVE-REVIEW
            "Aplikasyon {ref}: naghihintay sa ibang ahensya ({agency}). Hindi ito kasama sa "
            "pagproseso ng aming opisina."
        ),
    ),
    "waiting_posting": (
        "Application {ref}: in the required posting period. This is a waiting period, not a delay.",
        "Aplikasyon {ref}: nasa kinakailangang panahon ng pagpapaskil. Panahon ito ng paghihintay, hindi pagkaantala.",  # NEEDS-NATIVE-REVIEW
    ),
    "paused_by_suspension": (
        "Application {ref}: paused because of a declared work suspension.",
        "Aplikasyon {ref}: naka-pause dahil sa idineklarang suspensyon ng trabaho.",  # NEEDS-NATIVE-REVIEW
    ),
    "cannot_determine": (
        (
            "Application {ref}: we cannot tell from our records how long this should take. "
            "Please check with the office."
        ),
        (  # NEEDS-NATIVE-REVIEW
            "Aplikasyon {ref}: hindi namin matiyak mula sa aming talaan kung gaano katagal ito. "
            "Magtanong po sa opisina."
        ),
    ),
    "completed": (
        "Application {ref}: all steps are complete.",
        "Aplikasyon {ref}: kumpleto na ang lahat ng hakbang.",  # NEEDS-NATIVE-REVIEW
    ),
}
_TEXT = {
    "status": (
        "Here is the status of your application.",
        "Narito ang katayuan ng inyong aplikasyon.",  # NEEDS-NATIVE-REVIEW
    ),
    "none": (
        "We could not find an application with that reference.",
        "Wala kaming nakitang aplikasyon na may ganoong reference.",  # NEEDS-NATIVE-REVIEW
    ),
    "fallback": (
        "We could not check this safely. Please check with the office.",
        "Hindi namin ito nasuri nang ligtas. Magtanong po sa opisina.",  # NEEDS-NATIVE-REVIEW
    ),
}

FILIPINO_STRINGS: tuple[str, ...] = (  # NEEDS-NATIVE-REVIEW
    *(fil for _, fil in _LINE.values()),
    *(fil for _, fil in _TEXT.values()),
)


def to_chat_response(
    result: AgentResult, toolbox: Toolbox, language: str = "en", session_id: str | None = None
) -> ChatResponse:
    """The citizen-facing status answer for a status or office task."""
    if result.task.kind not in ("status", "office_sweep"):
        raise ValueError("only status and office tasks have a citizen-facing answer")
    lang = 0 if language == "en" else 1
    sid = session_id or "core2-simulated"
    meta = {"core2": True, "stopped_reason": result.stopped_reason, "steps": result.steps}
    if result.is_fallback:
        return ChatResponse(
            session_id=sid, language=language, kind="fallback", text=_TEXT["fallback"][lang],
            meta=meta,
        )  # fmt: skip
    apps = result.final.get("applications", [])
    if not apps:
        return ChatResponse(
            session_id=sid, language=language, kind="status", text=_TEXT["none"][lang], meta=meta
        )  # fmt: skip
    sections: list[Section] = []
    for item in apps:
        app = toolbox.store.get(item["app_id"])
        if app is None:
            continue
        service = toolbox.graph.service(app.service_id)
        state = workflow_state(app, toolbox.graph)
        agency = (state.current.external_agency if state.current else None) or ""
        line = _LINE[item["status"]][lang].format(ref=app.ref, agency=agency)
        sections.append(
            Section(
                service_id=service.id,
                service_name=service.name,
                office=toolbox.graph.office_of(service.id).name,
                notes=[line],
            )
        )
    return ChatResponse(
        session_id=sid, language=language, kind="status", text=_TEXT["status"][lang],
        sections=sections, meta=meta,
    )  # fmt: skip
