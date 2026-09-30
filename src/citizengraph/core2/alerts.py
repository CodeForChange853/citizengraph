"""Alert text. Templates only: an alert is never model output.

Slots are filled from graph rows (service, office, step number, role title, agency name) and from
exact tool results (elapsed time, allowed time, working days). Staff names never appear: the graph
only holds roles. Statutory limits are always described as *configured and unverified*, never as
law; the citizen-facing texts do not mention the statute at all.

Every Filipino string is a DRAFT and is marked ``# NEEDS-NATIVE-REVIEW``. ``FILIPINO_STRINGS``
lists them all so docs/core2_notes.md can be checked against the code (a test does that).
"""

from __future__ import annotations

from dataclasses import dataclass, field

PROBLEM_EN = {
    "missing_entered_at": "no start time recorded",
    "missing_completed_at": "no finish time recorded",
    "completed_before_entered": "finish time is earlier than start time",
}
PROBLEM_FIL = {  # NEEDS-NATIVE-REVIEW
    "missing_entered_at": "walang naitalang oras ng simula",  # NEEDS-NATIVE-REVIEW
    "missing_completed_at": "walang naitalang oras ng pagtatapos",  # NEEDS-NATIVE-REVIEW
    "completed_before_entered": "mas maaga ang oras ng pagtatapos kaysa sa simula",  # NEEDS-NATIVE-REVIEW
}


def _plural(n: float, one: str, many: str) -> str:
    return f"{n:g} {one if n == 1 else many}"


def minutes_en(m: float) -> str:
    if m < 60:
        return _plural(round(m, 1), "minute", "minutes")
    h, rest = divmod(round(m), 60)
    return _plural(h, "hour", "hours") + (f" {_plural(rest, 'minute', 'minutes')}" if rest else "")


def minutes_fil(m: float) -> str:  # NEEDS-NATIVE-REVIEW
    if m < 60:
        return f"{round(m, 1):g} minuto"
    h, rest = divmod(round(m), 60)
    return f"{h:g} oras" + (f" {rest:g} minuto" if rest else "")


def days_en(d: float, kind: str | None) -> str:
    label = {"working_days": "working ", "calendar_days": "calendar "}.get(kind or "", "")
    return _plural(round(d, 2), f"{label}day", f"{label}days")


def days_fil(d: float, kind: str | None) -> str:  # NEEDS-NATIVE-REVIEW
    suffix = {"working_days": " ng trabaho", "calendar_days": " (kalendaryo)"}.get(kind or "", "")
    return f"{round(d, 2):g} araw{suffix}"


@dataclass(frozen=True)
class AlertContext:
    ref: str
    service_name: str
    office_name: str
    step_order: int | None = None
    steps_total: int | None = None
    external_agency: str | None = None
    allowed_en: str | None = None
    allowed_fil: str | None = None
    elapsed_en: str | None = None
    elapsed_fil: str | None = None
    role_title: str | None = None
    role_absent: bool = False
    statutory_days: int | None = None
    statutory_cap: int | None = None
    issues: list[tuple[int | None, str]] = field(default_factory=list)


def _step(ctx: AlertContext, lang: str) -> str:
    if ctx.step_order is None or ctx.steps_total is None:
        return ""
    return (
        f" at step {ctx.step_order} of {ctx.steps_total}"
        if lang == "en"
        else f" sa hakbang {ctx.step_order} ng {ctx.steps_total}"  # NEEDS-NATIVE-REVIEW
    )


def _citizen_delay_en(c: AlertContext) -> str:
    if c.allowed_en and c.elapsed_en:
        return (
            f"Your application {c.ref} for {c.service_name}{_step(c, 'en')} is taking longer than "
            f"the {c.office_name} charter time ({c.elapsed_en} so far; charter time for this step: "
            f"{c.allowed_en}). We are sorry for the delay. Please ask the office if you have "
            "questions."
        )
    return (
        f"Your application {c.ref} for {c.service_name} has been in process for "
        f"{c.statutory_days} working days, which is longer than expected. We are sorry for the "
        "delay. Please ask the office if you have questions."
    )


def _citizen_delay_fil(c: AlertContext) -> str:  # NEEDS-NATIVE-REVIEW
    if c.allowed_fil and c.elapsed_fil:
        return (
            f"Ang aplikasyon ninyo na {c.ref} para sa {c.service_name}{_step(c, 'fil')} ay mas "
            f"matagal kaysa sa itinakdang oras ng {c.office_name} ({c.elapsed_fil} na; itinakdang "
            f"oras sa hakbang na ito: {c.allowed_fil}). Paumanhin po sa pagkaantala. "
            "Magtanong po sa opisina kung may katanungan."
        )  # NEEDS-NATIVE-REVIEW
    return (
        f"Ang aplikasyon ninyo na {c.ref} para sa {c.service_name} ay {c.statutory_days} araw ng "
        "trabaho nang pinoproseso, na mas matagal kaysa inaasahan. Paumanhin po sa pagkaantala. "
        "Magtanong po sa opisina kung may katanungan."
    )  # NEEDS-NATIVE-REVIEW


def _escalation_en(c: AlertContext) -> str:
    parts = [
        (
            f"ESCALATION for the head of {c.office_name}: application {c.ref} ({c.service_name}) "
            f"is past its time{_step(c, 'en')}."
        )
    ]
    if c.allowed_en and c.elapsed_en:
        parts.append(f"Elapsed {c.elapsed_en}; charter step time {c.allowed_en}.")
    if c.statutory_days is not None and c.statutory_cap is not None:
        parts.append(
            f"Working days since receipt: {c.statutory_days}; configured limit: "
            f"{c.statutory_cap} (this limit is NOT verified against RA 11032)."
        )
    if c.role_title:
        absent = " and is marked absent today" if c.role_absent else ""
        parts.append(f"Responsible role: {c.role_title}{absent}.")
    return " ".join(parts)


