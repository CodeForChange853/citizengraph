"""Duration parser: charter processing-time cells (docs/charter_data.md section 3)."""

import pytest

from citizengraph.parsing.durations import Duration, DurationComponent, parse_duration


def comps(text: str) -> list[tuple[float, float, str]]:
    d = parse_duration(text)
    return [(c.value_min, c.value_max, c.unit) for c in d.components]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2 minutes", [(2, 2, "minute")]),
        ("1 minute", [(1, 1, "minute")]),
        ("25mins", [(25, 25, "minute")]),
        ("37 mins (under normal condition)", [(37, 37, "minute")]),
        ("3 hours", [(3, 3, "hour")]),
        ("1 hour", [(1, 1, "hour")]),
        ("2 hours", [(2, 2, "hour")]),
        ("10 days", [(10, 10, "day")]),
    ],
)
def test_single_component(text, expected):
    assert comps(text) == expected
    assert parse_duration(text).status == "stated"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("5-10 minutes", [(5, 10, "minute")]),
        ("5 - 10 minutes", [(5, 10, "minute")]),
        ("3- 5 minutes", [(3, 5, "minute")]),
        ("3-5 minutes", [(3, 5, "minute")]),
        ("7 - 10 days", [(7, 10, "day")]),
        ("7-10 days", [(7, 10, "day")]),
        ("7 to 10 days", [(7, 10, "day")]),
    ],
)
def test_ranges(text, expected):
    assert comps(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1 hour and 6 minutes", [(1, 1, "hour"), (6, 6, "minute")]),
        (" 1 hour and 6 minutes (under normal conditions)", [(1, 1, "hour"), (6, 6, "minute")]),
        ("10 days, 33 minutes", [(10, 10, "day"), (33, 33, "minute")]),
        ("10 days and 28 minutes", [(10, 10, "day"), (28, 28, "minute")]),
        ("1 hours, 14 minutes", [(1, 1, "hour"), (14, 14, "minute")]),
        ("1 hour, 14 minutes", [(1, 1, "hour"), (14, 14, "minute")]),
        ("22 hours, 51 minutes", [(22, 22, "hour"), (51, 51, "minute")]),
        (
            "10 days, 1 hours, 54 minutes",
            [(10, 10, "day"), (1, 1, "hour"), (54, 54, "minute")],
        ),
        ("7-10 days, 26 minutes", [(7, 10, "day"), (26, 26, "minute")]),
    ],
)
def test_combinations(text, expected):
    assert comps(text) == expected


@pytest.mark.parametrize("text", ["- - -", "- - - ", "---", "-", "", "   ", None])
def test_not_stated(text):
    d = parse_duration(text)
    assert d.status == "not_stated"
    assert d.components == ()
    assert d.minutes_min is None and d.minutes_max is None


@pytest.mark.parametrize(
    "text", ["as soon as possible", "1 hour - 2 hours", "5 fortnights", "ten minutes"]
)
def test_unparsed_is_flagged_not_guessed(text):
    d = parse_duration(text)
    assert d.status == "unparsed"
    assert d.components == ()
    assert d.raw == text


def test_day_type_is_always_unknown():
    assert parse_duration("10 days").day_type == "unknown"
    assert parse_duration("7 - 10 days").day_type == "unknown"
    assert parse_duration("5 minutes").day_type == "unknown"
    assert parse_duration("- - -").day_type == "unknown"


def test_derived_minutes_hours_and_range():
    d = parse_duration("1 hour and 6 minutes")
    assert (d.minutes_min, d.minutes_max) == (66, 66)
    d = parse_duration("5 - 10 minutes")
    assert (d.minutes_min, d.minutes_max) == (5, 10)


def test_derived_minutes_days_are_calendar_equivalent_for_benchmarking_only():
    d = parse_duration("7 - 10 days")
    assert (d.minutes_min, d.minutes_max) == (7 * 1440, 10 * 1440)


def test_axes_are_kept_apart_for_validation():
    d = parse_duration("7-10 days, 26 minutes")
    assert (d.days_min, d.days_max) == (7, 10)
    assert (d.clock_minutes_min, d.clock_minutes_max) == (26, 26)
    d = parse_duration("22 hours, 51 minutes")
    assert (d.days_min, d.days_max) == (0, 0)
    assert (d.clock_minutes_min, d.clock_minutes_max) == (22 * 60 + 51, 22 * 60 + 51)


def test_to_dict_is_yaml_friendly():
    d = parse_duration("10 days, 33 minutes").to_dict()
    assert d["status"] == "stated"
    assert d["day_type"] == "unknown"
    assert d["components"][0] == {"value_min": 10, "value_max": 10, "unit": "day"}
    assert d["minutes_min"] == 10 * 1440 + 33


def test_types():
    assert isinstance(parse_duration("2 minutes"), Duration)
    assert isinstance(parse_duration("2 minutes").components[0], DurationComponent)


# ------------------------------------------------------------------- health / social welfare


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("10 min", [(10, 10, "minute")]),
        ("2 mins", [(2, 2, "minute")]),
        ("5 min ", [(5, 5, "minute")]),
        ("30 min/s", [(30, 30, "minute")]),
        ("10 min/s", [(10, 10, "minute")]),
        ("3 days", [(3, 3, "day")]),
        ("2-3 days", [(2, 3, "day")]),
        ("1 week", [(1, 1, "week")]),
        ("2 weeks", [(2, 2, "week")]),
        ("1 hour (Once a month)", [(1, 1, "hour")]),
        ("1 hour 30 min", [(1, 1, "hour"), (30, 30, "minute")]),
        (
            "1 week, 1 hour, 40 minutes",
            [(1, 1, "week"), (1, 1, "hour"), (40, 40, "minute")],
        ),
    ],
)
def test_health_and_social_welfare_forms(text, expected):
    assert comps(text) == expected
    assert parse_duration(text).status == "stated"


def test_weeks_are_their_own_axis_and_never_become_days():
    d = parse_duration("1 week, 1 hour, 40 minutes")
    assert (d.weeks_min, d.weeks_max) == (1, 1)
    assert (d.days_min, d.days_max) == (0, 0)
    assert (d.clock_minutes_min, d.clock_minutes_max) == (100, 100)
    assert d.day_type == "unknown"
    # benchmark-only derived minutes count a week as 7 x 1,440 minutes
    assert d.minutes_max == 7 * 1440 + 100


def test_known_typo_is_read_but_recorded():
    d = parse_duration("3 dsys")
    assert d.status == "stated"
    assert comps("3 dsys") == [(3, 3, "day")]
    assert d.normalizations == ("dsys -> day",)
    assert d.to_dict()["normalizations"] == ["dsys -> day"]


def test_clean_input_has_no_normalizations_or_review_keys():
    d = parse_duration("3 days").to_dict()
    assert "normalizations" not in d and "review" not in d


@pytest.mark.parametrize("text", ["1.15  min", "1.15 min", "1.5 hours", "0.5 days"])
def test_decimals_are_ambiguous_kept_raw_with_review_flag(text):
    d = parse_duration(text)
    assert d.status == "ambiguous"
    assert d.components == ()
    assert d.minutes_min is None and d.minutes_max is None
    assert d.raw == text
    assert d.review and "decimal" in d.review
    assert d.to_dict()["review"] == d.review


def test_other_typos_are_not_guessed():
    assert parse_duration("3 daysz").status == "unparsed"
    assert parse_duration("3 dazs").status == "unparsed"
