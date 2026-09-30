"""graph/load.py without a database: the plan it builds and how it drives a driver.

A recording fake stands in for the Neo4j driver, so nothing here needs a server. Tests that
need a real Neo4j are in test_graph_load_integration.py (marked `integration`).
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from graph_fixtures import staff_names

from citizengraph.graph.loader import DEFAULT_SEED_DIR, load_seed

ROOT = Path(__file__).resolve().parents[1]


def _import_loader():
    spec = importlib.util.spec_from_file_location("citizengraph_admin_load", ROOT / "graph/load.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


loadmod = _import_loader()


@pytest.fixture(scope="module")
def seed():
    return load_seed(DEFAULT_SEED_DIR)


@pytest.fixture(scope="module")
def plan(seed):
    return loadmod.build_plan(seed)


def by_name(plan):
    return {b.name: b for b in plan}


class FakeTx:
    def __init__(self, log):
        self.log = log

    def run(self, query, parameters=None, **kwargs):
        self.log.append(("run", query, {**(parameters or {}), **kwargs}))


class FakeSession:
    def __init__(self, log, kwargs):
        self.log = log
        self.log.append(("session", kwargs))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute_write(self, fn, *args, **kwargs):
        self.log.append(("tx_begin",))
        result = fn(FakeTx(self.log), *args, **kwargs)
        self.log.append(("tx_commit",))
        return result

    def run(self, *a, **k):  # the loader must use transaction functions only
        raise AssertionError("auto-commit session.run is not allowed in the loader")

    def execute_read(self, *a, **k):
        raise AssertionError("the loader has no reason to read")


class FakeDriver:
    def __init__(self):
        self.log: list[tuple] = []

    def session(self, **kwargs):
        return FakeSession(self.log, kwargs)


class TestPlan:
    def test_node_rows_match_the_seed(self, seed, plan):
        n = {b.name: len(b.rows) for b in plan}
        assert n["node:Office"] == 2
        assert n["node:Service"] == 13
        assert n["node:Requirement"] == len(seed.requirements)
        assert n["node:Step"] == len(seed.steps)
        assert n["node:Fee"] == len(seed.fees)
        assert n["node:Variant"] == len(seed.variants)
        assert n["node:Agency"] == len({r.secured_at for r in seed.requirements if r.secured_at})
        assert n["node:Role"] == len({s.role for s in seed.steps if s.role})

    def test_relationship_rows_match_the_seed(self, seed, plan):
        n = {b.name: len(b.rows) for b in plan}
        assert n["rel:OFFERS"] == len(seed.services)
        assert n["rel:REQUIRES"] == len(seed.requirements)
        assert n["rel:SECURED_AT"] == len([r for r in seed.requirements if r.secured_at])
        assert n["rel:PART_OF"] == len([r for r in seed.requirements if r.parent_id])
        assert n["rel:APPLIES_WHEN:Requirement"] == sum(len(r.variant_ids) for r in seed.requirements)
        assert n["rel:HAS_STEP"] == len(seed.steps)
        assert n["rel:NEXT"] == len(seed.steps) - len(seed.services)
        assert n["rel:PERFORMED_BY"] == len([s for s in seed.steps if s.role])
        assert n["rel:HAS_FEE"] == len(seed.fees)
        assert n["rel:APPLIES_WHEN:Fee"] == sum(len(f.variant_ids) for f in seed.fees)

    def test_nodes_are_written_before_the_relationships_that_need_them(self, plan):
        names = [b.name for b in plan]
        last_node = max(i for i, n in enumerate(names) if n.startswith("node:"))
        first_rel = min(i for i, n in enumerate(names) if n.startswith("rel:"))
        assert last_node < first_rel

    def test_plan_is_deterministic(self, seed, plan):
        again = loadmod.build_plan(seed)
        assert [(b.name, b.cypher, b.rows) for b in again] == [
            (b.name, b.cypher, b.rows) for b in plan
        ]

    def test_step_rows_carry_the_parsed_duration(self, plan):
        rows = by_name(plan)["node:Step"].rows
        stated = next(r for r in rows if r["props"].get("dur_unit") == "day")
        assert stated["props"]["dur_min"] == stated["props"]["dur_max"] == 10
        assert stated["props"]["minutes_max"] == 14400
        assert stated["props"]["day_type"] == "unknown"
        unstated = next(r for r in rows if r["props"].get("dur_unit") is None)
        assert unstated["props"].get("dur_min") is None
        assert unstated["props"]["day_type"] == "unknown"

    def test_every_node_row_has_its_id_inside_props(self, plan):
        for b in plan:
            if b.name.startswith("node:"):
                for row in b.rows:
                    assert row["props"]["id"] == row["id"]

    def test_review_status_travels_with_each_charter_node(self, plan):
        for name in ("node:Service", "node:Requirement", "node:Step", "node:Fee"):
            for row in by_name(plan)[name].rows:
                assert row["props"]["review_status"] == "needs_review"


class TestStatementHygiene:
    def test_every_statement_is_parameterized(self, plan):
        for b in plan:
            assert "$rows" in b.cypher, b.name

    def test_no_seed_text_is_inlined_into_cypher(self, seed, plan):
        texts = {
            v
            for rec in [*seed.services, *seed.requirements, *seed.steps, *seed.fees]
            for v in rec.model_dump().values()
            if isinstance(v, str) and len(v) > 6
        }
        assert len(texts) > 100
        blob = "\n".join(b.cypher for b in plan)
        assert [t for t in texts if t in blob] == []
        assert not re.search(r"\d{3,}", blob), "numbers must come from parameters"

    def test_data_statements_only_merge_and_set(self, plan):
        banned = re.compile(
            r"\b(CREATE|DELETE|DETACH|REMOVE|DROP|LOAD|FOREACH|CALL)\b", re.IGNORECASE
        )
        for b in plan:
            assert "MERGE" in b.cypher, b.name
            assert not banned.search(b.cypher), b.name

    def test_relationship_statements_only_match_existing_nodes(self, plan):
        for b in plan:
            if b.name.startswith("rel:"):
                assert b.cypher.count("MATCH") == 2, b.name
                assert b.cypher.count("MERGE") == 1, b.name


class TestStaffNames:
    def test_no_staff_name_reaches_the_database(self, seed, plan):
        blob = json.dumps([b.rows for b in plan], ensure_ascii=False)
        assert "internal_person" not in blob
        names = staff_names(seed)
        assert len(names) > 20
        assert sorted(n for n in names if n in blob) == []


class TestWriteSeed:
    def test_schema_runs_first_then_data_in_batches(self, seed):
        driver = FakeDriver()
        report = loadmod.write_seed(driver, seed, batch_size=7)
        ops = [e for e in driver.log if e[0] == "run"]
        schema = loadmod.schema_statements()
        assert len(schema) >= 8
        assert [o[1] for o in ops[: len(schema)]] == schema
        data = ops[len(schema):]
        assert data and all("$rows" in o[1] for o in data)
        assert all(len(o[2]["rows"]) <= 7 for o in data)
        assert sum(len(o[2]["rows"]) for o in data) == sum(len(b.rows) for b in report.plan)
        assert report.transactions == len(schema) + len(data)

    def test_each_batch_is_its_own_write_transaction(self, seed):
        driver = FakeDriver()
        loadmod.write_seed(driver, seed, batch_size=50)
        begins = [e for e in driver.log if e[0] == "tx_begin"]
        commits = [e for e in driver.log if e[0] == "tx_commit"]
        runs = [e for e in driver.log if e[0] == "run"]
        assert len(begins) == len(commits) == len(runs)

    def test_running_twice_issues_the_same_statements(self, seed):
        a, b = FakeDriver(), FakeDriver()
        loadmod.write_seed(a, seed)
        loadmod.write_seed(b, seed)
        assert a.log == b.log

    def test_database_name_is_passed_to_the_session(self, seed):
        driver = FakeDriver()
        loadmod.write_seed(driver, seed, database="charter")
        assert all(e[1] == {"database": "charter"} for e in driver.log if e[0] == "session")

    def test_batch_size_must_be_positive(self, seed):
        with pytest.raises(ValueError):
            loadmod.write_seed(FakeDriver(), seed, batch_size=0)

    def test_schema_statements_are_split_and_idempotent(self):
        stmts = loadmod.schema_statements()
        assert all(s.startswith("CREATE") and "IF NOT EXISTS" in s for s in stmts)
        assert not any(s.endswith(";") for s in stmts)
        assert not any(s.lstrip().startswith("//") for s in stmts)


class TestCli:
    def run(self, *args, env=None):
        return subprocess.run(
            [sys.executable, str(ROOT / "graph/load.py"), *args],
            capture_output=True,
            text=True,
            env=env,
            cwd=ROOT,
            timeout=60,
            check=False,
        )

    def test_dry_run_validates_and_prints_counts_without_connecting(self):
        done = self.run("--dry-run", env=_base_env())
        assert done.returncode == 0, done.stderr
        assert "13 services" in done.stdout
        assert "dry run" in done.stdout.lower()

    def test_refuses_to_run_without_a_password(self):
        env = _base_env()
        env.pop("NEO4J_PASSWORD", None)
        done = self.run(env=env)
        assert done.returncode == 2
        assert "NEO4J_PASSWORD" in done.stderr

    def test_a_broken_seed_stops_before_any_connection(self, tmp_path):
        (tmp_path / "offices.yaml").write_text("offices: []\n", encoding="utf-8")
        done = self.run("--dry-run", "--seed-dir", str(tmp_path), env=_base_env())
        assert done.returncode == 1
        assert "missing_file" in done.stderr


def _base_env():
    import os

    return {k: v for k, v in os.environ.items() if k.startswith(("PATH", "PYTHON", "HOME", "VIRTUAL"))}
