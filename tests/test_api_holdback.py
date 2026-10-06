"""The mock API must not show as fact what the default loader holds back (graph/holdback.py).

What is held back is derived here from the seed (``hold_back(load_seed())``), never from ids or
wording written in this file, so the test follows the data: when the LGU confirms a record and
its marker is removed from ``graph/seed``, the mock may show it again.

The mock is read through ``mock_fixtures()``, the same export the frontend fixtures come from.
Every string of a confirmed section is searched (summary, checklist, fees, steps, notes, related).

Not checked here: that the confirmed values equal the seed, and the loader's other default rule,
that a cross-office link is written only once it is reviewed (the mock's ``related`` routes).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

from citizengraph.api.main import mock_fixtures
from citizengraph.graph.holdback import hold_back
from citizengraph.graph.loader import load_seed

SEED = load_seed()
HELD = hold_back(SEED)
MOCK = mock_fixtures()
MOCK_STATUS = {row["id"]: row["info_status"] for row in MOCK["services"]}

_FOLD = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-"})


def norm(text: str) -> str:
    """Compare wording, not typography: the mock was copied by hand."""
    return re.sub(r"\s+", " ", text.translate(_FOLD)).strip().casefold()


def strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def held_texts() -> dict[str, str]:
    """Normalized held-back wording -> where it comes from (for the failure message).

    Requirement rows that are not group headings, and held-back "who may avail" texts. A group
    heading is left out on purpose: its wording (a label such as a business type) is also the
    condition prefix of rows that are kept, and a held-back group is held whole, so its parts
    already stand for it.
    """
    out: dict[str, str] = {}
    for r in SEED.requirements:
        if r.id in HELD.requirement_ids and not r.group and norm(r.text):
            out[norm(r.text)] = r.id
    held_who = {i.service_id for i in HELD.items if i.kind == "who_may_avail"}
    for service in SEED.services:
        if service.id in held_who and service.who_may_avail and norm(service.who_may_avail):
            out[norm(service.who_may_avail)] = f"{service.id}.who_may_avail"
    return out


def kept_texts(service_id: str) -> set[str]:
    """Wording the default load keeps for one service: the mock may show it."""
    return {norm(r.text) for r in HELD.seed.requirements if r.service_id == service_id}


def test_the_seed_holds_something_back_so_these_tests_are_not_empty():
    assert HELD.pending_services
    assert held_texts()


def test_every_mock_service_is_a_seed_service():
    assert set(MOCK_STATUS) <= {s.id for s in SEED.services}


def test_mock_pending_services_are_pending_for_the_loader():
    """One direction only: the mock has six of the seed's services, so the loader's pending set
    is larger and cannot be required to be inside the mock's."""
    mock_pending = {i for i, status in MOCK_STATUS.items() if status == "pending_lgu"}
    assert mock_pending
    assert mock_pending <= HELD.pending_services


def test_a_service_the_loader_marks_pending_is_never_confirmed_in_the_mock():
    """The other direction, for the services the mock does have."""
    confirmed = {i for i, status in MOCK_STATUS.items() if status == "confirmed"}
    assert confirmed
    assert not confirmed & HELD.pending_services


def test_no_confirmed_mock_service_shows_held_back_wording():
    held = held_texts()
    found: list[str] = []
    for lang, sections in MOCK["sections"].items():
        for service_id, section in sections.items():
            if section["info_status"] != "confirmed":
                continue
            kept = kept_texts(service_id)
            for shown in strings(section):
                for text, origin in held.items():
                    if text in norm(shown) and text not in kept:
                        found.append(f"{service_id} ({lang}) shows {shown!r}: held back as {origin}")
    assert found == []


def test_pending_mock_sections_send_nothing_but_name_and_office():
    empty = {"requirement_count": None, "fee_text": None, "time_text": None}
    for sections in MOCK["sections"].values():
        for service_id, section in sections.items():
            if section["info_status"] != "pending_lgu":
                continue
            assert section["summary"] == empty, service_id
            for field in ("checklist", "fees", "steps", "notes", "related"):
                assert section[field] == [], (service_id, field)
    for row in MOCK["services"]:
        if row["info_status"] == "pending_lgu":
            assert row["summary"] == empty, row["id"]
