"""Alias linker, intent detector, variant catalog and splitter, tested below the pipeline."""

from __future__ import annotations

from itertools import pairwise

import pytest

from citizengraph.gateway.intents import VariantCatalog
from citizengraph.gateway.pipeline import default_gateway
from citizengraph.gateway.splitter import split
from citizengraph.gateway.types import Draft

BP, OP, CP = "business_permit", "occupational_permit", "cockfight_permit"
BTIM, BDEL, TRANS = (
    "birth_registration_timely",
    "birth_registration_delayed",
    "certified_transcription",
)


@pytest.fixture(scope="module")
def gw():
    return default_gateway()


def link(gw, text):
    norm = gw.normalizer(text)
    return norm, gw.linker.link(norm)


def span_text(norm, mention):
    return " ".join(t.text for t in norm.tokens[mention.start : mention.end])


# --------------------------------------------------------------------------------- linker

EXACT = [
    ("business permit", BP, "business permit"),
    ("the BUSINESS PERMIT please", BP, "business permit"),
    ("mayor's permit", BP, "mayors permit"),
    ("occupational permit", OP, "occupational permit"),
    ("lisensya sa negosyo", BP, "lisensya sa negosyo"),
    ("permit sa sabong", CP, "permit sa sabong"),
    ("delayed birth registration", BDEL, "delayed birth registration"),
    ("timely birth registration", BTIM, "timely birth registration"),
    ("certified transcription", TRANS, "certified transcription"),
    ("ausf", "ausf_registration", "ausf"),
    ("sanitary permit", "cho_sanitary_permit", "sanitary permit"),
]


@pytest.mark.parametrize(("text", "target", "span"), EXACT, ids=lambda v: str(v)[:30])
def test_exact_phrase_matches_carry_a_span_and_a_score(gw, text, target, span):
    norm, mentions = link(gw, text)
    assert len(mentions) == 1
    m = mentions[0]
    assert m.targets == [target] and not m.ambiguous
    assert span_text(norm, m) == span
    assert m.best.method == "exact" and m.best.confidence == 1.0
    assert 0.8 <= m.best.score <= 1.0


def test_name_beats_everyday_in_score(gw):
    _, (name,) = link(gw, "business permit")
    _, (everyday,) = link(gw, "start a business")
    assert name.best.kind == "name" and everyday.best.kind == "everyday"
    assert name.best.score > everyday.best.score


TOKEN_SET = [
    ("certificate of birth registration", {BTIM, BDEL}),
    ("permit for occupational", {OP}),
    ("registration of delayed birth", {BDEL}),
    ("certified", None),  # one word of a two-word alias: not enough
]


@pytest.mark.parametrize(("text", "targets"), TOKEN_SET, ids=lambda v: str(v)[:30])
def test_reordered_words_match_as_a_token_set(gw, text, targets):
    _, mentions = link(gw, text)
    if targets is None:
        assert mentions == []
    else:
        assert {t for m in mentions for t in m.targets} == targets


def test_token_set_never_bridges_a_joining_word(gw):
    # "death" and "certificate" are two words apart but split by "and": not "death certificate"
    _, mentions = link(gw, "birth certificate and death registration")
    assert {t for m in mentions for t in m.targets} >= {BTIM}
    assert all("cho_death_certificate" not in m.targets for m in mentions)


def test_phrase_level_fuzzy_catches_what_word_repair_cannot(gw):
    _, mentions = link(gw, "medicl certificate for employment")
    (m,) = mentions
    assert m.targets == ["cho_medical_certificate"]
    assert m.best.method == "fuzzy" and m.best.confidence < 0.9


def test_the_whole_text_is_scanned(gw):
    filler = "lorem ipsum dolor sit amet " * 30
    _, mentions = link(gw, filler + "cockfight permit " + filler)
    assert [m.targets for m in mentions] == [[CP]]


def test_longer_alias_dominates_a_shorter_one_of_another_service(gw):
    _, (m,) = link(gw, "delayed birth registration")
    assert m.targets == [BDEL]  # the timely service's "birth registration" sits inside it
    _, (m,) = link(gw, "business permit")
    assert m.targets == [BP]  # bare "permit" of six other services sits inside it


def test_equal_phrases_of_different_services_are_ambiguous(gw):
    _, (m,) = link(gw, "birth certificate")
    assert m.ambiguous and set(m.targets) == {BTIM, BDEL, TRANS}
    scores = {c.score for c in m.candidates}
    assert len(scores) == 1  # same phrase, same kind, same weight


def test_ambiguity_margin_is_respected(gw):
    # "certified copy of birth certificate" (synonym) beats the everyday "birth certificate"
    _, (m,) = link(gw, "certified copy of birth certificate")
    assert m.targets == [TRANS]


