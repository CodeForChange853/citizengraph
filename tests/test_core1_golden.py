"""Golden file for the canonical Core 1 templates: the exact Cypher text is pinned.

The other Core 1 tests check properties of the templates (guardrail, parameters, coverage). None
of them notices a query that is still valid but means something else, for example
``ORDER BY st.order`` turned into ``ORDER BY st.id``. Here every template is compared, character
for character, with ``tests/golden/core1_cypher.json``, and the orderings are also written down
in this file, so they hold even when somebody regenerates the golden file.

Regenerating (only after a deliberate change to ``core1/templates.py``)::

    UPDATE_GOLDEN=1 python -m pytest tests/test_core1_golden.py

That run rewrites the file and FAILS when the content changed, so a regeneration can never look
like a normal pass. Review the diff of the JSON file, then run again without the variable.
"""

from __future__ import annotations

import difflib
import json
import os
import re
from pathlib import Path

import pytest

from citizengraph.core1 import templates as T

GOLDEN = Path(__file__).resolve().parent / "golden" / "core1_cypher.json"
GOLDEN_NAME = "tests/golden/core1_cypher.json"
UPDATE_ENV = "UPDATE_GOLDEN"
REGENERATE = f"{UPDATE_ENV}=1 python -m pytest tests/test_core1_golden.py"

# Change this number deliberately, together with the golden file and ORDER_BY below.
EXPECTED_COUNT = 38

ALL = sorted(T.TEMPLATES.values(), key=lambda t: t.key)

Entry = dict[str, list[str]]


def name(t: T.Template) -> str:
    """The key in the golden file, also the test id: ``fees/per_step/filtered``."""
    return f"{t.intent}/{t.shape}/{'filtered' if t.filtered else 'plain'}"


def entry(t: T.Template) -> Entry:
    # one list item per line, so a changed query is a one-line diff in the JSON file
    return {"cypher": t.cypher.split("\n"), "intents": list(t.intents), "params": list(t.params)}


def current() -> dict[str, Entry]:
    return {name(t): entry(t) for t in ALL}


def render(data: dict[str, Entry]) -> str:
    """The one canonical form of the file: sorted keys, indent 2, ASCII only, final newline."""
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def read_golden_text() -> str:
    # text mode turns a CRLF checkout (Windows, core.autocrlf) back into "\n"
    return GOLDEN.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def golden() -> dict[str, Entry]:
    """The committed golden file. It is written only when UPDATE_GOLDEN is exactly "1"."""
    if os.environ.get(UPDATE_ENV) == "1":
        if os.environ.get("CI"):
            pytest.fail(f"{UPDATE_ENV} must not be set in CI: the golden file is committed")
        expected = render(current())
        if not GOLDEN.is_file() or read_golden_text() != expected:
            GOLDEN.parent.mkdir(parents=True, exist_ok=True)
            with GOLDEN.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(expected)
            pytest.fail(
                f"golden file regenerated ({GOLDEN_NAME}); review the diff and re-run without "
                f"{UPDATE_ENV}"
            )
    if not GOLDEN.is_file():
        pytest.fail(f"{GOLDEN_NAME} is missing; it is never created by a normal run: {REGENERATE}")
    return json.loads(read_golden_text())


# ---- the exact text ----------------------------------------------------------------------------


@pytest.mark.parametrize("template", ALL, ids=name)
def test_template_text_is_exactly_the_golden_text(
    template: T.Template, golden: dict[str, Entry]
) -> None:
    key = name(template)
    if key not in golden:
        pytest.fail(f"{key} is not in {GOLDEN_NAME}. After reviewing the new query: {REGENERATE}")
    want = golden[key]
    want_cypher = "\n".join(want["cypher"])
    if template.cypher != want_cypher:
        diff = "\n".join(
            difflib.unified_diff(
                want_cypher.split("\n"),
                template.cypher.split("\n"),
                fromfile=f"golden {key}",
                tofile=f"templates.py {key}",
                lineterm="",
            )
        )
        pytest.fail(f"the Cypher of {key} changed:\n{diff}\nIf intended: {REGENERATE}")
    assert list(template.params) == want["params"], key
    assert list(template.intents) == want["intents"], key
    assert set(want) == {"cypher", "intents", "params"}, key


def test_golden_file_and_templates_have_the_same_keys(golden: dict[str, Entry]) -> None:
    have = {name(t) for t in ALL}
    assert sorted(have - set(golden)) == [], "templates missing from the golden file"
    assert sorted(set(golden) - have) == [], "golden entries with no template"


def test_template_count_is_the_golden_count(golden: dict[str, Entry]) -> None:
    assert len(T.TEMPLATES) == len(golden)
    assert len({name(t) for t in ALL}) == len(ALL)  # the file key loses nothing of the tuple key


def test_template_count_is_changed_on_purpose() -> None:
    assert len(T.TEMPLATES) == EXPECTED_COUNT


