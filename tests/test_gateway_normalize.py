"""Text primitives and the normalizer: folding, SMS and Taglish expansion, conservative typo
repair (prefer "unknown" over a wrong service)."""

from __future__ import annotations

import pytest

from citizengraph.gateway.pipeline import default_gateway
from citizengraph.gateway.text import fold, scripts_in, tokenize


@pytest.fixture(scope="module")
def normalize():
    return default_gateway().normalizer


# ------------------------------------------------------------------------------ fold, tokenize


@pytest.mark.parametrize(
    ("raw", "folded"),
    [
        ("Business PERMIT", "business permit"),
        ("Mayor’s Permit", "mayors permit"),
        ("mayor`s permit", "mayors permit"),
        ("ｂｕｓｉｎｅｓｓ", "business"),  # fullwidth
        ("café", "cafe"),
        ("Niño", "nino"),
        ("zero\u200bwidth", "zerowidth"),
        ("tab\tand\nnewline", "tab and newline"),
        ("bell\x07char", "bellchar"),
        ("ﬁle", "file"),  # ligature
        ("", ""),
    ],
)
def test_fold(raw, folded):
    assert fold(raw) == folded


@pytest.mark.parametrize(
    ("folded", "tokens"),
    [
        ("business permit", ["business", "permit"]),
        (
            "fees, business permit & cockfight permit!",
            ["fees", ",", "business", "permit", "&", "cockfight", "permit", "!"],
        ),
        ("pleaseeee help", ["please", "help"]),
        ("hellooo", ["hello"]),
        ("good", ["good"]),  # a double letter stays
        ("i-delete it", ["i", "delete", "it"]),
        ("mag-apply", ["mag", "apply"]),
        ("b.p.l.o. office", ["bplo", "office"]),
        ("3c fee", ["3c", "fee"]),
        ("a/b", ["a", "/", "b"]),
        ("wait...what", ["wait", ".", ".", ".", "what"]),
        ("ñandú 💥 here", ["nandu", "here"]),  # accents fold; symbols become separators
        ("日本語 permit", ["permit"]),  # letters outside Latin become separators
        ("", []),
    ],
)
def test_tokenize(folded, tokens):
    assert tokenize(fold(folded)) == tokens


def test_scripts():
    assert scripts_in("pay") == {"LATIN"}
    assert scripts_in("pаy") == {"LATIN", "CYRILLIC"}
    assert scripts_in("123") == set()


# -------------------------------------------------------------------- SMS and Taglish table


@pytest.mark.parametrize(
    ("raw", "cleaned"),
    [
        ("pls send reqs", "please send requirements"),
        ("wat r the fes", "what are the fees"),
        ("hw much for cert", "how much for certificate"),
        ("docs for brgy clearance", "documents for barangay clearance"),
        ("ur office", "your office"),
        ("nid info abt reg", "need information about registration"),
        ("mgkano po", "magkano po"),
        ("pano mag apply", "paano mag apply"),
        ("kelangan ba", "kailangan ba"),
        ("pde ba", "pwede ba"),
        ("bisnes permit", "business permit"),
        ("lisensiya sa negosyo", "lisensya sa negosyo"),
        ("sertifiko ng kasal", "sertipiko ng kasal"),
        ("REQS", "requirements"),
    ],
)
def test_sms_and_taglish_expansion(normalize, raw, cleaned):
    assert normalize(raw).cleaned == cleaned


# ------------------------------------------------------------------------------- typo repair


@pytest.mark.parametrize(
    ("typo", "fixed"),
    [
        ("bussines", "business"),
        ("buisness", "business"),
        ("bussiness", "business"),
        ("permt", "permit"),
        ("permitt", "permit"),
        ("requirments", "requirements"),
        ("requiremnts", "requirements"),
        ("occupatonal", "occupational"),
        ("ocupational", "occupational"),
        ("certifcate", "certificate"),
        ("certificat", "certificate"),
        ("registraton", "registration"),
        ("regstration", "registration"),
        ("delyed", "delayed"),
        ("delaed", "delayed"),
        ("sanitry", "sanitary"),
        ("cockfigt", "cockfight"),
        ("pharmcy", "pharmacy"),
        ("employement", "employment"),
        ("liscense", "license"),
        ("registeration", "registration"),
        ("kapanganakn", "kapanganakan"),
        ("pagpaparehistro", "pagpaparehistro"),
    ],
)
def test_common_typos_are_repaired(normalize, typo, fixed):
    assert normalize(typo).cleaned == fixed


