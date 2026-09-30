"""The redesigned training data (session 5b): valid, deterministic, leak-free, and NOT a lookup
table. These tests build the FULL dataset (a few seconds) and need no GPU, model or network."""

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
from citizengraph.core1.output import check_completion, parse_completion
from citizengraph.core1.prompt import MAX_PHRASE_CHARS_V2, MAX_PROMPT_TOKENS
from citizengraph.core1.slots import LANGUAGES, check_variants
from citizengraph.graph import InMemoryGraph
from citizengraph.guardrail.validator import validate_cypher

G = load("generate_dataset")
C = load("cells")
P = load("phrasebook")
NOISE = load("noise")

SPLITS = G.SPLITS
TRAINED = ("train", "validation", "test_synthetic")
HELD_OUT = {"office_who", "compare_time"}


@pytest.fixture(scope="module")
def graph():
    return InMemoryGraph.from_dir()


@pytest.fixture(scope="module")
def book():
    return P.load_phrasebook()


@pytest.fixture(scope="module")
def ds():
    started = time.perf_counter()
    dataset = G.build_dataset(seed=0)
    assert time.perf_counter() - started < 60, "the full dataset must generate in under a minute"
    return dataset


def everything(ds):
    return ds.all()


# ---- the phrase books -------------------------------------------------------------------------


def test_the_phrasebooks_are_consistent(book, graph):
    assert P.check_phrasebook(book, graph, C.HELD_OUT_SHAPES) == []


def test_every_shape_has_families_in_every_language(book):
    for intent, shape, filtered in T.TEMPLATES:
        if filtered:
            continue
        for language in LANGUAGES:
            families = book.families[(intent, shape, language)]
            assert len(families) >= (1 if shape in HELD_OUT else 3), (intent, shape, language)


def test_there_are_at_least_ten_new_question_families_with_their_own_wording(book):
    new = {s for (_, s, _) in book.families} & set(T.NEW_SHAPES)
    assert len(new) >= 10
    for shape in new:
        for language in LANGUAGES:
            assert any(k[1] == shape and k[2] == language for k in book.families)


def test_placeholders_match_what_each_shape_needs(book):
    for (intent, shape, _), fams in book.families.items():
        want = P.expected_placeholders(T.TEMPLATES[(intent, shape, False)])
        for fam in fams:
            for tpl in fam.templates:
                assert sorted(re.findall(r"\{(\w+)\}", tpl)) == want, (fam.id, tpl)


def test_documents_occur_in_requirements_and_agencies_are_seed_agencies(book, graph):
    texts = [r.text.lower() for r in graph.seed.requirements]
    for doc in book.document_names:
        assert sum(doc in t for t in texts) >= 1, doc
    from citizengraph.graph.ids import slug

    agencies = {slug(r.secured_at) for r in graph.seed.requirements if r.secured_at}
    assert set(book.agency_names) <= agencies
    assert set(book.office_names) == {o.id for o in graph.seed.offices}


def test_a_broken_phrasebook_is_reported(book, graph):
    broken = P.Phrasebook(
        service_names={k: v for k, v in book.service_names.items() if k != "business_permit"},
        variants=book.variants,
        variant_frames=book.variant_frames,
        variant_joiners=book.variant_joiners,
        families={
            **book.families,
            ("office", "office_services", "en"): (
                P.Family(
                    "office.office_services.en.1",
                    "office",
                    "office_services",
                    "en",
                    ("x {service}",),
                ),
            ),
        },
        office_names=book.office_names,
        agency_names={**book.agency_names, "not-an-agency": {"en": ("x",), "fil": ("y",)}},
        document_names={**book.document_names, "zzz nothing": {"en": ("x",), "fil": ("y",)}},
    )
    problems = "; ".join(P.check_phrasebook(broken, graph, C.HELD_OUT_SHAPES))
    assert "business_permit" in problems
    assert "at least 3 families" in problems
    assert "must contain exactly" in problems
    assert "not-an-agency" in problems and "zzz nothing" in problems