def test_office_mentions_are_not_services(gw):
    _, mentions = link(gw, "bplo")
    assert mentions[0].is_office and mentions[0].targets == ["bplo"]
    _, mentions = link(gw, "city health office and civil registry")
    assert [m.targets for m in mentions] == [["cho"], ["lcro"]]


def test_a_single_office_narrows_a_shared_phrase(gw):
    _, mentions = link(gw, "death certificate city health office")
    service = next(m for m in mentions if not m.is_office)
    assert service.targets == ["cho_death_certificate"] and service.resolved_by == "office"


def test_two_offices_do_not_narrow(gw):
    _, mentions = link(gw, "death certificate civil registry or city health office")
    service = next(m for m in mentions if not m.is_office)
    assert len(service.targets) > 1 and service.resolved_by is None


def test_cue_words_narrow_ambiguity(gw):
    _, (m,) = link(gw, "birth certificate but it is late")
    assert m.targets == [BDEL] and m.resolved_by == "cue"


def test_cues_do_not_leak_between_mentions(gw):
    _, mentions = link(gw, "birth certificate and late death registration")
    birth = mentions[0]
    assert len(birth.targets) > 1  # "late" belongs to the death mention


def test_cue_winner_needs_exactly_one(gw):
    assert gw.linker.cue_winner(["it", "is", "late"], [BTIM, BDEL, TRANS]) == BDEL
    assert gw.linker.cue_winner(["nothing"], [BTIM, BDEL]) is None
    assert gw.linker.cue_winner(["late", "timely"], [BTIM, BDEL]) is None


@pytest.mark.parametrize(
    "text",
    ["how is the weather", "asdf qwer", "passport renewal", "hello there", "", "fees fees fees"],
)
def test_unrelated_text_links_to_nothing(gw, text):
    assert link(gw, text)[1] == []


def test_mentions_are_in_text_order_and_do_not_overlap(gw):
    _, mentions = link(gw, "fees for fishing permit, sanitary permit & dental services")
    starts = [m.start for m in mentions]
    assert starts == sorted(starts)
    assert all(a.end <= b.start for a, b in pairwise(mentions))


def test_linking_is_deterministic(gw):
    text = "birth certificate and permit and bussines permt " * 3
    first = [(m.start, m.end, m.targets) for m in link(gw, text)[1]]
    for _ in range(3):
        assert [(m.start, m.end, m.targets) for m in link(gw, text)[1]] == first


# ------------------------------------------------------------------------------- intents

INTENT_CASES = [
    # requirements
    ("requirements for x", "requirements"), ("what documents do i need", "requirements"),
    ("what do i need to bring", "requirements"), ("checklist", "requirements"),
    ("ano ang kailangan", "requirements"), ("mga dokumento", "requirements"),
    ("ano ang dadalhin", "requirements"),
    # fees
    ("how much", "fees"), ("what is the fee", "fees"), ("cost", "fees"), ("price list", "fees"),
    ("magkano", "fees"), ("magkano po", "fees"), ("ano ang bayad", "fees"), ("presyo", "fees"),
    # steps
    ("what are the steps", "steps"), ("how to apply", "steps"), ("procedure", "steps"),
    ("paano", "steps"), ("anong proseso", "steps"), ("hakbang", "steps"),
    ("what is the process", "steps"),
    # processing time
    ("how long", "processing_time"), ("how many days", "processing_time"),
    ("processing time", "processing_time"), ("gaano katagal", "processing_time"),
    ("ilang araw", "processing_time"), ("matagal ba", "processing_time"),
    ("how long is the process", "processing_time"),
    # where to secure
    ("where can i get", "where_to_secure"), ("where to secure", "where_to_secure"),
    ("saan kukuha", "where_to_secure"), ("saan makakakuha", "where_to_secure"),
    # who may avail
    ("who can apply", "who_may_avail"), ("eligibility", "who_may_avail"),
    ("who is eligible", "who_may_avail"), ("sino ang pwede", "who_may_avail"),
    ("pwede ba ako", "who_may_avail"),
    # office
    ("which office", "office"), ("where do i apply", "office"), ("office address", "office"),
    ("saan mag apply", "office"), ("saan pupunta", "office"), ("nasaan ang opisina", "office"),
    # status
    ("status", "status"), ("where is my application", "status"), ("any update", "status"),
    ("asa na", "status"), ("nasaan na", "status"), ("kumusta na", "status"),
    ("matagal na", "status"), ("track my permit", "status"),
]  # fmt: skip


