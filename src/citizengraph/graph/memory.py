"""In-memory graph built from the validated seed, with the lookups Core 1 and Core 2 tests need.

No Neo4j. The helpers mirror what the Cypher queries return, so tests can run without a server.

Variant matching, used by ``requirements`` and ``fees``: the caller passes what it knows, e.g.
``{"business_type": "corporation"}``. A record with variant links is kept when, for each
dimension it links, the caller either did not say anything about that dimension (unknown, so the
citizen is not left without a document) or gave a value the record links. Values within one
dimension are alternatives; different dimensions all have to hold. A condition the seed could not
structure (``condition_structured`` is false) cannot be filtered, so those records are always
returned; ask ``condition_unresolved`` / ``fee_condition_unresolved`` and show the condition text.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping

from citizengraph.graph.ids import clean_name
from citizengraph.graph.models import Fee, Link, Office, Requirement, Seed, Service, Step

VariantSelection = Mapping[str, "str | Iterable[str]"]


class UnknownServiceError(KeyError):
    """No service with that id."""


def _wanted(variants: VariantSelection | None) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for dimension, value in (variants or {}).items():
        out[dimension] = {value} if isinstance(value, str) else set(value)
    return out


def _matches(variant_ids: list[str], wanted: dict[str, set[str]]) -> bool:
    by_dimension: dict[str, set[str]] = defaultdict(set)
    for vid in variant_ids:
        dimension, _, value = vid.partition(":")
        by_dimension[dimension].add(value)
    return all(
        dimension not in wanted or wanted[dimension] & values
        for dimension, values in by_dimension.items()
    )


class InMemoryGraph:
    def __init__(self, seed: Seed):
        self.seed = seed
        self._services = {s.id: s for s in seed.services}
        self._offices = {o.id: o for o in seed.offices}
        self._requirements = {r.id: r for r in seed.requirements}
        self._fees = {f.id: f for f in seed.fees}
        self._requirements_of: dict[str, list[Requirement]] = defaultdict(list)
        for r in seed.requirements:
            self._requirements_of[r.service_id].append(r)
        self._fees_of: dict[str, list[Fee]] = defaultdict(list)
        for f in seed.fees:
            self._fees_of[f.service_id].append(f)
        self._fees_of_step: dict[str, list[Fee]] = defaultdict(list)
        for f in seed.fees:
            if f.step_id:
                self._fees_of_step[f.step_id].append(f)
        by_id = {st.id: st for st in seed.steps}
        self._steps_of: dict[str, list[Step]] = {}
        for sid in self._services:
            steps = [st for st in seed.steps if st.service_id == sid]
            successors = {st.next_id for st in steps if st.next_id}
            chain: list[Step] = []
            cur = next((st for st in steps if st.id not in successors), None)
            while cur is not None:
                chain.append(cur)
                cur = by_id.get(cur.next_id) if cur.next_id else None
            self._steps_of[sid] = chain

    @classmethod
    def from_dir(cls, seed_dir=None) -> InMemoryGraph:
        from citizengraph.graph.loader import load_seed

        return cls(load_seed(seed_dir))

    # services and offices

    def service(self, service_id: str) -> Service:
        try:
            return self._services[service_id]
        except KeyError:
            raise UnknownServiceError(service_id) from None

    def find_service(self, name: str) -> Service | None:
        """Exact match on the service name, ignoring case and extra spaces."""
        wanted = " ".join(name.split()).casefold()
        return next(
            (s for s in self._services.values() if " ".join(s.name.split()).casefold() == wanted),
            None,
        )

    def services(self, office_id: str | None = None) -> list[Service]:
        return [s for s in self._services.values() if office_id in (None, s.office_id)]

    def office_of(self, service_id: str) -> Office:
        return self._offices[self.service(service_id).office_id]

    # steps, requirements, fees

    def steps(self, service_id: str) -> list[Step]:
        """Steps in NEXT-chain order."""
        self.service(service_id)
        return list(self._steps_of[service_id])

    def requirements(
        self, service_id: str, variants: VariantSelection | None = None
    ) -> list[Requirement]:
        self.service(service_id)
        wanted = _wanted(variants)
        return [r for r in self._requirements_of[service_id] if _matches(r.variant_ids, wanted)]

    def fees(self, service_id: str, variants: VariantSelection | None = None) -> list[Fee]:
        self.service(service_id)
        wanted = _wanted(variants)
        return [f for f in self._fees_of[service_id] if _matches(f.variant_ids, wanted)]

    def fees_of_step(self, step_id: str) -> list[Fee]:
        """The fee rows charged at one step (the `CHARGES` relationship)."""
        if step_id not in {st.id for st in self.seed.steps}:
            raise KeyError(step_id)
        return list(self._fees_of_step.get(step_id, []))

    # cross-office links (suggestions until a person reviews them; see Link.review_status)

    def links(self, kind: str | None = None) -> list[Link]:
        return [link for link in self.seed.links if kind in (None, link.kind)]

    def satisfied_by(self, requirement_id: str) -> list[Service]:
        """Services whose output satisfies the requirement (suggested links included)."""
        return [
            self._services[link.service_id]
            for link in self.seed.links
            if link.kind == "requirement_satisfied_by"
            and link.requirement_id == requirement_id
            and link.service_id is not None
        ]

    def office_for_agency(self, agency: str) -> Office | None:
        """The scoped Office an Agency name stands for, when it is exactly one (else None)."""
        wanted = clean_name(agency)
        for link in self.seed.links:
            if (
                link.kind == "agency_is_office"
                and link.office_id
                and clean_name(link.agency or "") == wanted
            ):
                return self._offices[link.office_id]
        return None

    def condition_unresolved(self, requirement_id: str) -> bool:
        """True when the requirement, or a group it is part of, has a condition the seed could
        not turn into variant links."""
        seen: set[str] = set()
        cur: Requirement | None = self._requirements[requirement_id]
        while cur is not None and cur.id not in seen:
            if cur.condition_structured is False:
                return True
            seen.add(cur.id)
            cur = self._requirements.get(cur.parent_id) if cur.parent_id else None
        return False

    def fee_condition_unresolved(self, fee_id: str) -> bool:
        return self._fees[fee_id].condition_structured is False
