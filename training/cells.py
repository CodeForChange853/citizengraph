"""Cells: what one training question is ABOUT (targets, query shape, stated variants).

A cell is (shape, the targets the gateway would have linked, the variant combination the phrase
states). The generator turns each cell into examples (language x noise level x phrase family).

Only things that exist in ``graph/seed/`` are used: services, offices, agencies, documents, and
variant combinations that some requirement or fee of the service links. A data-dependent shape is
generated only where its data exists (for example ``cheapest`` only for offices whose services
have fee rows), so the gold query never asks about nothing.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from itertools import combinations, product

from citizengraph.core1 import templates as T
from citizengraph.core1.targets import Target
from citizengraph.graph import InMemoryGraph
from training.phrasebook import Phrasebook

# Shapes that never appear in train, validation or test_synthetic: their families form the
# `test_unseen_shape` split, which measures how a model copes with a query shape it was not taught.
HELD_OUT_SHAPES = frozenset({"office_who", "compare_time"})
MAX_PAIRS = 40  # service pairs per comparison shape

Combo = tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class Cell:
    intent: str
    shape: str
    targets: tuple[Target, ...]
    entities: tuple[tuple[str, str], ...]  # placeholder -> id of what the phrase names
    combo: Combo = ()
    context: bool = False  # a service target that the phrase does not name (session carry-over)

    @property
    def key(self) -> str:
        targets = ",".join(str(t) for t in self.targets)
        combo = ",".join(f"{d}={v}" for d, v in self.combo)
        return f"{self.intent}/{self.shape}|{targets}|{combo}|{int(self.context)}"

    @property
    def entity_map(self) -> dict[str, str]:
        return dict(self.entities)

    @property
    def filtered(self) -> bool:
        """The gold query carries the variant filter: variants are stated and the shape can be
        filtered (the graph has no variant links on steps, times, offices, ...)."""
        return bool(self.combo) and T.supports_variants(self.intent, self.shape)


def variant_combos(graph: InMemoryGraph, service_id: str) -> list[Combo]:
    """Every selection of at most one value per dimension that the service's records link."""
    dims: dict[str, set[str]] = {}
    for rec in (*graph.requirements(service_id), *graph.fees(service_id)):
        for vid in rec.variant_ids:
            dimension, _, value = vid.partition(":")
            dims.setdefault(dimension, set()).add(value)
    names = sorted(dims)
    options = [[None, *sorted(dims[d])] for d in names]
    return [
        tuple((d, v) for d, v in zip(names, choice, strict=True) if v is not None)
        for choice in product(*options)
    ]


def withheld_combos(graph: InMemoryGraph, service_id: str, seed: int) -> set[Combo]:
    """Non-empty combinations kept out of train (only for services with at least 3 of them)."""
    nonempty = [c for c in variant_combos(graph, service_id) if c]
    if len(nonempty) < 3:
        return set()
    rng = random.Random(f"{seed}|withheld|{service_id}")
    return set(rng.sample(nonempty, max(1, round(len(nonempty) / 3))))


# ---- what data exists --------------------------------------------------------------------------


def matching_requirements(graph: InMemoryGraph, words: str):
    return [r for r in graph.seed.requirements if words in r.text.lower()]


def has_go_first_data(graph: InMemoryGraph, service_id: str) -> bool:
    for req in graph.requirements(service_id):
        if graph.satisfied_by(req.id):
            return True
        if req.secured_at and graph.office_for_agency(req.secured_at):
            return True
    return False


def has_prereq_data(graph: InMemoryGraph, office_id: str) -> bool:
    """Some requirement of the office's services points to another office (like office_prereqs)."""
    for svc in graph.services(office_id):
        for req in graph.requirements(svc.id):
            if any(graph.office_of(d.id).id != office_id for d in graph.satisfied_by(req.id)):
                return True
            office = graph.office_for_agency(req.secured_at) if req.secured_at else None
            if office is not None and office.id != office_id:
                return True
    return False


def _service_data(graph: InMemoryGraph) -> dict[str, set[str]]:
    """Which services have which kind of data (names are shape requirements below)."""
    has: dict[str, set[str]] = {
        k: set()
        for k in ("leaf_requirements", "fees", "step_fees", "external", "timed", "go_first")
    }
    for svc in graph.seed.services:
        sid = svc.id
        if any(not r.group for r in graph.requirements(sid)):
            has["leaf_requirements"].add(sid)
        fees = graph.fees(sid)
        if fees:
            has["fees"].add(sid)
        if any(f.step_id for f in fees):
            has["step_fees"].add(sid)
        steps = graph.steps(sid)
        if any(st.external_agency for st in steps):
            has["external"].add(sid)
        if any(st.duration.minutes_max is not None for st in steps):
            has["timed"].add(sid)
        if has_go_first_data(graph, sid):
            has["go_first"].add(sid)
    return has


