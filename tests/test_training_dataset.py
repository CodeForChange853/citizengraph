"""The generated training data: valid, deterministic, leak-free and inside the budget.

These tests build the FULL dataset (a few seconds) and need no GPU, model or network.
"""

from __future__ import annotations

import ast
import builtins
import os
import re
import time
from collections import Counter, defaultdict
from pathlib import Path

import pytest
from test_training_common import ROOT, load

from citizengraph.core1 import templates as T
from citizengraph.core1.prompt import MAX_PROMPT_TOKENS
from citizengraph.core1.slots import INTENTS, LANGUAGES, check_variants
from citizengraph.graph import InMemoryGraph
from citizengraph.guardrail.validator import validate_cypher

G = load("generate_dataset")
NOISE = load("noise")

SPLITS = G.SPLITS


@pytest.fixture(scope="module")
def graph():
    return InMemoryGraph.from_dir()


@pytest.fixture(scope="module")
def book():
    return G.load_phrasebook()


@pytest.fixture(scope="module")
def ds():
    started = time.perf_counter()
    dataset = G.build_dataset(seed=0)
    assert time.perf_counter() - started < 60, "the full dataset must generate in under a minute"
    return dataset


def everything(ds):
    return [e for s in SPLITS for e in ds.examples[s]]


# ---- the phrasebook ---------------------------------------------------------------------------


def test_the_phrasebook_is_consistent(book, graph):
    assert G.check_phrasebook(book, graph) == []


def test_every_template_shape_has_families_in_every_language(book):
    for intent, shape, filtered in T.TEMPLATES:
        if filtered:
            continue
        for language in LANGUAGES:
            assert len(book.families[(intent, shape, language)]) >= 3


def test_a_broken_phrasebook_is_reported(book, graph):
    broken = G.Phrasebook(
        service_names={k: v for k, v in book.service_names.items() if k != "business_permit"},
        variants=book.variants,
        variant_frames=book.variant_frames,
        variant_joiners=book.variant_joiners,
        families={**book.families, ("office", "list", "en"): (
            G.Family("office.list.en.1", "office", "list", "en", ("no placeholder here",)),
        )},
    )
    problems = "; ".join(G.check_phrasebook(broken, graph))
    assert "business_permit" in problems
    assert "{service}" in problems
    assert "at least 3 families" in problems


def test_phrases_carry_no_numbers_or_charter_words_of_their_own(book):
    # Templates are questions only: no amounts, days or document names.
    for fams in book.families.values():
        for fam in fams:
            for tpl in fam.templates:
                assert not re.search(r"\d", tpl), tpl


# ---- coverage ---------------------------------------------------------------------------------


def test_only_the_curated_services_are_used(ds, graph):
    curated = {s.id for s in graph.seed.services}
    assert len(curated) == 26
    used = {e.slots.service_id for e in everything(ds)}
    assert used == curated  # every curated service appears, nothing else does


def test_every_intent_shape_language_and_noise_level_is_present_in_every_split(ds):
    for split in SPLITS:
        rows = ds.examples[split]
        assert {(e.slots.intent, e.shape) for e in rows} == {
            (i, s) for (i, s, f) in T.TEMPLATES if not f
        }, split
        assert {e.slots.language for e in rows} == set(LANGUAGES)
        assert {e.noise for e in rows} == set(NOISE.NOISE_LEVELS)


def test_status_never_appears(ds):
    assert "status" in INTENTS
    assert all(e.slots.intent != "status" for e in everything(ds))


def test_variant_combinations_are_the_ones_that_exist(ds, graph):
    for e in everything(ds):
        assert check_variants(e.slots.variants) == []
        assert dict(e.slots.variants) in [
            dict(c) for c in G.variant_combos(graph, e.slots.service_id)
        ]


def test_derived_shapes_exist_only_where_the_data_exists(ds, graph):
    for e in everything(ds):
        svc = e.slots.service_id
        if e.shape == "per_step":
            assert any(f.step_id for f in graph.fees(svc))
        if e.shape == "go_first":
            assert G._has_go_first_data(graph, svc)
        if (e.slots.intent, e.shape) == ("requirements", "count"):
            assert any(not r.group for r in graph.requirements(svc))


def test_variants_appear_for_services_that_have_them(ds):
    with_variants = [e for e in everything(ds) if e.slots.variants]
    assert len(with_variants) > 200
    # an intent without variant links still sees variants in the slots: its gold is unfiltered
    steps = [e for e in with_variants if e.slots.intent == "steps"]
    assert steps and all(not e.template_key.endswith("true") for e in steps)