def test_phrases_carry_no_digits_or_charter_numbers(book):
    for fams in book.families.values():
        for fam in fams:
            for template in fam.templates:
                assert not re.search(r"\d", re.sub(r"\{\w+\}", "", template)), template


def test_no_wording_belongs_to_two_intents_or_shapes(book):
    owner: dict[str, tuple[str, str]] = {}
    for (intent, shape, _), fams in book.families.items():
        for fam in fams:
            for template in fam.templates:
                key = " ".join(template.casefold().split())
                assert owner.setdefault(key, (intent, shape)) == (intent, shape), template


# ---- cells and coverage -----------------------------------------------------------------------


def test_only_curated_things_are_used(ds, graph, book):
    curated = {s.id for s in graph.seed.services}
    assert len(curated) == 26
    offices = {o.id for o in graph.seed.offices}
    for e in everything(ds):
        for t in e.request.targets:
            if t.kind == "service":
                assert t.id in curated
            elif t.kind == "office":
                assert t.id in offices
            elif t.kind == "agency":
                assert t.id in book.agency_names
            else:
                assert t.id in book.document_names
    used = {t.id for e in everything(ds) for t in e.request.targets if t.kind == "service"}
    assert used == curated


def test_every_shape_is_in_the_data_and_held_out_shapes_only_in_the_unseen_split(ds):
    every_shape = {(i, s) for (i, s, f) in T.TEMPLATES if not f}
    assert {(e.template_key.split("/")[0], e.shape) for e in everything(ds)} == every_shape
    for split in TRAINED:
        assert not {e.shape for e in ds.examples[split]} & HELD_OUT
    assert {e.shape for e in ds.examples["test_unseen_shape"]} == HELD_OUT
    assert set(ds.held_out) == HELD_OUT


def test_every_trained_shape_is_in_every_trained_split(ds):
    trained = {s for (_, s, f) in T.TEMPLATES if not f} - HELD_OUT
    for split in TRAINED:
        assert {e.shape for e in ds.examples[split]} == trained, split


def test_every_language_and_noise_level_is_in_every_split(ds):
    for split in SPLITS:
        rows = ds.examples[split]
        assert {e.language for e in rows} == set(LANGUAGES)
        assert {e.noise for e in rows} == set(NOISE.NOISE_LEVELS)


def test_status_never_appears(ds):
    assert all("status" not in e.intents for e in everything(ds))


def test_derived_shapes_exist_only_where_the_data_exists(ds, graph):
    for e in everything(ds):
        services = e.request.of_kind("service")
        if e.shape == "per_step":
            assert any(f.step_id for f in graph.fees(services[0]))
        if e.shape == "go_first":
            assert C.has_go_first_data(graph, services[0])
        if e.shape in ("fees_total", "fee_time"):
            assert graph.fees(services[0])
        if e.shape == "longest_step":
            assert any(st.duration.minutes_max is not None for st in graph.steps(services[0]))
        if e.shape == "external_steps":
            assert any(st.external_agency for st in graph.steps(services[0]))
        if e.shape == "cheapest":
            office = e.request.of_kind("office")[0]
            assert any(graph.fees(s.id) for s in graph.services(office))
        if e.shape == "doc_in_service":
            words = e.request.of_kind("document")[0]
            assert any(words in r.text.lower() for r in graph.requirements(services[0]))


def test_stated_variants_exist_in_the_seed(ds):
    for e in everything(ds):
        for vid in e.variant_ids:
            dimension, _, value = vid.partition(":")
            assert check_variants({dimension: value}) == []


# ---- the model's job is real: the output is NOT a function of the slots ------------------------


def test_there_are_many_distinct_gold_queries(ds):
    queries = {e.cypher for e in everything(ds)}
    assert len(queries) >= 30  # session 5 had 17
    assert len({e.completion for e in everything(ds)}) >= len(queries)
    train = {e.cypher for e in ds.examples["train"]}
    assert len(train) >= 28
    assert len({e.cypher for e in ds.examples["test_unseen_shape"]}) == 2