# service-level shapes that only make sense where the service has some data
_SERVICE_NEEDS = {
    ("requirements", "count"): "leaf_requirements",
    ("fees", "per_step"): "step_fees",
    ("fees", "fees_total"): "fees",
    ("fees", "fee_time"): "fees",
    ("processing_time", "longest_step"): "timed",
    ("steps", "external_steps"): "external",
    ("where_to_secure", "go_first"): "go_first",
}


def _pairs(ids: list[str], seed: int, shape: str) -> list[tuple[str, str]]:
    rng = random.Random(f"{seed}|pairs|{shape}")
    pairs = [(a, b) for a, b in combinations(sorted(ids), 2)]
    chosen = rng.sample(pairs, min(MAX_PAIRS, len(pairs)))
    return [(b, a) if rng.random() < 0.5 else (a, b) for a, b in sorted(chosen)]


def enumerate_cells(graph: InMemoryGraph, book: Phrasebook, seed: int = 0) -> list[Cell]:
    """Every cell the dataset covers, in a stable order."""
    has = _service_data(graph)
    offices = [o.id for o in graph.seed.offices if graph.services(o.id)]
    shapes = [(i, s) for (i, s, f) in T.TEMPLATES if not f]
    cells: list[Cell] = []
    for intent, shape in shapes:
        needs = T.TEMPLATES[(intent, shape, False)].needs
        if needs == ("sid",):
            required = _SERVICE_NEEDS.get((intent, shape))
            for svc in graph.seed.services:
                if required and svc.id not in has[required]:
                    continue
                for combo in variant_combos(graph, svc.id):
                    cells.append(
                        Cell(
                            intent,
                            shape,
                            (
                                Target(kind="service", id=svc.id),
                                Target(kind="office", id=svc.office_id),
                            ),
                            (("service", svc.id),),
                            combo,
                        )
                    )
        elif needs == ("oid",):
            for oid in offices:
                if not _office_has_data(graph, shape, oid):
                    continue
                cells.append(
                    Cell(intent, shape, (Target(kind="office", id=oid),), (("office", oid),))
                )
                rng = random.Random(f"{seed}|context|{oid}|{shape}")
                ctx = rng.choice(sorted(s.id for s in graph.services(oid)))
                cells.append(
                    Cell(
                        intent,
                        shape,
                        (Target(kind="service", id=ctx), Target(kind="office", id=oid)),
                        (("office", oid),),
                        context=True,
                    )
                )
        elif needs == ("aid",):
            for aid in sorted(book.agency_names):
                cells.append(
                    Cell(intent, shape, (Target(kind="agency", id=aid),), (("agency", aid),))
                )
        elif needs == ("doc",):
            for doc in sorted(book.document_names):
                rows = matching_requirements(graph, doc)
                if shape == "doc_where" and not any(r.secured_at for r in rows):
                    continue
                cells.append(
                    Cell(intent, shape, (Target(kind="document", id=doc),), (("document", doc),))
                )
        elif needs == ("doc", "sid"):
            for doc in sorted(book.document_names):
                for sid in sorted({r.service_id for r in matching_requirements(graph, doc)}):
                    svc = graph.service(sid)
                    for combo in variant_combos(graph, sid):
                        cells.append(
                            Cell(
                                intent,
                                shape,
                                (
                                    Target(kind="service", id=sid),
                                    Target(kind="office", id=svc.office_id),
                                    Target(kind="document", id=doc),
                                ),
                                (("service", sid), ("document", doc)),
                                combo,
                            )
                        )
        elif needs == ("sid", "sid2"):
            ids = [s.id for s in graph.seed.services]
            if shape == "compare_fees":
                ids = sorted(has["fees"])
            elif shape == "compare_requirements":
                ids = sorted(has["leaf_requirements"])
            for a, b in _pairs(ids, seed, shape):
                cells.append(
                    Cell(
                        intent,
                        shape,
                        (Target(kind="service", id=a), Target(kind="service", id=b)),
                        (("service", a), ("service2", b)),
                    )
                )
        else:  # pragma: no cover - a new template needs a cell rule
            raise ValueError(f"no cell rule for {intent}/{shape} needs {needs}")
    return cells


def _office_has_data(graph: InMemoryGraph, shape: str, office_id: str) -> bool:
    services = graph.services(office_id)
    if shape == "cheapest":
        return any(graph.fees(s.id) for s in services)
    if shape == "no_fee_rows":
        return any(not graph.fees(s.id) for s in services)
    if shape == "office_prereqs":
        return has_prereq_data(graph, office_id)
    if shape == "office_req_counts":
        return any(graph.requirements(s.id) for s in services)
    return bool(services)


__all__ = [
    "HELD_OUT_SHAPES",
    "Cell",
    "Combo",
    "enumerate_cells",
    "has_go_first_data",
    "matching_requirements",
    "variant_combos",
    "withheld_combos",
]
