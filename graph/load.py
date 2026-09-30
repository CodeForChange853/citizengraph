"""Admin-only: write the curated seed (graph/seed/*.yaml) into Neo4j.

    NEO4J_PASSWORD=... python graph/load.py [--uri bolt://localhost:7687] [--user neo4j]
                                            [--database NAME] [--batch-size 500] [--dry-run]

This is the ONLY place in the repository that writes to Neo4j (CLAUDE.md rule 1: the runtime is
read-only, this offline loader is the single admin write path). Nothing under src/citizengraph/
may import it or start a write transaction; tests/test_graph_write_boundary.py enforces both.

What it does:
  1. loads and cross-validates the seed with citizengraph.graph (stops on any problem);
  2. runs graph/schema.cypher (constraints and indexes, all `IF NOT EXISTS`);
  3. upserts nodes, then relationships, with parameterized `UNWIND $rows ... MERGE` statements,
     one write transaction per batch of at most --batch-size rows.

Re-running is idempotent: every node is MERGEd on its id and its properties are replaced, every
relationship is MERGEd. It only adds and updates; it never deletes, so a record removed from the
seed stays in the database until it is cleaned up by hand.

Never written to the database: staff names (`internal_person_raw`), and anything not listed in
docs/specs.md section 1 except the review/source bookkeeping properties below.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_SRC = Path(__file__).resolve().parents[1] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from citizengraph.graph.ids import clean_name, slug
from citizengraph.graph.loader import DEFAULT_SEED_DIR, SeedError, load_seed
from citizengraph.graph.models import Seed

SCHEMA_PATH = Path(__file__).with_name("schema.cypher")
DEFAULT_BATCH_SIZE = 500


@dataclass(frozen=True)
class Batch:
    """All rows for one statement. `name` is `node:<Label>` or `rel:<TYPE>[:<From>]`."""

    name: str
    cypher: str
    rows: list[dict[str, Any]]


@dataclass
class LoadReport:
    plan: list[Batch]
    transactions: int = 0
    counts: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------------------------
# Statements. Labels and relationship types are fixed constants; every value is a parameter.

_NODE = "UNWIND $rows AS row\nMERGE (n:{label} {{id: row.id}})\nSET n = row.props"
_REL = (
    "UNWIND $rows AS row\n"
    "MATCH (a:{src} {{id: row.a}})\n"
    "MATCH (b:{dst} {{id: row.b}})\n"
    "MERGE (a)-[:{rel}]->(b)"
)


def _node_statement(label: str) -> str:
    return _NODE.format(label=label)


def _rel_statement(src: str, rel: str, dst: str) -> str:
    return _REL.format(src=src, rel=rel, dst=dst)


def _props(**values: Any) -> dict[str, Any]:
    """Drop nulls: Neo4j has no null properties, and `SET n = map` replaces the old ones."""
    return {k: v for k, v in values.items() if v is not None}


def _node_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"id": r["id"], "props": r} for r in rows]


def _pairs(pairs: list[tuple[str, str]]) -> list[dict[str, Any]]:
    return [{"a": a, "b": b} for a, b in pairs]


def build_plan(seed: Seed) -> list[Batch]:
    """Turn a validated seed into ordered batches (nodes first). Pure: touches no database."""
    offices = [
        _props(id=o.id, name=o.name, review_status=o.review_status) for o in seed.offices
    ]
    services = [
        _props(
            id=s.id,
            name=s.name,
            classification=s.classification,
            transaction_type=s.transaction_type,
            who_may_avail=s.who_may_avail,
            total_fee_text=s.total_fee_text,
            total_time_text=s.total_time_text,
            description=s.description,
            charter_ref=s.charter_ref,
            review_status=s.review_status,
            source_sheet=s.source.sheet,
            source_rows=s.source.rows,
        )
        for s in seed.services
    ]
    variants = [
        _props(id=v.id, dimension=v.dimension, value=v.value) for v in seed.variants
    ]

    agencies: dict[str, str] = {}
    for r in seed.requirements:
        if r.secured_at:
            agencies.setdefault(slug(r.secured_at), clean_name(r.secured_at))
    roles: dict[str, str] = {}
    for st in seed.steps:
        if st.role:
            roles.setdefault(slug(st.role), clean_name(st.role))

    requirements = [
        _props(
            id=r.id,
            key=r.key,
            text=r.text,
            group=r.group,
            parent_id=r.parent_id,
            min_required=r.min_required,
            condition_text=r.condition_text,
            condition_structured=r.condition_structured,
            review_status=r.review_status,
            source_sheet=r.source.sheet,
            source_row=r.source_row,
        )
        for r in seed.requirements
    ]
    steps = []
    for st in seed.steps:
        d = st.duration
        steps.append(
            _props(
                id=st.id,
                order=st.order,
                citizen_action=st.citizen_action,
                agency_action=st.agency_action,
                external_agency=st.external_agency,
                dur_min=d.value_min,
                dur_max=d.value_max,
                dur_unit=d.unit,
                minutes_min=d.minutes_min,
                minutes_max=d.minutes_max,
                day_type=d.day_type,
                review_status=st.review_status,
                source_sheet=st.source.sheet,
                source_row=st.source_row,
            )
        )
    fees = [
        _props(
            id=f.id,
            label=f.label,
            amount_min=f.amount_min,
            amount_max=f.amount_max,
            unit=f.unit,
            note=f.note,
            condition_text=f.condition_text,
            condition_structured=f.condition_structured,
            review_status=f.review_status,
            source_sheet=f.source.sheet,
            source_row=f.source_row,
        )
        for f in seed.fees
    ]

    def node(label: str, rows: list[dict[str, Any]]) -> Batch:
        return Batch(f"node:{label}", _node_statement(label), _node_rows(rows))

    def rel(name: str, src: str, kind: str, dst: str, pairs: list[tuple[str, str]]) -> Batch:
        return Batch(name, _rel_statement(src, kind, dst), _pairs(pairs))

    return [
        node("Office", offices),
        node("Service", services),
        node("Variant", variants),
        node("Agency", [{"id": i, "name": n} for i, n in agencies.items()]),
        node("Role", [{"id": i, "title": t} for i, t in roles.items()]),
        node("Requirement", requirements),
        node("Step", steps),
        node("Fee", fees),
        rel("rel:OFFERS", "Office", "OFFERS", "Service",
            [(s.office_id, s.id) for s in seed.services]),
        rel("rel:REQUIRES", "Service", "REQUIRES", "Requirement",
            [(r.service_id, r.id) for r in seed.requirements]),
        rel("rel:SECURED_AT", "Requirement", "SECURED_AT", "Agency",
            [(r.id, slug(r.secured_at)) for r in seed.requirements if r.secured_at]),
        rel("rel:PART_OF", "Requirement", "PART_OF", "Requirement",
            [(r.id, r.parent_id) for r in seed.requirements if r.parent_id]),
        rel("rel:APPLIES_WHEN:Requirement", "Requirement", "APPLIES_WHEN", "Variant",
            [(r.id, v) for r in seed.requirements for v in r.variant_ids]),
        rel("rel:HAS_STEP", "Service", "HAS_STEP", "Step",
            [(st.service_id, st.id) for st in seed.steps]),
        rel("rel:NEXT", "Step", "NEXT", "Step",
            [(st.id, st.next_id) for st in seed.steps if st.next_id]),
        rel("rel:PERFORMED_BY", "Step", "PERFORMED_BY", "Role",
            [(st.id, slug(st.role)) for st in seed.steps if st.role]),
        rel("rel:HAS_FEE", "Service", "HAS_FEE", "Fee",
            [(f.service_id, f.id) for f in seed.fees]),
        rel("rel:APPLIES_WHEN:Fee", "Fee", "APPLIES_WHEN", "Variant",
            [(f.id, v) for f in seed.fees for v in f.variant_ids]),
    ]  # fmt: skip


# ---------------------------------------------------------------------------------------------


def schema_statements(path: Path = SCHEMA_PATH) -> list[str]:
    """The statements of graph/schema.cypher, without comments or trailing semicolons."""
    lines = [
        line for line in path.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("//")
    ]  # fmt: skip
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


def _chunks(rows: list[dict[str, Any]], size: int) -> Iterator[list[dict[str, Any]]]:
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def _run_statement(tx: Any, statement: str) -> None:
    tx.run(statement)


def _run_rows(tx: Any, statement: str, rows: list[dict[str, Any]]) -> None:
    tx.run(statement, rows=rows)


def write_seed(
    driver: Any,
    seed: Seed,
    *,
    database: str | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    schema_path: Path = SCHEMA_PATH,
) -> LoadReport:
    """Run the schema, then write every batch in its own write transaction."""
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    plan = build_plan(seed)
    report = LoadReport(plan=plan)
    session_args = {"database": database} if database else {}
    with driver.session(**session_args) as session:
        for statement in schema_statements(schema_path):
            session.execute_write(_run_statement, statement)
            report.transactions += 1
        for batch in plan:
            for chunk in _chunks(batch.rows, batch_size):
                session.execute_write(_run_rows, batch.cypher, chunk)
                report.transactions += 1
            report.counts[batch.name] = len(batch.rows)
    return report


def _summary(seed: Seed) -> str:
    return (
        f"{len(seed.offices)} offices, {len(seed.services)} services, "
        f"{len(seed.requirements)} requirements, {len(seed.steps)} steps, "
        f"{len(seed.fees)} fees, {len(seed.variants)} variants"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Write graph/seed/*.yaml into Neo4j (admin only).")
    ap.add_argument("--seed-dir", default=str(DEFAULT_SEED_DIR))
    ap.add_argument("--uri", default=os.environ.get("NEO4J_URI", "bolt://localhost:7687"))
    ap.add_argument("--user", default=os.environ.get("NEO4J_USER", "neo4j"))
    ap.add_argument("--database", default=os.environ.get("NEO4J_DATABASE"))
    ap.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    ap.add_argument("--dry-run", action="store_true", help="validate and print counts only")
    args = ap.parse_args(argv)
    if args.batch_size < 1:
        ap.error("--batch-size must be at least 1")

    try:
        seed = load_seed(args.seed_dir)
    except SeedError as exc:
        print(exc, file=sys.stderr)
        return 1
    if args.dry_run:
        plan = build_plan(seed)
        print(f"dry run: seed is valid ({_summary(seed)}); {len(plan)} statements planned, "
              "nothing written")
        return 0

    password = os.environ.get("NEO4J_PASSWORD")
    if not password:
        print("NEO4J_PASSWORD is not set (the password is only read from the environment)",
              file=sys.stderr)
        return 2

    from neo4j import GraphDatabase  # imported here so dry runs and tests need no driver

    try:
        with GraphDatabase.driver(args.uri, auth=(args.user, password)) as driver:
            driver.verify_connectivity()
            report = write_seed(
                driver, seed, database=args.database, batch_size=args.batch_size
            )
    except Exception as exc:  # noqa: BLE001 - admin CLI: report any driver/server failure once
        print(f"load failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 3
    print(f"loaded {_summary(seed)} in {report.transactions} write transactions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
