"""Fee parser: charter fee cells (docs/charter_data.md section 3)."""

import pytest

from citizengraph.parsing.fees import parse_fees


def items(text):
    return [
        (i.label, i.amount_min, i.amount_max, i.unit, i.qualifier) for i in parse_fees(text).items
    ]


@pytest.mark.parametrize("text", ["none", "None", " none ", "NONE"])
def test_none(text):
    f = parse_fees(text)
    assert f.status == "none"
    assert f.items == ()


@pytest.mark.parametrize("text", ["- - -", "- - - ", "---", "", None, "   "])
def test_not_stated(text):
    f = parse_fees(text)
    assert f.status == "not_stated"
    assert f.items == ()


def test_none_with_parenthetical_note_keeps_note():
    f = parse_fees("none (private courier fees will apply)")
    assert f.status == "none"
    assert f.notes == ("private courier fees will apply",)
    f = parse_fees("none (option for private courier)")
    assert f.status == "none"
    assert f.notes == ("option for private courier",)


@pytest.mark.parametrize(
    ("text", "amount"),
    [("₱200.00", 200.0), ("₱25.00", 25.0), ("₱235.50", 235.5), ("₱1,000.00", 1000.0)],
)
def test_single_amount(text, amount):
    f = parse_fees(text)
    assert f.status == "amounts"
    assert items(text) == [(None, amount, amount, None, None)]


@pytest.mark.parametrize(
    ("text", "lo", "hi"),
    [
        ("₱1,000.00 - ₱3,000.00", 1000.0, 3000.0),
        ("₱255.00 - ₱295.00", 255.0, 295.0),
        ("₱255.00 to ₱295.00", 255.0, 295.0),
        ("₱255.00–₱295.00", 255.0, 295.0),
    ],
)
def test_range(text, lo, hi):
    assert items(text) == [(None, lo, hi, None, None)]


def test_per_copy():
    assert items("₱20.00 per copy") == [(None, 20.0, 20.0, "per copy", None)]


def test_per_unit_slash():
    got = items("MD - ₱1,000 / cock \nDerby - ₱1,500 / cock")
    assert got == [
        ("MD", 1000.0, 1000.0, "per cock", None),
        ("Derby", 1500.0, 1500.0, "per cock", None),
    ]


def test_cockfight_tiers_without_units():
    got = items("2C - ₱3,000\n3C - ₱4,500\n4C - ₱6,000\n5C - ₱7,500")
    assert [(g[0], g[1]) for g in got] == [
        ("2C", 3000.0),
        ("3C", 4500.0),
        ("4C", 6000.0),
        ("5C", 7500.0),
    ]


def test_multi_item_cell_with_labels_before_amount_and_note():
    text = (
        "Zoning - ₱30.00\nSanitary Services - ₱100.00\n"
        "Business Name Clearance -₱5.50\nSignboard - ₱100.00"
    )
    f = parse_fees(text)
    assert [(i.label, i.amount_max) for i in f.items] == [
        ("Zoning", 30.0),
        ("Sanitary Services", 100.0),
        ("Business Name Clearance", 5.5),
        ("Signboard", 100.0),
    ]


def test_label_after_amount_and_fixed():
    f = parse_fees("₱200.00 / fixed \n₱50.00 - garbage fee\n*ALL FEES MUST BE SETTLED AT THE CTO*")
    assert [(i.label, i.amount_max, i.unit) for i in f.items] == [
        (None, 200.0, None),
        ("garbage fee", 50.0, None),
    ]
    assert f.items[0].note == "fixed"
    assert f.notes == ("ALL FEES MUST BE SETTLED AT THE CTO",)


def test_qualifier_lines_inherit_previous_label():
    text = (
        "Police Clearance - ₱25.00\nMedical Health - ₱30.00 \nMayor’s Permit Fee - ₱40.00\n"
        "Occupational Tax - ₱120.00 (company)\n₱215.00 (individual)\n"
        "*ALL FEES MUST BE SETTLED AT THE CTO*"
    )
    f = parse_fees(text)
    assert [(i.label, i.amount_max, i.qualifier) for i in f.items] == [
        ("Police Clearance", 25.0, None),
        ("Medical Health", 30.0, None),
        ("Mayor’s Permit Fee", 40.0, None),
        ("Occupational Tax", 120.0, "company"),
        ("Occupational Tax", 215.0, "individual"),
    ]


def test_total_with_only_qualifiers():
    f = parse_fees("₱215.00 (company)\n₱310.00 (individual)")
    assert [(i.label, i.amount_max, i.qualifier) for i in f.items] == [
        (None, 215.0, "company"),
        (None, 310.0, "individual"),
    ]


def test_wrapped_label_lines_are_joined():
    text = "a. Annulment/Legal separation\n- ₱500.00\nh. Emancipation of Minor -\n₱200.00"
    f = parse_fees(text)
    assert [(i.label, i.amount_max) for i in f.items] == [
        ("Annulment/Legal separation", 500.0),
        ("Emancipation of Minor", 200.0),
    ]


def test_text_only_fee_is_not_invented():
    f = parse_fees("As determined by the CSWMO")
    assert f.status == "text_only"
    assert f.items == ()
    assert f.notes == ("As determined by the CSWMO",)


def test_settle_at_cto_note_alone_is_not_a_fee():
    f = parse_fees("*ALL FEES MUST BE SETTLED AT THE CTO*")
    assert f.status == "not_stated"
    assert f.notes == ("ALL FEES MUST BE SETTLED AT THE CTO",)


def test_to_dict_is_yaml_friendly():
    d = parse_fees("₱20.00 per copy").to_dict()
    assert d["status"] == "amounts"
    assert d["items"] == [
        {
            "label": None,
            "amount_min": 20.0,
            "amount_max": 20.0,
            "unit": "per copy",
            "qualifier": None,
            "note": None,
        }
    ]
    assert d["raw"] == "₱20.00 per copy"


def test_settle_at_cto_note_without_asterisks_is_still_a_note():
    f = parse_fees("ALL FEES MUST BE SETTLED AT THE CTO")
    assert f.status == "not_stated"
    assert f.notes == ("ALL FEES MUST BE SETTLED AT THE CTO",)


# ------------------------------------------------------------------- health / social welfare


@pytest.mark.parametrize("text", ["None", "None ", "none\n"])
def test_capitalised_none_with_trailing_space(text):
    assert parse_fees(text).status == "none"


def test_bare_number_is_an_amount_with_a_no_currency_note():
    f = parse_fees("250")
    assert f.status == "amounts"
    assert [(i.amount_min, i.amount_max, i.note) for i in f.items] == [
        (250, 250, "no currency sign in source")
    ]
    assert parse_fees("1,250.50").items[0].amount_max == 1250.5


@pytest.mark.parametrize("text", ["P30.00", "₱30.00", "Php 30.00", "PHP30"])
def test_peso_forms(text):
    f = parse_fees(text)
    assert [(i.amount_min, i.amount_max, i.note) for i in f.items] == [(30, 30, None)]


def test_bare_number_only_when_the_whole_cell_is_a_number():
    assert parse_fees("250 per session").status == "text_only"
    assert parse_fees("1 copy").status == "text_only"