@pytest.mark.parametrize(("text", "intent"), INTENT_CASES, ids=lambda v: str(v)[:30])
def test_intent_phrases(gw, text, intent):
    hits = gw.detector.detect(gw.normalizer(text))
    assert list(dict.fromkeys(h.intent for h in hits)) == [intent]


def test_no_intent_words_no_intent(gw):
    for text in ("business permit", "birth certificate", "hello", "asdf"):
        assert gw.detector.detect(gw.normalizer(text)) == []


def test_several_intents_come_back_in_text_order(gw):
    hits = gw.detector.detect(gw.normalizer("fees and requirements and how long"))
    assert [h.intent for h in hits] == ["fees", "requirements", "processing_time"]


def test_intent_words_inside_a_service_name_do_not_count(gw):
    norm = gw.normalizer("breqs processing")
    mentions = gw.linker.link(norm)
    assert gw.detector.detect(norm, mentions) == []


def test_weak_steps_word_yields_to_a_time_phrase(gw):
    norm = gw.normalizer("how long is the processing")
    assert [h.intent for h in gw.detector.detect(norm)] == ["processing_time"]


def test_where_is_my_is_status_not_office(gw):
    assert gw.detector.detect(gw.normalizer("where is the office"))[0].intent == "office"
    assert gw.detector.detect(gw.normalizer("where is my permit"))[0].intent == "status"


# ------------------------------------------------------------------------------ variants


def test_catalog_lists_only_dimensions_the_service_uses(gw):
    catalog = gw.catalog
    assert set(catalog.dimensions(BP)) == {"applicant_type", "business_type"}
    assert catalog.dimensions(BP)["business_type"] == {
        "association",
        "corporation",
        "single_proprietor",
    }
    assert set(catalog.dimensions(OP)) == {"taxpayer"}
    assert set(catalog.dimensions(CP)) == {"cockfight_category"}
    assert set(catalog.dimensions(BDEL)) == {"birth_status", "foreign_parent"}
    assert set(catalog.dimensions(BTIM)) == {"birth_status"}
    assert catalog.dimensions("cho_dental_services") == {}
    assert catalog.dimensions("no_such_service") == {}


def test_catalog_values_exist_in_the_graph_variants(gw):
    known = {(v.dimension, v.value) for v in gw.graph.seed.variants}
    for sid in (s.id for s in gw.graph.services()):
        for dimension, values in gw.catalog.dimensions(sid).items():
            assert all((dimension, v) in known for v in values)


def test_resolve_keeps_only_supported_single_values(gw):
    cat: VariantCatalog = gw.catalog
    assert cat.resolve(OP, [("taxpayer", "company")], []) == ({"taxpayer": "company"}, [])
    assert cat.resolve(OP, [("taxpayer", "company"), ("taxpayer", "individual")], [])[1] == [
        "variant_conflict:taxpayer"
    ]
    assert cat.resolve(OP, [("cockfight_category", "MD")], []) == ({}, [])
    assert cat.resolve(BP, [("applicant_type", "new")], [("applicant_type", "renewal")]) == (
        {},
        ["variant_unavailable:applicant_type=renewal", "variant_conflict:applicant_type"],
    )
    assert cat.resolve("cho_dental_services", [], [("applicant_type", "renewal")]) == ({}, [])


@pytest.mark.parametrize(
    ("text", "cues"),
    [
        ("one parent is a foreigner", [("foreign_parent", "yes")]),
        ("illegitimate child", [("birth_status", "non_marital")]),
        ("the parents are not married", [("birth_status", "non_marital")]),
        ("hindi kasal ang magulang", [("birth_status", "non_marital")]),
        ("kasal ang magulang", [("birth_status", "marital")]),
        ("corporation", [("business_type", "corporation")]),
        ("for individual", [("taxpayer", "individual")]),
        ("derby", [("cockfight_category", "Derby")]),
        ("3c", [("cockfight_category", "3C")]),
        ("bagong negosyo", [("applicant_type", "new")]),
    ],
)
def test_variant_cues(gw, text, cues):
    supported, _ = gw.detector.variant_cues(gw.normalizer(text))
    assert sorted({(d, v) for _, d, v in supported}) == sorted(cues)


def test_unsupported_cues_are_kept_apart(gw):
    supported, unsupported = gw.detector.variant_cues(gw.normalizer("renewal for a cooperative"))
    assert supported == []
    assert {(d, v) for _, d, v in unsupported} == {
        ("applicant_type", "renewal"), ("business_type", "cooperative"),
    }  # fmt: skip


# ------------------------------------------------------------------------------- splitter


def drafts_for(gw, text, language="en") -> tuple[list[Draft], list[str]]:
    norm = gw.normalizer(text)
    mentions = gw.linker.link(norm)
    intents = gw.detector.detect(norm, mentions)
    cues, unsupported = gw.detector.variant_cues(norm)
    return split(norm, mentions, intents, cues, unsupported, gw.lexicon, gw.cfg, language, False)


