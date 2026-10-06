"""Records that are loadable as fact but suspect, and so are held back until the LGU confirms.

The markers are data (``graph/seed/*.yaml``), never code: ``Requirement.suspect`` with a
``suspect_reason``, and ``Service.held_back`` entries for ``requirements`` (the whole checklist
is untrusted or incomplete) or ``who_may_avail``. ``hold_back`` turns a validated seed into the
seed that may be shown to citizens plus the list of what was left out and why. Pure: no Neo4j.

What is held back:
  * a suspect requirement, every requirement of a service whose checklist is held back, every
    descendant (``parent_id``) of a held-back requirement, and a group that lost one of its
    parts (with its other parts: a group is shown whole or not at all);
  * a held-back ``who_may_avail`` (it becomes null);
  * a cross-office link that names a held-back requirement, or an Agency that only held-back
    requirements are secured at (the Agency itself is then no longer derived from the seed).

A service with any held-back citizen-visible item is *pending*: an empty or shorter list must
not be read as "nothing is required". A held-back checklist makes its service pending even
when it has no rows. Steps are never held back.

Limits. Always call ``hold_back`` on the full seed: ``HoldBack.seed`` no longer contains the
suspect rows, so holding it back again would lose their services from ``pending_services``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from citizengraph.graph.ids import clean_name
from citizengraph.graph.models import Seed

HeldKind = Literal["requirements", "requirement", "who_may_avail", "link"]

# Kinds a citizen would see missing; a dropped link alone does not make a service pending.
_CITIZEN_VISIBLE: frozenset[str] = frozenset({"requirements", "requirement", "who_may_avail"})


@dataclass(frozen=True)
class HeldItem:
    service_id: str
    kind: HeldKind
    record_id: str | None  # requirement or link id; null for a service-level item
    reason: str


@dataclass(frozen=True)
class HoldBack:
    seed: Seed  # what is left: safe to load
    items: tuple[HeldItem, ...]

    @property
    def pending_services(self) -> frozenset[str]:
        return frozenset(i.service_id for i in self.items if i.kind in _CITIZEN_VISIBLE)

    @property
    def requirement_ids(self) -> frozenset[str]:
        return frozenset(i.record_id for i in self.items if i.kind == "requirement" and i.record_id)

    def by_service(self) -> dict[str, list[HeldItem]]:
        """Items grouped by service, services in seed order."""
        out: dict[str, list[HeldItem]] = {}
        for service in self.seed.services:
            items = [i for i in self.items if i.service_id == service.id]
            if items:
                out[service.id] = items
        return out


def hold_back(seed: Seed) -> HoldBack:
    """Split a validated seed into what may be loaded and what is held back (with reasons)."""
    items: list[HeldItem] = []
    checklist_reason: dict[str, str] = {}
    who_reason: dict[str, str] = {}
    for service in seed.services:
        for entry in service.held_back:
            if entry.field == "requirements":
                checklist_reason[service.id] = entry.reason
                items.append(HeldItem(service.id, "requirements", None, entry.reason))
            else:
                who_reason[service.id] = entry.reason
                items.append(HeldItem(service.id, "who_may_avail", None, entry.reason))

    by_id = {r.id: r for r in seed.requirements}
    reasons: dict[str, str] = {}
    for r in seed.requirements:
        if r.suspect:
            reasons[r.id] = r.suspect_reason or "suspect"
        elif r.service_id in checklist_reason:
            reasons[r.id] = f"the whole checklist is held back: {checklist_reason[r.service_id]}"
    # Spread through the parent_id tree until nothing changes: down to every part of a held-back
    # group, and up to a group that lost a part (it cannot be shown as complete, and its
    # min_required would count parts that are no longer there).
    changed = True
    while changed:
        changed = False
        for r in seed.requirements:
            parent_id = r.parent_id
            if parent_id is None or parent_id not in by_id:
                continue
            if parent_id in reasons and r.id not in reasons:
                reasons[r.id] = f"part of held-back {parent_id}"
                changed = True
            elif r.id in reasons and parent_id not in reasons:
                reasons[parent_id] = f"its part {r.id} is held back, so the group is incomplete"
                changed = True
    for r in seed.requirements:
        if r.id in reasons:
            items.append(HeldItem(r.service_id, "requirement", r.id, reasons[r.id]))

    requirements = [r for r in seed.requirements if r.id not in reasons]
    agencies = {clean_name(r.secured_at) for r in requirements if r.secured_at}
    links = []
    for link in seed.links:
        held_req = by_id.get(link.requirement_id) if link.requirement_id in reasons else None
        if held_req is not None:
            items.append(
                HeldItem(held_req.service_id, "link", link.id, f"names held-back {held_req.id}")
            )
        elif link.kind == "agency_is_office" and clean_name(link.agency or "") not in agencies:
            owners = sorted(
                {
                    r.service_id
                    for r in seed.requirements
                    if r.secured_at and clean_name(r.secured_at) == clean_name(link.agency or "")
                }
            )
            for sid in owners:
                items.append(
                    HeldItem(
                        sid,
                        "link",
                        link.id,
                        f"agency {link.agency!r} is only named by held-back requirements",
                    )
                )
        else:
            links.append(link)

    services = [
        s.model_copy(update={"who_may_avail": None}) if s.id in who_reason else s
        for s in seed.services
    ]
    kept = seed.model_copy(
        update={"services": services, "requirements": requirements, "links": links}
    )
    return HoldBack(seed=kept, items=tuple(items))