def test_golden_file_is_in_canonical_form(golden: dict[str, Entry]) -> None:
    # hand edits, duplicate keys or another key order would make a regeneration a noisy diff
    assert read_golden_text() == render(golden), f"not canonical; {REGENERATE}"
    assert read_golden_text().isascii()


# ---- orderings, written down here and not read from the golden file ---------------------------
# (intent, shape) -> the exact ORDER BY expression, or None for a query that returns one
# aggregate or one node row and has no ORDER BY at all. The plain and the filtered template of a
# pair have the same ordering.

ORDER_BY: dict[tuple[str, str], str | None] = {
    ("requirements", "list"): "r.id",
    ("requirements", "count"): None,
    ("requirements", "doc_services"): "s.id, r.id",
    ("requirements", "doc_in_service"): "r.id",
    ("requirements", "office_req_counts"): "n DESC, s.id",
    ("requirements", "compare_requirements"): "s.id",
    ("fees", "list"): "f.id",
    ("fees", "per_step"): "st.order, f.id",
    ("fees", "cheapest"): "lowest, s.id",
    ("fees", "no_fee_rows"): "s.id",
    ("fees", "fees_total"): None,
    ("fees", "fee_time"): "st.order, f.id",
    ("fees", "compare_fees"): "s.id",
    ("steps", "list"): "st.order",
    ("steps", "count"): None,
    ("steps", "external_steps"): "st.order",
    ("processing_time", "list"): "st.order",
    ("processing_time", "longest_step"): "st.minutes_max DESC, st.order",
    ("processing_time", "compare_time"): "s.id, st.order",
    ("where_to_secure", "list"): "r.id",
    ("where_to_secure", "go_first"): "r.id",
    ("where_to_secure", "doc_where"): "s.id, r.id",
    ("where_to_secure", "agency_services"): "s.id",
    ("where_to_secure", "office_prereqs"): "s.id, r.id",
    ("who_may_avail", "list"): None,
    ("who_may_avail", "office_who"): "s.id",
    ("office", "list"): None,
    ("office", "office_services"): "s.id",
    ("office", "office_count"): None,
}


def order_terms(cypher: str) -> list[str]:
    """The terms of the query's ORDER BY line (empty when it has none)."""
    found = [line for line in cypher.split("\n") if line.startswith("ORDER BY ")]
    assert len(found) <= 1
    return [term.strip() for term in found[0][len("ORDER BY ") :].split(",")] if found else []


def returns(cypher: str, column: str) -> bool:
    """True when the RETURN line lists ``column`` (``st.id``), not merely something ending in it."""
    line = next(line for line in cypher.split("\n") if line.startswith("RETURN "))
    return re.search(rf"(?<![\w.]){re.escape(column)}\b", line) is not None


def test_every_template_has_an_expected_ordering() -> None:
    assert {(t.intent, t.shape) for t in ALL} == set(ORDER_BY)


@pytest.mark.parametrize("template", ALL, ids=name)
def test_query_ends_with_the_expected_order_by_and_limit(template: T.Template) -> None:
    lines = template.cypher.split("\n")
    expected = ORDER_BY[(template.intent, template.shape)]
    assert re.fullmatch(r"LIMIT [1-9]\d*", lines[-1])
    if expected is None:
        # ... RETURN <one row> / LIMIT 1
        assert "ORDER BY" not in template.cypher
        assert lines[-2].startswith("RETURN ") and lines[-1] == "LIMIT 1"
    else:
        # ... RETURN <columns> / ORDER BY <expected> / LIMIT n
        assert lines[-2] == f"ORDER BY {expected}"
        assert lines[-3].startswith("RETURN ")
        assert template.cypher.count("ORDER BY") == 1


def test_step_rows_are_ordered_by_the_step_order() -> None:
    # st.order is the charter's step number; st.id is only an identifier
    listing = [t for t in ALL if returns(t.cypher, "st.id")]
    assert {(t.intent, t.shape) for t in listing} == {
        ("steps", "list"),
        ("steps", "external_steps"),
        ("processing_time", "list"),
        ("processing_time", "longest_step"),
        ("processing_time", "compare_time"),
        ("fees", "per_step"),
        ("fees", "fee_time"),
    }
    for t in listing:
        terms = order_terms(t.cypher)
        assert "st.order" in terms, t.key
        assert "st.id" not in terms, t.key


def test_fee_rows_are_ordered_by_the_fee_id() -> None:
    # Fee labels can be null or repeated, so only the id gives a stable order
    listing = [t for t in ALL if returns(t.cypher, "f.id")]
    assert {(t.intent, t.shape) for t in listing} == {
        ("fees", "list"),
        ("fees", "per_step"),
        ("fees", "fee_time"),
    }
    for t in listing:
        per_step = returns(t.cypher, "st.id")
        assert order_terms(t.cypher) == (["st.order", "f.id"] if per_step else ["f.id"]), t.key


def test_requirement_rows_are_ordered_by_the_requirement_id_last() -> None:
    listing = [t for t in ALL if returns(t.cypher, "r.id")]
    assert len(listing) >= 7
    for t in listing:
        assert order_terms(t.cypher)[-1] == "r.id", t.key
