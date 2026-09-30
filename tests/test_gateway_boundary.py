"""What the gateway must never do: call a model, reach the network, read the held-out set, log
citizen text. Plus the Filipino review list in docs/gateway_notes.md stays complete."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from citizengraph.gateway import native_review

ROOT = Path(__file__).resolve().parents[1]
GATEWAY = ROOT / "src" / "citizengraph" / "gateway"
SOURCES = sorted(GATEWAY.rglob("*.py"))
DATA = sorted(GATEWAY.rglob("*.yaml")) + [ROOT / "graph" / "seed" / "aliases.yaml"]
FORBIDDEN_IMPORTS = {
    "citizengraph.llm", "llama_cpp", "ollama", "openai", "anthropic", "requests", "httpx",
    "urllib", "urllib3", "socket", "http", "aiohttp", "subprocess", "neo4j", "fastapi",
    "logging", "sqlite3",
}  # fmt: skip


def imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_the_scan_sees_the_package():
    assert len(SOURCES) >= 12 and len(DATA) >= 6


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_no_model_network_or_logging_imports(path):
    bad = {
        name for name in imports(path)
        if any(name == f or name.startswith(f + ".") for f in FORBIDDEN_IMPORTS)
    }  # fmt: skip
    assert not bad, f"{path.name} imports {sorted(bad)}"


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_nothing_prints_or_opens_files_outside_the_data_dirs(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    if path.name != "native_review.py":  # its command line prints the review list
        assert "print" not in calls
    assert "eval" not in calls and "exec" not in calls and "open" not in calls


@pytest.mark.parametrize("path", SOURCES + DATA, ids=lambda p: p.name)
def test_the_heldout_folder_is_never_touched(path):
    assert "heldout" not in path.read_text(encoding="utf-8").lower()


def test_gateway_does_not_reach_the_graph_writer():
    for path in SOURCES:
        assert not {n for n in imports(path) if n.split(".")[-1] == "load"}, path.name
        assert "execute_write" not in path.read_text(encoding="utf-8")


def test_gateway_data_files_hold_no_staff_names_or_secrets():
    banned = ("password:", "api_key", "secret:", "token:")
    for path in DATA:
        text = path.read_text(encoding="utf-8").lower()
        assert not any(b in text for b in banned), path.name


# ------------------------------------------------------------------ the review list


def test_notes_list_every_filipino_string_needing_review():
    notes = (ROOT / "docs" / "gateway_notes.md").read_text(encoding="utf-8")
    assert native_review.BEGIN in notes and native_review.END in notes
    block = notes.split(native_review.BEGIN, 1)[1].split(native_review.END, 1)[0]
    assert block.strip() == native_review.render().strip(), (
        "docs/gateway_notes.md is out of date: run "
        "`python -m citizengraph.gateway.native_review` and paste it between the markers"
    )


def test_review_list_covers_aliases_and_lexicon_data():
    titles = [title for title, _ in native_review.collect()]
    assert any("aliases of `business_permit`" in t for t in titles)
    assert any("cues_fil" in t for t in titles)
    assert any("sms_fil" in t for t in titles)
    assert any("intents.yaml" in t for t in titles)
    assert any("spam.yaml" in t for t in titles)
    total = sum(len(items) for _, items in native_review.collect())
    assert total > 900


def test_every_filipino_alias_is_in_the_review_list():
    from citizengraph.gateway import load_aliases

    listed = {item for _, items in native_review.collect() for item in items}
    missing = [a.text for a in load_aliases().aliases if a.lang == "fil" and a.text not in listed]
    assert not missing