# ---- gold Cypher ------------------------------------------------------------------------------


def test_every_gold_query_in_the_full_dataset_passes_the_guardrail(ds):
    checked = set()
    for e in everything(ds):
        if e.cypher in checked:
            continue
        checked.add(e.cypher)
        result = validate_cypher(e.cypher)
        assert result.ok, (e.id, result.reasons)
    assert checked <= {t.cypher for t in T.TEMPLATES.values()}
    assert len(checked) >= 12


def test_every_gold_query_is_the_canonical_template_with_ids_as_parameters(ds):
    for e in everything(ds):
        assert e.cypher == T.build_query(e.slots, e.shape).cypher
        assert e.params["sid"] == e.slots.service_id
        assert ("variant_ids" in e.params) == e.template_key.endswith("true")
        assert e.slots.service_id not in e.cypher
        assert "'" not in e.cypher and '"' not in e.cypher


def test_variants_change_the_gold_only_through_the_filter(ds):
    for e in everything(ds):
        filtered = e.template_key.endswith("true")
        supported = T.supports_variants(e.slots.intent, e.shape)
        assert filtered == (bool(e.slots.variants) and supported)


# ---- prompts ----------------------------------------------------------------------------------


def test_prompts_are_under_budget(ds):
    worst = max(e.tokens for e in everything(ds))
    assert worst < MAX_PROMPT_TOKENS * 0.5, worst


def test_the_message_format_is_system_user_assistant(ds):
    for e in everything(ds)[:200]:
        roles = [m["role"] for m in e.messages()["messages"]]
        assert roles == ["system", "user", "assistant"]
        assert e.user.splitlines()[0] == f"service: {e.slots.service_id}"


# ---- splits -----------------------------------------------------------------------------------


def test_splits_do_not_share_phrase_template_families(ds):
    families = {s: {e.family for e in ds.examples[s]} for s in SPLITS}
    for a in SPLITS:
        for b in SPLITS:
            if a < b:
                assert not families[a] & families[b], (a, b)
    for split in SPLITS:
        assert all(ds.family_split[f] == split for f in families[split])


def test_every_group_puts_one_family_in_each_held_out_split(book, ds):
    for fams in book.families.values():
        counts = Counter(ds.family_split[f.id] for f in fams)
        assert counts["validation"] == 1 and counts["test_synthetic"] == 1
        assert counts["train"] == len(fams) - 2


def test_no_prompt_is_repeated_across_splits(ds):
    seen: dict[str, str] = {}
    for split in SPLITS:
        for e in ds.examples[split]:
            assert seen.setdefault(e.user + "|" + e.system, split) == split


def test_withheld_variant_combinations_never_reach_train(ds):
    assert ds.withheld
    withheld = {
        (sid, tuple(sorted(c.items()))) for sid, combos in ds.withheld.items() for c in combos
    }
    assert all(
        (e.slots.service_id, tuple(sorted(e.slots.variants.items()))) not in withheld
        for e in ds.examples["train"]
    )
    held = [e for s in ("validation", "test_synthetic") for e in ds.examples[s] if e.combo_withheld]
    assert held
    assert all(e.combo_withheld for e in everything(ds) if (
        e.slots.service_id, tuple(sorted(e.slots.variants.items()))) in withheld)


def test_train_is_the_bulk_and_evaluation_splits_are_not_tiny(ds):
    sizes = {s: len(ds.examples[s]) for s in SPLITS}
    assert sizes["train"] > 3 * sizes["validation"] > 0
    assert sizes["test_synthetic"] > 500


# ---- determinism ------------------------------------------------------------------------------


def test_same_seed_same_bytes(ds, tmp_path):
    again = G.build_dataset(seed=0)
    for split in SPLITS:
        assert G.jsonl(ds.examples[split]) == G.jsonl(again.examples[split])
        assert G.jsonl(ds.examples[split], meta=True) == G.jsonl(again.examples[split], meta=True)
    a, b = tmp_path / "a", tmp_path / "b"
    G.write_dataset(ds, a)
    G.write_dataset(again, b)
    for p in sorted(a.iterdir()):
        assert p.read_bytes() == (b / p.name).read_bytes()
    assert G.dataset_card(ds) == G.dataset_card(again)
    assert b"\r" not in (a / "train.jsonl").read_bytes()


