"""graph/seed/aliases.yaml and its loader: complete for all 40 services and the four offices,
every Filipino row marked for review, and every kind of mistake reported (all at once)."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from citizengraph.gateway.aliases import AliasError, load_aliases, parse_aliases
from citizengraph.graph import DEFAULT_SEED_DIR, InMemoryGraph

NOT_IN_GRAPH = {
    "BPLO-03", "BPLO-06", "LCRO-03", "LCRO-05", "LCRO-07", "LCRO-08", "LCRO-10", "LCRO-12",
    "LCRO-15", "LCRO-16", "LCRO-17", "CHO-04", "CHO-05", "CHO-06",
}  # fmt: skip
OFFICES = {"bplo", "lcro", "cho", "cswdo"}


@pytest.fixture(scope="module")
def graph():
    return InMemoryGraph.from_dir()


@pytest.fixture(scope="module")
def table(graph):
    return load_aliases(graph=graph)


# ------------------------------------------------------------------ the real table


def test_forty_services_26_in_the_graph_and_14_not(table, graph):
    assert len(table.services) == 40
    in_graph = {sid for sid, e in table.services.items() if e.in_graph}
    assert len(in_graph) == 26 and in_graph == {s.id for s in graph.services()}
    assert {sid for sid, e in table.services.items() if not e.in_graph} == NOT_IN_GRAPH


def test_registry_matches_the_graph_charter_refs_and_offices(table, graph):
    for s in graph.services():
        entry = table.services[s.id]
        assert (entry.charter_ref, entry.office_id) == (s.charter_ref, s.office_id)


def test_services_not_in_the_graph_carry_a_charter_name_and_their_charter_ref_as_id(table):
    for sid in NOT_IN_GRAPH:
        entry = table.services[sid]
        assert entry.charter_ref == sid and entry.name
        assert not entry.in_graph


def test_the_charter_counts_per_office(table):
    per_office: dict[str, int] = {}
    for entry in table.services.values():
        per_office[entry.office_id] = per_office.get(entry.office_id, 0) + 1
    assert per_office == {"bplo": 7, "lcro": 17, "cswdo": 1, "cho": 15}


def test_every_service_has_english_and_filipino_names_and_everyday_phrases(table):
    missing: list[str] = []
    for sid in table.services:
        rows = table.for_target(sid)
        for lang in ("en", "fil"):
            for kind in ("name", "everyday"):
                if not any(a.kind == kind and a.lang == lang for a in rows):
                    missing.append(f"{sid}: no {lang} {kind}")
    assert not missing, missing


def test_every_office_is_covered_including_the_abbreviations(table):
    assert table.office_ids == OFFICES
    wanted = {
        "bplo": {"bplo", "business permits and licensing office"},
        "lcro": {"lcro", "ccro", "civil registry", "civil registry office"},
        "cho": {"cho", "city health office"},
        "cswdo": {"cswdo", "social welfare"},
    }
    for office, texts in wanted.items():
        have = {a.text.lower() for a in table.for_target(office)}
        assert texts <= have, (office, texts - have)
        assert {a.lang for a in table.for_target(office)} == {"en", "fil"}
        assert any(a.kind == "abbreviation" for a in table.for_target(office))


def test_every_filipino_row_is_marked_for_review_and_english_rows_are_not(table):
    assert table.aliases
    for a in table.aliases:
        assert a.needs_native_review == (a.lang == "fil"), a
    assert {a.lang for a in table.aliases} == {"en", "fil"}  # no Waray


def test_raw_file_marks_filipino_rows_explicitly():
    raw = yaml.safe_load((DEFAULT_SEED_DIR / "aliases.yaml").read_text(encoding="utf-8"))
    assert raw["version"] == 1
    for row in raw["aliases"]:
        assert row["kind"] in {"name", "synonym", "abbreviation", "everyday"}
        assert ("needs_native_review" in row) == (row["lang"] == "fil")
        assert row["text"].strip()


def test_no_charter_staff_names_or_fee_amounts_in_aliases(table):
    banned = ("php", "₱", "peso", "pesos")
    assert not [a.text for a in table.aliases if any(b in a.text.lower() for b in banned)]


def test_the_table_is_data_only_nothing_in_it_is_invented_charter_content(table):
    # names of services not in the graph are the charter's own (docs/charter_data.md)
    assert table.services["LCRO-03"].name == "Application for Marriage License"
    assert table.services["CHO-06"].name == "Laboratory Services"


# ---------------------------------------------------------------- validation, all at once


def tiny(**changes):
    raw = {
        "version": 1,
        "services": [
            {"id": "svc_a", "charter_ref": "T-01", "office_id": "o1", "in_graph": True},
            {"id": "T-02", "charter_ref": "T-02", "office_id": "o1", "in_graph": False,
             "name": "Second Service"},
        ],
        "aliases": [
            {"target": "svc_a", "lang": "en", "text": "first service", "kind": "name"},
            {"target": "svc_a", "lang": "fil", "text": "unang serbisyo", "kind": "name",
             "needs_native_review": True},
            {"target": "T-02", "lang": "en", "text": "second service", "kind": "name"},
            {"target": "o1", "lang": "en", "text": "the office", "kind": "name"},
        ],
    }  # fmt: skip
    raw.update(changes)
    return raw


GRAPH = {"svc_a": ("T-01", "o1")}


def parse(raw):
    return parse_aliases(raw, office_ids=["o1"], graph_services=GRAPH)


def codes(raw) -> set[str]:
    with pytest.raises(AliasError) as err:
        parse(raw)
    return {i.code for i in err.value.issues}


def test_a_valid_table_parses():
    result = parse(tiny())
    assert set(result.services) == {"svc_a", "T-02"} and len(result.aliases) == 4
    assert result.is_office("o1") and not result.is_office("svc_a")


def mutate(fn):
    raw = copy.deepcopy(tiny())
    fn(raw)
    return raw


def _add_service_not_in_graph(raw):
    raw["services"].append(
        {"id": "svc_b", "charter_ref": "T-09", "office_id": "o1", "in_graph": True}
    )


def _duplicate_first_alias(raw):
    raw["aliases"].append(dict(raw["aliases"][0], text="First  Service!"))


BAD = [
    ("unknown_target", lambda r: r["aliases"][0].update(target="nowhere")),
    ("empty_text", lambda r: r["aliases"][0].update(text="   ")),
    ("empty_text", lambda r: r["aliases"][0].update(text="?!...")),
    ("empty_text", lambda r: r["aliases"][0].pop("text")),
    ("bad_lang", lambda r: r["aliases"][0].update(lang="waray")),
    ("bad_kind", lambda r: r["aliases"][0].update(kind="slang")),
    ("missing_review_mark", lambda r: r["aliases"][1].pop("needs_native_review")),
    ("schema", lambda r: r["aliases"][0].update(needs_native_review=True)),
    ("duplicate_alias", _duplicate_first_alias),
    ("duplicate_service", lambda r: r["services"].append(dict(r["services"][0]))),
    ("unknown_office", lambda r: r["services"][0].update(office_id="zzz")),
    ("unknown_service", _add_service_not_in_graph),
    ("graph_mismatch", lambda r: r["services"][0].update(charter_ref="T-77")),
    ("graph_mismatch", lambda r: r["services"][0].update(office_id="o2")),
    ("missing_service", lambda r: r["services"].pop(0)),
]


@pytest.mark.parametrize(("code", "change"), BAD, ids=[f"{c}-{i}" for i, (c, _) in enumerate(BAD)])
def test_each_kind_of_mistake_is_reported(code, change):
    assert code in codes(mutate(change))


def test_a_service_not_in_the_graph_needs_a_name():
    raw = mutate(lambda r: r["services"][1].pop("name"))
    assert "schema" in codes(raw)


def test_in_graph_false_for_a_graph_service_is_a_mismatch():
    raw = mutate(lambda r: r["services"][0].update(in_graph=False, name="x"))
    assert "graph_mismatch" in codes(raw)


def test_duplicate_charter_refs_are_reported():
    raw = mutate(lambda r: r["services"][1].update(charter_ref="T-01"))
    assert "duplicate_service" in codes(raw)


def test_the_same_text_for_different_targets_is_allowed_on_purpose():
    raw = mutate(
        lambda r: r["aliases"].append(
            {"target": "T-02", "lang": "en", "text": "first service", "kind": "name"}
        )
    )
    assert len(parse(raw).aliases) == 5  # that is how "birth certificate" becomes a question


def test_every_problem_is_reported_in_one_go():
    raw = tiny()
    raw["aliases"][0]["target"] = "nowhere"
    raw["aliases"][2]["text"] = ""
    raw["aliases"][3]["lang"] = "waray"
    with pytest.raises(AliasError) as err:
        parse(raw)
    assert {i.code for i in err.value.issues} >= {"unknown_target", "empty_text", "bad_lang"}
    assert "3 problem(s)" in str(err.value)


@pytest.mark.parametrize("raw", [None, [], "x", {"services": []}, {"services": [], "aliases": 3}])
def test_a_table_of_the_wrong_shape_is_rejected(raw):
    with pytest.raises(AliasError):
        parse(raw)


def test_load_aliases_reports_unreadable_files(tmp_path: Path, graph):
    with pytest.raises(AliasError) as err:
        load_aliases(tmp_path / "missing.yaml", graph=graph)
    assert err.value.issues[0].code == "bad_yaml"
    broken = tmp_path / "broken.yaml"
    broken.write_text("services: [unclosed", encoding="utf-8")
    with pytest.raises(AliasError):
        load_aliases(broken, graph=graph)


def test_load_aliases_validates_a_copy_of_the_real_file_against_the_graph(tmp_path, graph):
    raw = yaml.safe_load((DEFAULT_SEED_DIR / "aliases.yaml").read_text(encoding="utf-8"))
    raw["services"] = [s for s in raw["services"] if s["id"] != "business_permit"]
    copy_path = tmp_path / "aliases.yaml"
    copy_path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    with pytest.raises(AliasError) as err:
        load_aliases(copy_path, graph=graph)
    assert {i.code for i in err.value.issues} >= {"missing_service", "unknown_target"}