def summary(drafts):
    return [(d.service_id or tuple(d.candidates), d.intent) for d in drafts]


JOINERS = [
    "fees for business permit and occupational permit",
    "fees for business permit at occupational permit",
    "fees for business permit saka occupational permit",
    "fees for business permit tsaka occupational permit",
    "fees for business permit tapos occupational permit",
    "fees for business permit, occupational permit",
    "fees for business permit & occupational permit",
    "fees for business permit + occupational permit",
    "fees for business permit / occupational permit",
    "fees for business permit plus occupational permit",
    "fees for business permit pati occupational permit",
    "fees for business permit or occupational permit",
    "fees for business permit; occupational permit",
    "fees for business permit and also occupational permit",
    "fees for business permit, and occupational permit",
]


@pytest.mark.parametrize("text", JOINERS, ids=lambda v: v[24:])
def test_every_joiner_splits_and_carries_the_shared_intent(gw, text):
    drafts, reasons = drafts_for(gw, text)
    assert summary(drafts) == [(BP, "fees"), (OP, "fees")]
    assert "multi_request" in reasons


def test_three_services_each_get_their_own_part(gw):
    drafts, _ = drafts_for(
        gw,
        "fees for business permit, requirements for cockfight permit and how long for fishing permit",
    )
    assert summary(drafts) == [
        (BP, "fees"),
        (CP, "requirements"),
        ("fishing_permit", "processing_time"),
    ]


def test_parts_have_their_own_phrase(gw):
    drafts, _ = drafts_for(gw, "fees for business permit and requirements for cockfight permit")
    assert drafts[0].phrase == "fees for business permit"
    assert drafts[1].phrase == "requirements for cockfight permit"


def test_cues_stay_with_their_part(gw):
    drafts, _ = drafts_for(
        gw, "business permit for corporation and occupational permit for individual fees"
    )
    assert drafts[0].cues == [("business_type", "corporation")]
    assert drafts[1].cues == [("taxpayer", "individual")]


def test_several_intents_in_one_part_make_several_drafts(gw):
    drafts, _ = drafts_for(gw, "fees and requirements and steps for business permit")
    assert summary(drafts) == [(BP, "fees"), (BP, "requirements"), (BP, "steps")]


def test_a_part_without_intent_takes_the_nearest_ones(gw):
    drafts, _ = drafts_for(gw, "business permit and cockfight permit and fishing permit fees")
    assert [d.intent for d in drafts] == ["fees", "fees", "fees"]
    drafts, _ = drafts_for(
        gw, "requirements for business permit, cockfight permit. fees for fishing permit"
    )
    assert [d.intent for d in drafts] == ["requirements", "requirements", "fees"]


def test_no_intent_anywhere_leaves_it_open(gw):
    drafts, _ = drafts_for(gw, "business permit and cockfight permit")
    assert [d.intent for d in drafts] == [None, None]


def test_office_mentions_never_split_a_message(gw):
    drafts, reasons = drafts_for(gw, "fees for business permit at bplo")
    assert summary(drafts) == [(BP, "fees")] and "multi_request" not in reasons


def test_loosely_joined_mentions_become_one_request(gw):
    # "change of first name in birth certificate": one request, the clear service wins
    drafts, reasons = drafts_for(gw, "requirements for business permit for a new business")
    assert len(drafts) == 1 and "merged_adjacent_mentions" in reasons
    assert drafts[0].cues == [("applicant_type", "new")]
    drafts, _ = drafts_for(gw, "requirements change of first name in birth certificate")
    assert summary(drafts) == [("LCRO-15", "requirements")]


def test_a_clear_mention_that_says_more_replaces_the_vaguer_one_next_to_it(gw):
    for text in ("fees for birth certificate newborn", "fees for newborn birth certificate"):
        drafts, reasons = drafts_for(gw, text)
        assert summary(drafts) == [(BTIM, "fees")] and "merged_adjacent_mentions" in reasons


def test_unsplit_ambiguity_is_kept_as_candidates(gw):
    (draft,), _ = drafts_for(gw, "fees for birth certificate")
    assert draft.service_id is None and set(draft.candidates) == {BTIM, BDEL, TRANS}


def test_low_confidence_is_noted_on_the_draft(gw):
    (draft,), _ = drafts_for(gw, "fees for medicl certificate for employment")
    assert draft.low_confidence
    (draft,), _ = drafts_for(gw, "fees for business permit")
    assert not draft.low_confidence


def test_no_service_no_drafts(gw):
    assert drafts_for(gw, "how much is it") == ([], [])