def test_the_same_service_with_different_phrasing_gives_different_intents(ds):
    by_service: dict[str, set[str]] = defaultdict(set)
    for e in everything(ds):
        for sid in e.request.of_kind("service")[:1]:
            by_service[sid].add(e.intent_header)
    assert len(by_service) == 26
    assert all(len(v) >= 5 for v in by_service.values())
    # one concrete case: the business permit is asked about in many different ways
    assert len(by_service["business_permit"]) >= 7
    same_prompt_slots = defaultdict(set)
    for e in ds.examples["train"]:
        same_prompt_slots[(e.targets_text, e.language)].add(e.completion)
    assert max(len(v) for v in same_prompt_slots.values()) >= 15


def test_the_slots_alone_cannot_predict_the_output(ds):
    ceiling = G.slots_only_ceiling(ds.examples["train"], ds.examples["test_synthetic"])
    assert ceiling < 0.35, ceiling
    ceiling_unseen = G.slots_only_ceiling(ds.examples["train"], ds.examples["test_unseen_shape"])
    assert ceiling_unseen == 0.0  # those shapes are not in train at all


def test_the_same_words_with_a_different_target_kind_are_a_different_question(ds):
    # "how many ..." style wording exists for services (steps/requirements) and for offices
    kinds_by_shape: dict[str, set[str]] = defaultdict(set)
    for e in everything(ds):
        kinds_by_shape[e.shape].add("+".join(t.kind for t in e.request.targets))
    assert {"service+office"} <= kinds_by_shape["count"] | kinds_by_shape["list"]
    assert "office" in kinds_by_shape["office_count"]
    assert "document" in kinds_by_shape["doc_services"]
    assert "agency" in kinds_by_shape["agency_services"]
    assert "service+service" in kinds_by_shape["compare_fees"]


def test_no_prompt_has_two_different_answers(ds):
    seen: dict[tuple, str] = {}
    for e in everything(ds):
        key = (e.targets_text, e.language, e.request.phrase)
        assert seen.setdefault(key, e.completion) == e.completion, key


def test_an_ambiguous_wording_is_labelled_as_both_intents(ds):
    both = [e for e in everything(ds) if e.intent_header == "fees+processing_time"]
    assert both
    assert any("magkano at gaano katagal" in e.request.phrase for e in both)
    for e in both:
        assert e.shape == "fee_time"


def test_variants_are_read_from_the_wording_only_for_shapes_that_can_filter(ds):
    filtered = [e for e in everything(ds) if e.variant_ids]
    assert len(filtered) > 300
    for e in filtered:
        assert T.supports_variants(e.template_key.split("/")[0], e.shape)
        assert e.template_key.endswith("/true")
    ignored = [e for e in everything(ds) if not e.variant_ids and e.shape in ("list", "count")]
    assert ignored


# ---- gold completions and prompts ------------------------------------------------------------


def test_every_gold_query_in_the_full_dataset_passes_the_guardrail(ds):
    checked = set()
    for e in everything(ds):
        if e.cypher in checked:
            continue
        checked.add(e.cypher)
        result = validate_cypher(e.cypher)
        assert result.ok, (e.id, result.reasons)


def test_every_gold_completion_parses_checks_out_and_is_canonical(ds):
    for e in everything(ds):
        parsed = parse_completion(e.completion)
        assert not parsed.problems and parsed.cypher == e.cypher
        checked = check_completion(e.completion, e.request)
        assert checked.ok and checked.canonical, (e.id, checked.problems)
        assert checked.params == e.params
        assert e.cypher == T.TEMPLATES[tuple(_key(e))].cypher


def _key(e):
    intent, shape, filtered = e.template_key.split("/")
    return (intent, shape, filtered == "true")