def _escalation_fil(c: AlertContext) -> str:  # NEEDS-NATIVE-REVIEW
    parts = [
        (
            f"PAG-ULAT SA PINUNO ng {c.office_name}: ang aplikasyon {c.ref} ({c.service_name}) "
            f"ay lampas na sa oras{_step(c, 'fil')}."
        )
    ]
    if c.allowed_fil and c.elapsed_fil:
        parts.append(f"Lumipas: {c.elapsed_fil}; itinakdang oras: {c.allowed_fil}.")
    if c.statutory_days is not None and c.statutory_cap is not None:
        parts.append(
            f"Araw ng trabaho mula pagtanggap: {c.statutory_days}; itinakdang limitasyon: "
            f"{c.statutory_cap} (HINDI pa napapatunayan sa RA 11032 ang limitasyong ito)."
        )
    if c.role_title:
        absent = " at absent ngayon" if c.role_absent else ""
        parts.append(f"Responsableng tungkulin: {c.role_title}{absent}.")
    return " ".join(parts)  # NEEDS-NATIVE-REVIEW


def _external_en(c: AlertContext) -> str:
    return (
        f"Your application {c.ref} for {c.service_name} is waiting at another agency "
        f"({c.external_agency}) for longer than the usual time ({c.elapsed_en} so far; usual "
        f"time: {c.allowed_en}). This step is outside the processing of {c.office_name}. Please "
        f"follow up with {c.external_agency}."
    )


def _external_fil(c: AlertContext) -> str:  # NEEDS-NATIVE-REVIEW
    return (
        f"Ang aplikasyon ninyo na {c.ref} para sa {c.service_name} ay naghihintay sa ibang "
        f"ahensya ({c.external_agency}) nang mas matagal kaysa karaniwan ({c.elapsed_fil} na; "
        f"karaniwang oras: {c.allowed_fil}). Hindi ito kasama sa pagproseso ng {c.office_name}. "
        f"Makipag-ugnayan po sa {c.external_agency}."
    )  # NEEDS-NATIVE-REVIEW


def _missing_en(c: AlertContext) -> str:
    items = "; ".join(
        f"step {n if n is not None else '?'}: {PROBLEM_EN.get(p, p)}" for n, p in c.issues
    )
    return (
        f"DATA FLAG for {c.office_name}: application {c.ref} ({c.service_name}) has timestamp "
        f"problems ({items}). Time cannot be measured for these steps and nothing has been "
        "assumed. Please correct the record."
    )


def _missing_fil(c: AlertContext) -> str:  # NEEDS-NATIVE-REVIEW
    items = "; ".join(
        f"hakbang {n if n is not None else '?'}: {PROBLEM_FIL.get(p, p)}" for n, p in c.issues
    )
    return (
        f"BABALA SA DATOS para sa {c.office_name}: ang aplikasyon {c.ref} ({c.service_name}) ay "
        f"may problema sa oras ({items}). Hindi masusukat ang oras sa mga hakbang na ito at "
        "walang ipinagpalagay. Pakiayos po ang talaan."
    )  # NEEDS-NATIVE-REVIEW


_EN = {
    "citizen_delay_notice": _citizen_delay_en,
    "department_head_escalation": _escalation_en,
    "external_wait_notice": _external_en,
    "missing_data_flag": _missing_en,
}
_FIL = {  # NEEDS-NATIVE-REVIEW
    "citizen_delay_notice": _citizen_delay_fil,
    "department_head_escalation": _escalation_fil,
    "external_wait_notice": _external_fil,
    "missing_data_flag": _missing_fil,
}


def render_alert(kind: str, ctx: AlertContext) -> tuple[str, str]:
    """(English text, Filipino draft text) for one alert kind."""
    return _EN[kind](ctx), _FIL[kind](ctx)


# Every Filipino template fragment above, for the native-speaker review list.
FILIPINO_STRINGS: tuple[str, ...] = (  # NEEDS-NATIVE-REVIEW
    *PROBLEM_FIL.values(),
    "minuto",
    "oras",
    "araw",
    "ng trabaho",
    "(kalendaryo)",
    "sa hakbang {n} ng {total}",
    "Ang aplikasyon ninyo na {ref} para sa {service}",
    "ay mas matagal kaysa sa itinakdang oras ng {office}",
    "itinakdang oras sa hakbang na ito",
    "Paumanhin po sa pagkaantala.",
    "Magtanong po sa opisina kung may katanungan.",
    "nang pinoproseso, na mas matagal kaysa inaasahan",
    "PAG-ULAT SA PINUNO ng {office}",
    "lampas na sa oras",
    "Lumipas:",
    "itinakdang oras:",
    "Araw ng trabaho mula pagtanggap:",
    "itinakdang limitasyon:",
    "HINDI pa napapatunayan sa RA 11032 ang limitasyong ito",
    "Responsableng tungkulin:",
    "at absent ngayon",
    "naghihintay sa ibang ahensya",
    "nang mas matagal kaysa karaniwan",
    "karaniwang oras:",
    "Hindi ito kasama sa pagproseso ng {office}.",
    "Makipag-ugnayan po sa {agency}.",
    "BABALA SA DATOS para sa {office}",
    "may problema sa oras",
    "Hindi masusukat ang oras sa mga hakbang na ito at walang ipinagpalagay.",
    "Pakiayos po ang talaan.",
)
