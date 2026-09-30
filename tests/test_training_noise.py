"""Noise injection: deterministic, leveled, and it never destroys what it cannot repair."""

from __future__ import annotations

import random
import re
import string

import pytest
from test_training_common import load

N = load("noise")

TEXT = "what are the requirements for a business permit and how much is the fee"
FIL = "ano ang mga requirements para sa business permit at magkano ang bayad"


def rng(seed=1):
    return random.Random(seed)


def test_levels_are_zero_ten_and_thirty():
    assert N.NOISE_LEVELS == (0, 10, 30)


def test_level_zero_is_the_identity_and_uses_no_randomness():
    r = rng()
    state = r.getstate()
    assert N.add_noise(TEXT, 0, r) == TEXT
    assert r.getstate() == state


def test_same_seed_same_output():
    assert N.add_noise(TEXT, 30, rng(5)) == N.add_noise(TEXT, 30, rng(5))
    outs = {N.add_noise(TEXT, 30, rng(s)) for s in range(20)}
    assert len(outs) > 10


def test_noise_keeps_the_word_count_and_never_empties_a_word():
    for seed in range(200):
        out = N.add_noise(TEXT, 30, rng(seed))
        assert len(out.split()) == len(TEXT.split())
        assert all(w for w in out.split())
        assert "\n" not in out


def test_noise_changes_about_the_requested_share_of_words():
    def changed_share(level):
        changed = total = 0
        for seed in range(400):
            out = N.add_noise(FIL, level, rng(seed)).lower().split()
            for a, b in zip(FIL.split(), out, strict=True):
                total += 1
                changed += a != b
        return changed / total

    low, high = changed_share(10), changed_share(30)
    assert 0.05 < low < 0.15
    assert 0.2 < high < 0.4
    assert low < high


def test_words_with_digits_and_ids_are_left_alone():
    text = "fees for the 2C cockfight $sid 3rd time 100"
    for seed in range(100):
        out = N.add_noise(text, 30, rng(seed)).lower().split()
        for original in ("2c", "$sid", "3rd", "100"):
            assert original in out


def test_punctuation_around_words_is_kept():
    for seed in range(100):
        out = N.add_noise("magkano ang bayad?", 30, rng(seed))
        assert out.endswith("?")


def test_each_operation_changes_a_word_and_stays_plausible():
    r = rng(3)
    assert N.keyboard_typo("permit", r) != "permit"
    assert len(N.keyboard_typo("permit", r)) == 6
    assert N.drop_vowel("requirements", r) != "requirements"
    assert len(N.drop_vowel("requirements", r)) < len("requirements")
    assert N.double_letter("fee", r) != "fee"
    assert len(N.double_letter("fee", r)) == 4
    assert N.swap_ck("clerk", r) in {"klerk", "clerc"}
    assert N.swap_ph_f("phone", r) == "fone"
    assert N.swap_ph_f("fee", r) == "phee"
    assert N.sms_spelling("please", r) == "pls"
    assert N.sms_spelling("zzz", r) == "zzz"  # not in the table: unchanged


def test_operations_that_do_not_apply_return_the_word_unchanged():
    r = rng()
    assert N.swap_ph_f("tax", r) == "tax"
    assert N.drop_vowel("tv", r) == "tv"
    assert N.swap_ck("tax", r) == "tax"


def test_keyboard_typo_uses_adjacent_keys_only():
    for seed in range(200):
        out = N.keyboard_typo("a", rng(seed))
        assert out in N.KEYBOARD_NEIGHBOURS["a"]
    for letter, near in N.KEYBOARD_NEIGHBOURS.items():
        assert letter in string.ascii_lowercase
        assert letter not in near and near <= set(string.ascii_lowercase)


def test_casing_noise_is_a_property_of_the_whole_message():
    outs = {N.add_noise(TEXT, 30, rng(s)) for s in range(300)}
    assert any(o == o.upper() for o in outs) or any(re.search(r"[A-Z]", o) for o in outs)
    assert any(o != o.lower() for o in outs)


def test_noise_does_not_touch_the_clean_phrase_object():
    clean = "business permit"
    N.add_noise(clean, 30, rng())
    assert clean == "business permit"


@pytest.mark.parametrize("level", [0, 10, 30, 10.5, 100])
def test_any_percentage_is_accepted(level):
    assert isinstance(N.add_noise(TEXT, level, rng()), str)


@pytest.mark.parametrize("level", [-1, 101, "10", None, True])
def test_anything_else_is_rejected(level):
    with pytest.raises(ValueError):
        N.add_noise(TEXT, level, rng())