def test_gold_queries_never_contain_literal_ids(ds):
    for e in everything(ds):
        assert "'" not in e.cypher and '"' not in e.cypher
        for t in e.request.targets:
            assert t.id not in e.cypher


def test_the_prompt_does_not_give_the_answer_away(ds):
    for e in everything(ds):
        lines = e.user.splitlines()
        assert [ln.split(":")[0] for ln in lines] == ["language", "targets", "request"]
        assert "intent" not in e.user and "variants" not in e.user and "shape" not in e.user
        assert e.completion.splitlines()[0].startswith("intent: ")


def test_the_system_message_is_the_same_in_every_example(ds):
    assert len({e.system for e in everything(ds)}) == 1


def test_slots_given_prompts_differ_only_by_the_added_slots(ds):
    for e in everything(ds)[:800]:
        inferred, given = e.user.splitlines(), e.user_slots_given.splitlines()
        assert len(given) == len(inferred) + 2
        assert f"intent: {e.intent_header}" in given
        shown = ", ".join(v.replace(":", "=") for v in e.variant_ids) or "none"
        assert f"variants: {shown}" in given
        assert [ln for ln in given if not ln.startswith(("intent:", "variants:"))] == inferred


def test_prompts_are_well_under_the_budget(ds):
    worst = max(e.tokens for e in everything(ds))
    assert worst < MAX_PROMPT_TOKENS * 0.65, worst


def test_phrases_are_cleaned_like_the_gateway(ds):
    for e in everything(ds):
        phrase = e.request.phrase
        assert re.fullmatch(r"[a-z0-9]+( [a-z0-9]+)*", phrase), phrase
        assert len(phrase) <= MAX_PHRASE_CHARS_V2


def test_gateway_clean_matches_the_gateways_words():
    assert G.gateway_clean("Mayor's  Permit -- mag-apply!?") == "mayors permit mag apply"
    long = G.gateway_clean("word " * 100)
    assert (
        len(long) <= MAX_PHRASE_CHARS_V2 and long.startswith("word word") and not long.endswith(" ")
    )
    assert G.gateway_clean("Ñandú  café") == "nandu cafe"


def test_entity_words_are_not_damaged_by_noise(ds, book):
    # a document target's words survive in the phrase at every noise level (English examples)
    hits = total = 0
    for e in everything(ds):
        docs = e.request.of_kind("document")
        if docs and e.language == "en" and e.noise == 30:
            total += 1
            names = [n for n in book.document_names[docs[0]]["en"]]
            hits += any(
                re.sub(r"[^a-z0-9 ]", "", n.lower()).replace("an ", "").replace("a ", "", 1)
                in e.request.phrase
                or n.lower() in e.request.phrase
                for n in names
            )
    assert total > 5 and hits / total > 0.9


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
    for (_, shape, _), fams in book.families.items():
        counts = Counter(ds.family_split[f.id] for f in fams)
        if shape in HELD_OUT:
            assert counts == {"test_unseen_shape": len(fams)}
        else:
            assert counts["validation"] == 1 and counts["test_synthetic"] == 1
            assert counts["train"] == len(fams) - 2


def test_no_example_is_repeated_across_splits(ds):
    seen: dict[tuple, str] = {}
    for split in SPLITS:
        for e in ds.examples[split]:
            key = (e.targets_text, e.language, e.request.phrase)
            assert seen.setdefault(key, split) == split


def test_withheld_variant_combinations_never_reach_train(ds):
    assert ds.withheld
    withheld = {
        (sid, tuple(sorted(f"{d}:{v}" for d, v in c.items())))
        for sid, combos in ds.withheld.items()
        for c in combos
    }
    for e in ds.examples["train"]:
        sid = e.request.of_kind("service")
        assert not e.combo_withheld
        assert not sid or (sid[0], e.variant_ids) not in withheld
    held = [e for s in ("validation", "test_synthetic") for e in ds.examples[s] if e.combo_withheld]
    assert held