def test_a_different_seed_gives_different_data(ds):
    other = G.build_dataset(seed=1)
    assert G.jsonl(other.examples["train"]) != G.jsonl(ds.examples["train"])


# ---- no leakage, no facts ---------------------------------------------------------------------


def _norm(text: str) -> str:
    return " ".join(text.casefold().split())


def _answer_strings(graph) -> set[str]:
    out: set[str] = set()

    def add(*values):
        out.update(_norm(v) for v in values if isinstance(v, str) and v.strip())

    for r in graph.seed.requirements:
        add(r.text, r.condition_text, r.secured_at)
    for f in graph.seed.fees:
        add(f.label, f.note, f.condition_text)
    for st in graph.seed.steps:
        add(st.citizen_action, st.agency_action, st.external_agency, st.role, st.duration.raw)
    for s in graph.seed.services:
        add(s.who_may_avail, s.total_fee_text, s.total_time_text, s.description)
    for o in graph.seed.offices:
        add(o.name)
    for link in graph.seed.links:
        add(link.agency)
    return out


def test_no_example_contains_charter_answer_text(ds, graph, book):
    allowed = {_norm(s.name) for s in graph.seed.services}
    for names in book.service_names.values():
        allowed.update(_norm(n) for n in names["en"] + names["fil"])
    for forms in book.variants.values():
        allowed.update(_norm(n) for n in forms["en"] + forms["fil"])
    answers = {
        a for a in _answer_strings(graph)
        if len(a) >= 12 and not any(a.strip(" :.,()-") in ok for ok in allowed)
    }
    assert len(answers) > 100  # the check has something to look for
    for e in everything(ds):
        text = _norm(e.user + " " + e.cypher + " " + e.clean_phrase)
        for a in answers:
            assert a not in text, (e.id, a)
    for e in ds.examples["train"][:1]:
        assert not [a for a in answers if a in _norm(e.system)]


HELDOUT = ROOT / "eval" / "heldout"
HELDOUT_SUFFIXES = {".csv", ".jsonl", ".json", ".txt", ".tsv", ".xlsx"}


def test_the_generator_never_touches_the_held_out_folder(monkeypatch):
    touched: list[str] = []
    real_open = builtins.open
    real_scandir = os.scandir

    def watching_open(file, *a, **k):
        if "heldout" in str(file):
            touched.append(str(file))
        return real_open(file, *a, **k)

    def watching_scandir(path=".", *a, **k):
        if "heldout" in str(path):
            touched.append(str(path))
        return real_scandir(path, *a, **k)

    monkeypatch.setattr(builtins, "open", watching_open)
    monkeypatch.setattr(os, "scandir", watching_scandir)

    def watching_path_open(self, *a, **k):
        if "heldout" in str(self):
            touched.append(str(self))
        return real_open(self, *a, **k)

    monkeypatch.setattr(Path, "open", watching_path_open)
    G.build_dataset(seed=3)
    assert touched == []
    # and no code in training/ or core1/ even spells the folder (docstrings and comments may)
    for path in [*(ROOT / "training").glob("*.py"), *(ROOT / "src/citizengraph/core1").glob("*.py")]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = {
            id(node.body[0].value)
            for node in ast.walk(tree)
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef))
            and node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert id(node) in docstrings or "heldout" not in node.value.lower(), path


def test_no_example_contains_a_held_out_inquiry(ds):
    """Runs only where the real inquiries are present (they are not in the repository).

    The generator and this project's tooling never read them; this test is the one place where a
    person who has the folder checks the finished dataset against it. Each data file is read as
    plain lines, and every line of 25 characters or more must not occur inside any example.
    """
    files = [p for p in HELDOUT.rglob("*") if p.suffix.lower() in HELDOUT_SUFFIXES and p.is_file()]
    if not files:
        pytest.skip("eval/heldout/ has no data files here (the real inquiries are kept elsewhere)")
    lines = {
        _norm(line)
        for p in files
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines()
        if len(line.strip()) >= 25
    }
    for e in everything(G.build_dataset(seed=0)):
        text = _norm(e.user + " " + e.clean_phrase)
        assert not [ln for ln in lines if ln in text]


# ---- Filipino review list --------------------------------------------------------------------


NOTES = ROOT / "docs" / "training_notes.md"


