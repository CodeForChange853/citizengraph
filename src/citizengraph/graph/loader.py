"""Read ``graph/seed/*.yaml`` and cross-validate it. Pure: no Neo4j, model or network.

``load_seed`` and ``parse_seed`` return a ``Seed`` or raise ``SeedError`` listing *every*
problem found (not only the first), so a curator can fix a file in one pass. This is the
read-only side; the Neo4j writer is ``graph/load.py`` (see the decisions log in CLAUDE.md).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from citizengraph.graph.ids import clean_name, slug
from citizengraph.graph.models import (
    Fee,
    Link,
    Office,
    Requirement,
    Seed,
    Service,
    Step,
    Variant,
)

DEFAULT_SEED_DIR = Path(__file__).resolve().parents[3] / "graph" / "seed"

_FILES: dict[str, type] = {
    "offices": Office,
    "services": Service,
    "requirements": Requirement,
    "steps": Step,
    "fees": Fee,
    "variants": Variant,
    "links": Link,
}


@dataclass(frozen=True)
class SeedIssue:
    code: str
    message: str

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


class SeedError(ValueError):
    def __init__(self, issues: list[SeedIssue]):
        self.issues = issues
        lines = "\n".join(f"  {i}" for i in issues)
        super().__init__(f"{len(issues)} seed problem(s):\n{lines}")


def load_seed(seed_dir: Path | str | None = None) -> Seed:
    """Read the six seed YAML files from `seed_dir` (default: graph/seed) and validate them."""
    base = Path(seed_dir) if seed_dir is not None else DEFAULT_SEED_DIR
    raw: dict[str, list[dict[str, Any]]] = {}
    issues: list[SeedIssue] = []
    for name in _FILES:
        path = base / f"{name}.yaml"
        if not path.is_file():
            issues.append(SeedIssue("missing_file", f"{path} does not exist"))
            continue
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            issues.append(SeedIssue("bad_yaml", f"{path.name}: {exc}"))
            continue
        if not isinstance(doc, dict) or not isinstance(doc.get(name), list):
            issues.append(
                SeedIssue("bad_yaml", f"{path.name}: expected a top-level '{name}:' list")
            )
            continue
        raw[name] = doc[name]
    if issues:
        raise SeedError(issues)
    return parse_seed(raw)


def parse_seed(raw: Mapping[str, list[dict[str, Any]]]) -> Seed:
    """Build a ``Seed`` from already-parsed YAML (file stem -> list of records)."""
    issues: list[SeedIssue] = []
    parsed: dict[str, list[Any]] = {}
    for name, model in _FILES.items():
        parsed[name] = []
        for i, rec in enumerate(raw.get(name, [])):
            try:
                parsed[name].append(model.model_validate(rec))
            except ValidationError as exc:
                who = rec.get("id", f"#{i}") if isinstance(rec, dict) else f"#{i}"
                for err in exc.errors():
                    where = ".".join(str(p) for p in err["loc"])
                    issues.append(SeedIssue("schema", f"{name}.yaml [{who}] {where}: {err['msg']}"))
    if issues:
        raise SeedError(issues)
    seed = Seed(**parsed)
    issues = validate_seed(seed)
    if issues:
        raise SeedError(issues)
    return seed


def validate_seed(seed: Seed) -> list[SeedIssue]:
    """Cross-reference checks. Returns every issue found (empty when the seed is sound)."""
    v = _Validator(seed)
    v.run()
    return v.issues


class _Validator:
    def __init__(self, seed: Seed):
        self.seed = seed
        self.issues: list[SeedIssue] = []
        self.services = {s.id: s for s in seed.services}
        self.variants = {x.id: x for x in seed.variants}
        self.requirements = {r.id: r for r in seed.requirements}
        self.steps = {s.id: s for s in seed.steps}
        self.steps_of: dict[str, list[Step]] = defaultdict(list)
        for st in seed.steps:
            self.steps_of[st.service_id].append(st)

    def add(self, code: str, message: str) -> None:
        self.issues.append(SeedIssue(code, message))

    def run(self) -> None:
        self.duplicate_ids()
        self.services_reference_offices()
        self.records_reference_services()
        self.variant_links()
        self.requirement_tree()
        self.step_orders_and_chains()
        self.fee_steps()
        self.sources()
        self.slugs()
        self.links()

    def duplicate_ids(self) -> None:
        s = self.seed
        for kind, records in (
            ("offices", s.offices), ("services", s.services), ("requirements", s.requirements),
            ("steps", s.steps), ("fees", s.fees), ("variants", s.variants), ("links", s.links),
        ):  # fmt: skip
            for rec_id, n in Counter(r.id for r in records).items():
                if n > 1:
                    self.add("duplicate_id", f"{kind}: id {rec_id!r} appears {n} times")
        node_ids = [
            *(r.id for r in s.offices), *(r.id for r in s.services),
            *(r.id for r in s.requirements), *(r.id for r in s.steps), *(r.id for r in s.fees),
        ]  # fmt: skip
        records_by_kind = (
            ("office", s.offices),
            ("service", s.services),
            ("requirement", s.requirements),
            ("step", s.steps),
            ("fee", s.fees),
        )  # fmt: skip
        for rec_id, n in Counter(node_ids).items():
            kinds = {k for k, records in records_by_kind if any(r.id == rec_id for r in records)}
            if len(kinds) > 1:
                self.add(
                    "duplicate_id", f"id {rec_id!r} is used by more than one kind: {sorted(kinds)}"
                )

    def services_reference_offices(self) -> None:
        offices = {o.id for o in self.seed.offices}
        for s in self.seed.services:
            if s.office_id not in offices:
                self.add("unknown_office", f"service {s.id}: office_id {s.office_id!r} not found")

    def records_reference_services(self) -> None:
        for kind, records in (
            ("requirement", self.seed.requirements),
            ("step", self.seed.steps),
            ("fee", self.seed.fees),
        ):
            for r in records:
                if r.service_id not in self.services:
                    self.add(
                        "unknown_service", f"{kind} {r.id}: service_id {r.service_id!r} not found"
                    )

    def variant_links(self) -> None:
        for kind, records in (("requirement", self.seed.requirements), ("fee", self.seed.fees)):
            for r in records:
                for vid in r.variant_ids:
                    if vid not in self.variants:
                        self.add("unknown_variant", f"{kind} {r.id}: variant {vid!r} not found")

    def requirement_tree(self) -> None:
        children: dict[str, list[Requirement]] = defaultdict(list)
        for r in self.seed.requirements:
            if r.parent_id is None:
                continue
            parent = self.requirements.get(r.parent_id)
            if parent is None:
                self.add("unknown_parent", f"requirement {r.id}: parent {r.parent_id!r} not found")
                continue
            if parent.service_id != r.service_id:
                self.add(
                    "parent_other_service",
                    f"requirement {r.id}: parent {parent.id} belongs to service {parent.service_id}",
                )
            children[parent.id].append(r)
            missing = set(parent.variant_ids) - set(r.variant_ids)
            if missing:
                self.add(
                    "variant_not_inherited",
                    f"requirement {r.id}: lacks parent {parent.id}'s variants {sorted(missing)}",
                )
        for r in self.seed.requirements:
            seen = {r.id}
            cur = r
            while cur.parent_id and cur.parent_id in self.requirements:
                cur = self.requirements[cur.parent_id]
                if cur.id in seen:
                    self.add("parent_cycle", f"requirement {r.id}: parent chain loops at {cur.id}")
                    break
                seen.add(cur.id)
        for pid, kids in children.items():
            parent = self.requirements[pid]
            if not parent.group:
                self.add("group_mismatch", f"requirement {pid} has children but group is false")
            if parent.min_required is not None and parent.min_required > len(kids):
                self.add(
                    "min_required_too_large",
                    f"requirement {pid}: min_required {parent.min_required} > {len(kids)} children",
                )

    def step_orders_and_chains(self) -> None:
        for sid in self.services:
            steps = self.steps_of.get(sid, [])
            if not steps:
                self.add("no_steps", f"service {sid} has no steps")
                continue
            orders = sorted(st.order for st in steps)
            if orders != list(range(1, len(steps) + 1)):
                self.add(
                    "step_order", f"service {sid}: step orders {orders} are not 1..{len(steps)}"
                )
            self.check_chain(sid, steps)
        for st in self.seed.steps:
            src = st.duration_shared_from
            if src is None:
                continue
            target = self.steps.get(src)
            if (
                target is None
                or target.service_id != st.service_id
                or target.order >= st.order
                or target.duration.status != "stated"
            ):
                self.add(
                    "unknown_shared_from",
                    f"step {st.id}: duration_shared_from {src!r} must be an earlier step of the "
                    "same service with a stated duration",
                )

    def check_chain(self, sid: str, steps: list[Step]) -> None:
        ok = True
        for st in steps:
            if st.next_id is None:
                continue
            nxt = self.steps.get(st.next_id)
            if nxt is None:
                self.add("unknown_next", f"step {st.id}: next_id {st.next_id!r} not found")
                ok = False
            elif nxt.service_id != sid:
                self.add(
                    "next_other_service",
                    f"step {st.id}: next_id {nxt.id} belongs to service {nxt.service_id}",
                )
                ok = False
        if not ok:
            return
        preds = Counter(st.next_id for st in steps if st.next_id)
        heads = [st for st in steps if st.id not in preds]
        shared = [i for i, n in preds.items() if n > 1]
        if shared or len(heads) != 1:
            self.add(
                "next_chain",
                f"service {sid}: NEXT links must form one chain "
                f"(heads={[h.id for h in heads]}, shared successors={shared})",
            )
            return
        walked: list[Step] = []
        cur: Step | None = heads[0]
        while cur is not None and len(walked) <= len(steps):
            walked.append(cur)
            cur = self.steps.get(cur.next_id) if cur.next_id else None
        if len(walked) != len(steps):
            self.add(
                "next_chain",
                f"service {sid}: NEXT chain reaches {len(walked)} of {len(steps)} steps "
                "(broken link or loop)",
            )
        elif [w.order for w in walked] != sorted(w.order for w in walked):
            self.add("next_chain", f"service {sid}: NEXT chain does not follow the order numbers")

    def fee_steps(self) -> None:
        for f in self.seed.fees:
            if f.step_id is None:
                continue
            st = self.steps.get(f.step_id)
            if st is None:
                self.add("unknown_step", f"fee {f.id}: step_id {f.step_id!r} not found")
            elif st.service_id != f.service_id:
                self.add(
                    "step_other_service",
                    f"fee {f.id}: step {st.id} belongs to service {st.service_id}",
                )

    def sources(self) -> None:
        for kind, records in (
            ("requirement", self.seed.requirements),
            ("step", self.seed.steps),
            ("fee", self.seed.fees),
        ):
            for r in records:
                svc = self.services.get(r.service_id)
                if svc is None:
                    continue
                if r.source != svc.source:
                    self.add(
                        "source_mismatch",
                        f"{kind} {r.id}: source differs from its service's block ({svc.id})",
                    )
                lo, hi = svc.source.rows
                if not lo <= r.source_row <= hi:
                    self.add(
                        "source_row_outside",
                        f"{kind} {r.id}: row {r.source_row} is outside {svc.id}'s rows {lo}-{hi}",
                    )
        for s in self.seed.services:
            lo, hi = s.source.rows
            if s.total_source_row is not None and not lo <= s.total_source_row <= hi:
                self.add(
                    "source_row_outside",
                    f"service {s.id}: total row {s.total_source_row} is outside rows {lo}-{hi}",
                )

    def slugs(self) -> None:
        for label, names in (
            ("agency", (r.secured_at for r in self.seed.requirements if r.secured_at)),
            ("role", (st.role for st in self.seed.steps if st.role)),
        ):
            by_slug: dict[str, set[str]] = defaultdict(set)
            for name in names:
                by_slug[slug(name)].add(clean_name(name))
            for s, variants in by_slug.items():
                if len(variants) > 1:
                    self.add(
                        "duplicate_slug",
                        f"{label} names {sorted(variants)} all become id {s!r}; make them identical",
                    )

    def links(self) -> None:
        blocks = [svc.source for svc in self.seed.services]
        offices = {o.id for o in self.seed.offices}
        agencies = {clean_name(r.secured_at) for r in self.seed.requirements if r.secured_at}
        seen: set[tuple[str, str, str]] = set()
        offices_of_agency: dict[str, set[str]] = defaultdict(set)
        for link in self.seed.links:
            for src in link.sources:
                if src not in blocks:
                    self.add(
                        "source_mismatch",
                        f"link {link.id}: source {src.sheet} rows {src.rows} is not a service "
                        "block of the seed",
                    )
            req = self.requirements.get(link.requirement_id) if link.requirement_id else None
            if link.requirement_id and req is None:
                self.add(
                    "unknown_requirement",
                    f"link {link.id}: requirement {link.requirement_id!r} not found",
                )
            if link.kind == "requirement_satisfied_by":
                if link.service_id not in self.services:
                    self.add(
                        "unknown_service", f"link {link.id}: service {link.service_id!r} not found"
                    )
                elif req is not None and req.service_id == link.service_id:
                    self.add(
                        "link_self",
                        f"link {link.id}: requirement {req.id} cannot be satisfied by its own service",
                    )
                key = (link.kind, link.requirement_id or "", link.service_id or "")
            else:
                agency = clean_name(link.agency or "")
                if link.office_id not in offices:
                    self.add(
                        "unknown_office", f"link {link.id}: office {link.office_id!r} not found"
                    )
                if agency not in agencies:
                    self.add(
                        "unknown_agency",
                        f"link {link.id}: no requirement is secured at an agency named {agency!r}",
                    )
                if req is not None and (
                    req.secured_at is None or clean_name(req.secured_at) != agency
                ):
                    self.add(
                        "agency_context_mismatch",
                        f"link {link.id}: requirement {req.id} is not secured at {agency!r}",
                    )
                offices_of_agency[agency].add(link.office_id or "")
                key = (link.kind, agency, link.office_id or "")
            if key in seen:
                self.add(
                    "duplicate_link", f"link {link.id} repeats {key[0]} {key[1]!r} -> {key[2]!r}"
                )
            seen.add(key)
        for agency, targets in offices_of_agency.items():
            if len(targets) > 1:
                self.add(
                    "agency_two_offices",
                    f"agency {agency!r} is linked to offices {sorted(targets)}",
                )