def test_train_is_the_bulk_and_the_evaluation_splits_are_not_tiny(ds):
    sizes = {s: len(ds.examples[s]) for s in SPLITS}
    assert sizes["train"] > 2 * sizes["validation"] > 0
    assert sizes["test_synthetic"] > 1000 and sizes["test_unseen_shape"] > 200


# ---- determinism ------------------------------------------------------------------------------


def test_same_seed_same_bytes(ds, tmp_path):
    again = G.build_dataset(seed=0)
    for split in SPLITS:
        assert G.jsonl(ds.examples[split]) == G.jsonl(again.examples[split])
        assert G.jsonl(ds.examples[split], meta=True) == G.jsonl(again.examples[split], meta=True)
        assert G.jsonl(ds.examples[split], slots_given=True) == G.jsonl(
            again.examples[split], slots_given=True
        )
    a, b = tmp_path / "a", tmp_path / "b"
    G.write_dataset(ds, a)
    G.write_dataset(again, b)
    for p in sorted(a.rglob("*.jsonl")):
        assert p.read_bytes() == (b / p.relative_to(a)).read_bytes()
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
    return out


def _allowed_names(graph, book) -> set[str]:
    """Names of things a question may mention: services, offices, agencies, documents, variants,
    and every alias the gateway knows (an alias is a name, not an answer)."""
    allowed = {_norm(s.name) for s in graph.seed.services} | {
        _norm(o.name) for o in graph.seed.offices
    }
    for table in (
        book.service_names,
        book.office_names,
        book.agency_names,
        book.document_names,
        book.variants,
    ):
        for forms in table.values():
            allowed.update(_norm(n) for names in forms.values() for n in names)
    allowed |= set(book.agency_names) | set(book.document_names)
    for langs in P.load_aliases(graph).values():
        for forms in langs.values():
            allowed.update(_norm(n) for n in forms)
    # the raw alias table too (every target, every kind, both languages)
    import yaml

    data = yaml.safe_load(P.ALIASES_PATH.read_text(encoding="utf-8"))
    allowed.update(_norm(a["text"]) for a in data["aliases"])
    return allowed


def test_no_example_contains_charter_answer_text(ds, graph, book):
    allowed = _allowed_names(graph, book)
    answers = {
        a
        for a in _answer_strings(graph)
        if len(a) >= 12 and not any(a.strip(" :.,()-") in ok for ok in allowed)
    }
    assert len(answers) > 100  # the check has something to look for
    for e in everything(ds):
        text = _norm(e.user + " " + e.completion + " " + e.raw_phrase)
        for a in answers:
            assert a not in text, (e.id, a)
    assert not [a for a in answers if a in _norm(everything(ds)[0].system)]


def test_alias_names_and_office_names_are_not_flagged_as_answers(graph, book):
    """Session 5 flagged "occupational tax" (an alias of a service) as charter answer text."""
    allowed = _allowed_names(graph, book)
    assert _norm("occupational tax") in allowed
    assert any("lcro" == a for a in allowed) and any("civil registry office" in a for a in allowed)


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
    for path in [
        *(ROOT / "training").glob("*.py"),
        *(ROOT / "src/citizengraph/core1").glob("*.py"),
    ]:
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
        text = _norm(e.user + " " + e.raw_phrase)
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
    for table in (book.service_names, book.office_names, book.agency_names, book.document_names):
        for forms in table.values():
            for name in forms["fil"]:
                assert name in listed
    for forms in book.variants.values():
        for phrase in forms["fil"]:
            assert phrase in listed
    for word in NOISE.SMS_FIL:
        assert word in listed


def test_the_phrasebooks_mark_filipino_for_review():
    for name in ("phrasebook.yaml", "phrasebook_shapes.yaml"):
        assert "NEEDS-NATIVE-REVIEW" in (ROOT / "training" / name).read_text(encoding="utf-8")
    assert "NEEDS-NATIVE-REVIEW" in (ROOT / "training" / "noise.py").read_text(encoding="utf-8")