def test_every_filipino_string_is_listed_for_native_review(book):
    notes = NOTES.read_text(encoding="utf-8")
    assert G.REVIEW_BEGIN in notes and G.REVIEW_END in notes
    start, end = notes.index(G.REVIEW_BEGIN), notes.index(G.REVIEW_END)
    assert notes[start : end + len(G.REVIEW_END)] == G.render_review_block(book), (
        "run: python -m training.generate_dataset --write-review-list docs/training_notes.md"
    )
    listed = notes[start:end]
    for fams in book.families.values():
        for fam in fams:
            if fam.language in ("fil", "mixed"):
                for tpl in fam.templates:
                    assert tpl in listed
    for svc in book.service_names.values():
        for name in svc["fil"]:
            assert name in listed
    for forms in book.variants.values():
        for phrase in forms["fil"]:
            assert phrase in listed
    for word in NOISE.SMS_FIL:
        assert word in listed


def test_the_phrasebook_marks_filipino_for_review():
    text = (ROOT / "training" / "phrasebook.yaml").read_text(encoding="utf-8")
    assert "NEEDS-NATIVE-REVIEW" in text
    assert "NEEDS-NATIVE-REVIEW" in (ROOT / "training" / "noise.py").read_text(encoding="utf-8")


# ---- output files and the sample --------------------------------------------------------------


def test_write_dataset_and_docs(ds, tmp_path):
    written = G.write_dataset(ds, tmp_path / "out")
    assert {p.name for p in written} == {
        f"{s}{m}.jsonl" for s in SPLITS for m in ("", ".meta")
    }
    import json

    for split in SPLITS:
        rows = [json.loads(x) for x in (tmp_path / "out" / f"{split}.jsonl").read_text(
            encoding="utf-8").splitlines()]
        assert len(rows) == len(ds.examples[split])
        assert all(list(r) == ["messages"] for r in rows)
        assert all(validate_cypher(r["messages"][2]["content"]).ok for r in rows[:300])
    docs = G.write_docs(ds, tmp_path / "docs")
    assert {p.name for p in docs} == {"sample.jsonl", "sample.meta.jsonl", "DATASET_CARD.md"}


def test_the_sample_is_about_sixty_examples_and_covers_everything(ds):
    sample = G.pick_sample(ds)
    assert 55 <= len(sample) <= 75
    assert {(e.slots.intent, e.shape) for e in sample} == {
        (i, s) for (i, s, f) in T.TEMPLATES if not f
    }
    assert {e.slots.language for e in sample} == set(LANGUAGES)
    assert {e.noise for e in sample} == set(NOISE.NOISE_LEVELS)
    assert {e.split for e in sample} == set(SPLITS)


def test_the_committed_sample_is_valid_chat_data():
    import json

    path = ROOT / "training" / "sample" / "sample.jsonl"
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
    assert 55 <= len(rows) <= 75
    for row in rows:
        roles = [m["role"] for m in row["messages"]]
        assert roles == ["system", "user", "assistant"]
        assert validate_cypher(row["messages"][2]["content"]).ok
    meta = (ROOT / "training" / "sample" / "sample.meta.jsonl").read_text(encoding="utf-8")
    assert len(meta.splitlines()) == len(rows)


def test_the_dataset_card_reports_counts(ds):
    card = G.dataset_card(ds)
    for needle in ("By intent", "By language", "By noise level", "train", "validation",
                   "test_synthetic", str(len(ds.examples["train"]))):
        assert needle in card
    by_intent = defaultdict(int)
    for e in everything(ds):
        by_intent[e.slots.intent] += 1
    for intent, n in by_intent.items():
        assert re.search(rf"\| {intent} \|.*\| {n} \|", card)


def test_the_committed_card_exists_and_says_how_to_regenerate():
    card = (ROOT / "training" / "DATASET_CARD.md").read_text(encoding="utf-8")
    assert "python -m training.generate_dataset" in card
    assert "By intent" in card


def test_command_line_writes_everything(tmp_path):
    rc = G.main(["--seed", "0", "--out", str(tmp_path / "o"), "--docs-dir", str(tmp_path / "d")])
    assert rc == 0
    assert (tmp_path / "o" / "train.jsonl").is_file()
    assert (tmp_path / "d" / "DATASET_CARD.md").is_file()
    rc = G.main(["--no-docs", "--out", str(tmp_path / "o2")])
    assert rc == 0 and not (tmp_path / "o2" / "DATASET_CARD.md").exists()
