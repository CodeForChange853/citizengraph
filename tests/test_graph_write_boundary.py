"""graph/load.py is the only place that writes to Neo4j, and nothing at runtime can reach it.

CLAUDE.md rule 1: the runtime is read-only; the offline loader is the single admin write path.
The scanner is itself tested on small snippets so the boundary tests cannot pass by accident.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "citizengraph"
LOADER = ROOT / "graph" / "load.py"

WRITE_ATTRS = {"execute_write", "write_transaction", "begin_transaction"}
WRITE_CYPHER = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|LOAD\s+CSV|FOREACH)\b", re.IGNORECASE
)
RUN_ATTRS = {"run", "execute_query"}


def imports_loader(source: str) -> list[str]:
    """Describe every way `source` pulls in graph/load.py."""
    hits: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if parts[-1] == "load" or alias.name == "graph.load":
                    hits.append(f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            parts = module.split(".") if module else []
            if parts and parts[-1] == "load":
                hits.append(f"from {module} import ...")
            if any(alias.name == "load" for alias in node.names) and parts[-1:] in (
                [],
                ["graph"],
            ):
                hits.append(f"from {module or '.'} import load")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            v = node.value.replace("\\", "/")
            if v in {"graph.load", "graph/load", "load.py"} or v.endswith("graph/load.py"):
                hits.append(f"string reference {node.value!r}")
    return hits


def write_calls(source: str) -> list[str]:
    """Describe every call in `source` that starts a Neo4j write."""
    hits: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        name = node.func.attr
        if name in WRITE_ATTRS:
            hits.append(f".{name}()")
        elif name in RUN_ATTRS and node.args:
            first = node.args[0]
            if (
                isinstance(first, ast.Constant)
                and isinstance(first.value, str)
                and WRITE_CYPHER.search(first.value)
            ):
                hits.append(f".{name}() with write Cypher")
            if name == "execute_query" and not any(k.arg == "routing_" for k in node.keywords):
                hits.append(".execute_query() without routing_ (defaults to a write)")
    return hits


def python_files(base: Path):
    return sorted(p for p in base.rglob("*.py") if "__pycache__" not in p.parts)


class TestScannerItself:
    @pytest.mark.parametrize(
        "snippet",
        [
            "import load",
            "import graph.load",
            "from graph import load",
            "from graph.load import main",
            "from . import load",
            "from citizengraph.graph.load import x",
            "import importlib\nimportlib.import_module('graph.load')",
            "import runpy\nrunpy.run_path('graph/load.py')",
        ],
    )
    def test_detects_ways_of_importing_the_loader(self, snippet):
        assert imports_loader(snippet)

    @pytest.mark.parametrize(
        "snippet",
        [
            "from citizengraph.graph.loader import load_seed",
            "from citizengraph.graph import InMemoryGraph",
            "def load(x): ...",
            "import yaml",
        ],
    )
    def test_ignores_the_seed_loader_and_unrelated_code(self, snippet):
        assert imports_loader(snippet) == []

    @pytest.mark.parametrize(
        "snippet",
        [
            "session.execute_write(fn)",
            "session.write_transaction(fn)",
            "session.begin_transaction()",
            "session.run('MERGE (n:X {id: $i})', i=1)",
            "tx.run('match (n) detach delete n')",
            "driver.execute_query('MATCH (n) RETURN n')",
        ],
    )
    def test_detects_write_paths(self, snippet):
        assert write_calls(snippet)

    @pytest.mark.parametrize(
        "snippet",
        [
            "session.execute_read(fn)",
            "tx.run('MATCH (s:Service) RETURN s LIMIT 5')",
            "driver.execute_query('MATCH (n:Service) RETURN n LIMIT 1', routing_='r')",
            "rows.run()",
        ],
    )
    def test_read_paths_pass(self, snippet):
        assert write_calls(snippet) == []


def test_the_scanner_sees_the_loader_and_the_source_tree():
    assert "execute_write" in LOADER.read_text(encoding="utf-8")
    assert write_calls(LOADER.read_text(encoding="utf-8"))
    assert len(python_files(SRC)) > 20


def test_no_module_under_src_imports_the_loader():
    offenders = {
        str(p.relative_to(ROOT)): hits
        for p in python_files(SRC)
        if (hits := imports_loader(p.read_text(encoding="utf-8")))
    }
    assert offenders == {}


def test_no_module_under_src_starts_a_write_transaction():
    offenders = {
        str(p.relative_to(ROOT)): hits
        for p in python_files(SRC)
        if (hits := write_calls(p.read_text(encoding="utf-8")))
    }
    assert offenders == {}


def test_api_and_cores_specifically_stay_clear_of_the_loader():
    for sub in ("api", "core1", "core2", "gateway", "composer", "llm", "guardrail"):
        for p in python_files(SRC / sub):
            text = p.read_text(encoding="utf-8")
            assert imports_loader(text) == [], p
            assert write_calls(text) == [], p


def test_the_loader_is_the_only_writer_in_the_repo():
    skip = {"tests", ".venv", "venv", "node_modules", ".git"}
    offenders = {}
    for p in python_files(ROOT):
        rel = p.relative_to(ROOT)
        if rel.parts[0] in skip or p == LOADER:
            continue
        if hits := write_calls(p.read_text(encoding="utf-8")):
            offenders[str(rel)] = hits
    assert offenders == {}


def test_the_loader_depends_only_on_the_seed_package_and_the_driver():
    tree = ast.parse(LOADER.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for name in names:
            if name.split(".")[0] == "citizengraph":
                assert name.startswith("citizengraph.graph"), name