# ---- output files and the sample --------------------------------------------------------------


def test_write_dataset_and_docs(ds, tmp_path):
    import json

    written = G.write_dataset(ds, tmp_path / "out")
    names = {str(p.relative_to(tmp_path / "out")) for p in written}
    assert names == (
        {f"{s}.jsonl" for s in SPLITS}
        | {f"{s}.meta.jsonl" for s in SPLITS}
        | {f"slots_given/{s}.jsonl" for s in SPLITS}
    )
    for split in SPLITS:
        rows = [
            json.loads(x)
            for x in (tmp_path / "out" / f"{split}.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        given = (tmp_path / "out" / "slots_given" / f"{split}.jsonl").read_text(encoding="utf-8")
        assert len(rows) == len(ds.examples[split]) == len(given.splitlines())
        assert all(list(r) == ["messages"] for r in rows)
        assert all(
            [m["role"] for m in r["messages"]] == ["system", "user", "assistant"] for r in rows
        )
        assert all(
            validate_cypher(parse_completion(r["messages"][2]["content"]).cypher).ok
            for r in rows[:300]
        )
    docs = G.write_docs(ds, tmp_path / "docs")
    assert {p.name for p in docs} == {"sample.jsonl", "sample.meta.jsonl", "DATASET_CARD.md"}


def test_the_sample_covers_everything(ds):
    sample = G.pick_sample(ds)
    assert 55 <= len(sample) <= 95
    assert {e.shape for e in sample} >= {s for (_, s, f) in T.TEMPLATES if not f}
    assert {e.language for e in sample} == set(LANGUAGES)
    assert {e.noise for e in sample} == set(NOISE.NOISE_LEVELS)
    assert {e.split for e in sample} == set(SPLITS)


def test_the_committed_sample_is_valid_chat_data():
    import json

    path = ROOT / "training" / "sample" / "sample.jsonl"
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
    assert 55 <= len(rows) <= 95
    for row in rows:
        roles = [m["role"] for m in row["messages"]]
        assert roles == ["system", "user", "assistant"]
        parsed = parse_completion(row["messages"][2]["content"])
        assert not parsed.problems and validate_cypher(parsed.cypher).ok
        assert "intent" not in row["messages"][1]["content"]
    meta = (ROOT / "training" / "sample" / "sample.meta.jsonl").read_text(encoding="utf-8")
    assert len(meta.splitlines()) == len(rows)


def test_the_dataset_card_reports_counts_and_is_honest(ds):
    card = G.dataset_card(ds)
    for needle in (
        "What the model must learn",
        "By intent",
        "By shape",
        "By language",
        "By noise level",
        "test_unseen_shape",
        "distinct gold queries",
        "Known limits",
        str(len(ds.examples["train"])),
    ):
        assert needle in card
    by_intent = defaultdict(int)
    for e in everything(ds):
        by_intent[e.intent_header] += 1
    for intent, n in by_intent.items():
        assert re.search(rf"\| {re.escape(intent)} \|.*\| {n} \|", card)


def test_the_committed_card_exists_and_says_how_to_regenerate():
    card = (ROOT / "training" / "DATASET_CARD.md").read_text(encoding="utf-8")
    assert "python -m training.generate_dataset" in card
    assert "What the model must learn" in card and "distinct gold queries" in card


def test_command_line_writes_everything(tmp_path):
    rc = G.main(["--seed", "0", "--out", str(tmp_path / "o"), "--docs-dir", str(tmp_path / "d")])
    assert rc == 0
    assert (tmp_path / "o" / "train.jsonl").is_file()
    assert (tmp_path / "o" / "slots_given" / "train.jsonl").is_file()
    assert (tmp_path / "d" / "DATASET_CARD.md").is_file()
    rc = G.main(["--no-docs", "--out", str(tmp_path / "o2")])
    assert rc == 0 and not (tmp_path / "o2" / "DATASET_CARD.md").exists()