def test_repairs_are_recorded_and_flagged(normalize):
    result = normalize("bussines permt")
    assert result.repairs == [("bussines", "business"), ("permt", "permit")]
    assert [t.repaired for t in result.tokens] == [True, True]
    assert result.tokens[0].original == "bussines" and result.tokens[0].known
    assert result.cleaned == "business permit"


@pytest.mark.parametrize(
    "word",
    [
        "carriage",  # one letter from "marriage", but a real word the lexicon knows
        "berth", "dearth", "feel", "feet", "cost", "costs", "partner", "permission",
        "passport", "property", "insert", "deposit", "hospital",
    ],
)  # fmt: skip
def test_real_words_are_never_repaired(normalize, word):
    assert normalize(word).cleaned == word
    assert not normalize(word).repairs


@pytest.mark.parametrize(
    "word",
    [
        "xyz",
        "abc",
        "fee",  # shorter than 5 letters: never repaired
        "b1rth5",
        "p3rmit",  # digits: never repaired
        "magtanong",  # two substitutions from "magsabong": a different word, left alone
        "qwertyu",
        "qxzvkj",
    ],
)
def test_words_that_should_stay_unknown_stay(normalize, word):
    assert normalize(word).cleaned == word


@pytest.mark.parametrize(
    ("typo", "stays"),
    [
        ("marige", "marige"),  # 2 edits from "marriage" but only 6 letters: too risky
        ("brth", "brth"),  # 4 letters
        ("deth", "deth"),
    ],
)
def test_short_words_are_left_alone_even_when_a_service_word_is_near(normalize, typo, stays):
    assert normalize(typo).cleaned == stays


def test_equally_close_words_mean_no_repair(normalize):
    # "medicl" is one edit from both "medical" and "medico": unknown beats a wrong guess
    assert normalize("medicl").cleaned == "medicl"
    assert not normalize("medicl").tokens[0].known


def test_a_repair_never_turns_one_service_into_another(normalize):
    for phrase in ("birth", "death", "marriage", "timely", "delayed", "sanitary", "dental"):
        assert normalize(phrase).cleaned == phrase


@pytest.mark.parametrize(
    ("joined", "split"),
    [("businesspermit", "business permit"), ("occupationalpermit", "occupational permit")],
)
def test_run_together_words_are_split_when_both_halves_are_known(normalize, joined, split):
    assert normalize(joined).cleaned == split


def test_unknown_words_are_flagged_not_dropped(normalize):
    result = normalize("fees for blorptastic permit")
    assert result.cleaned == "fees for blorptastic permit"
    assert [t.known for t in result.tokens] == [True, True, False, True]
    assert result.unknown_ratio() == pytest.approx(0.25)


def test_token_offsets_point_into_the_cleaned_text(normalize):
    result = normalize("Fees,  for   BUSINESS permit!")
    for tok in result.tokens:
        assert result.cleaned[tok.start : tok.end] == tok.text


def test_numbers_count_as_known(normalize):
    assert normalize("3c 2c 1000").unknown_ratio() == 0.0


def test_normalizing_twice_changes_nothing(normalize):
    for text in ("bussines permt requirments", "PLEASEEE help pls", "Mayor’s permit & fees"):
        once = normalize(text).cleaned
        assert normalize(once).cleaned == once


def test_normalizer_is_deterministic_across_instances():
    from citizengraph.gateway import Gateway

    text = "bussines permt requirments for occupatonal permit and cockfigt permt"
    assert Gateway().normalizer(text).cleaned == default_gateway().normalizer(text).cleaned
