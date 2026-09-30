"""Gateway settings from config/limits.yaml (gateway: section only)."""

from __future__ import annotations

import pytest
import yaml

from citizengraph.gateway import Gateway, SessionState
from citizengraph.gateway.config import (
    DEFAULT_LIMITS_PATH,
    GatewayConfig,
    GatewayConfigError,
    config_from_mapping,
    load_config,
)


def test_the_repo_file_has_the_documented_thresholds():
    cfg = load_config()
    assert cfg.max_chars == 500 and cfg.hard_max_chars == 2000
    assert cfg.rate_limit_per_minute == 10
    assert cfg == GatewayConfig(**cfg.__dict__)  # round-trips
    assert cfg.default_intent is None
    # LCRO-06 requirements look copied from marriage registration (CLAUDE.md): held back until the LGU confirms
    assert cfg.withheld_services == ("death_registration_timely",)


def test_every_key_of_the_section_is_a_known_setting_and_vice_versa():
    section = yaml.safe_load(DEFAULT_LIMITS_PATH.read_text(encoding="utf-8"))["gateway"]
    assert set(section) == set(GatewayConfig.__dataclass_fields__)


def test_other_sections_of_the_file_are_left_alone():
    doc = yaml.safe_load(DEFAULT_LIMITS_PATH.read_text(encoding="utf-8"))
    assert doc["core1"]["cypher_limit_max"] == 50 and doc["core1"]["cypher_max_chars"] == 2000
    assert doc["prompt"]["context_tokens"] == 2048 and doc["core2"]["max_steps"] == 8


def test_missing_file_or_section_means_defaults(tmp_path):
    assert load_config(tmp_path / "nope.yaml") == GatewayConfig()
    (tmp_path / "x.yaml").write_text("core1: {}\n", encoding="utf-8")
    assert load_config(tmp_path / "x.yaml") == GatewayConfig()


def test_values_are_read_and_typed(tmp_path):
    (tmp_path / "x.yaml").write_text(
        "gateway:\n  max_chars: 100\n  hard_max_chars: 300\n  gibberish_threshold: 1\n"
        "  withheld_services: [a, b]\n  default_intent: fees\n",
        encoding="utf-8",
    )
    cfg = load_config(tmp_path / "x.yaml")
    assert (cfg.max_chars, cfg.hard_max_chars) == (100, 300)
    assert cfg.gibberish_threshold == 1.0 and isinstance(cfg.gibberish_threshold, float)
    assert cfg.withheld_services == ("a", "b") and cfg.default_intent == "fees"


@pytest.mark.parametrize(
    "raw",
    [
        {"max_chars": "500"},
        {"max_chars": True},
        {"max_chars": 0},
        {"max_chars": 900, "hard_max_chars": 800},
        {"rate_limit_per_minute": 0},
        {"repeat_limit": 0},
        {"gibberish_threshold": 1.5},
        {"link_min_score": -0.1},
        {"max_sub_requests": 0},
        {"withheld_services": "business_permit"},
        {"withheld_services": [1]},
        {"default_intent": "dance"},
        {"default_intent": 3},
        {"surprise": 1},
    ],
)
def test_bad_values_are_rejected_loudly(raw):
    with pytest.raises(GatewayConfigError):
        config_from_mapping(raw)


def test_unreadable_or_malformed_files_are_rejected(tmp_path):
    (tmp_path / "bad.yaml").write_text("gateway: [unclosed", encoding="utf-8")
    with pytest.raises(GatewayConfigError):
        load_config(tmp_path / "bad.yaml")
    (tmp_path / "list.yaml").write_text("gateway: [1, 2]\n", encoding="utf-8")
    with pytest.raises(GatewayConfigError):
        load_config(tmp_path / "list.yaml")


def test_default_intent_can_be_switched_on():
    cfg = GatewayConfig(default_intent="requirements")
    result = Gateway(config=cfg).process("business permit", SessionState(), 1.0)
    assert result.status == "ok"
    assert [(s.service_id, s.intent) for s in result.sub_requests] == [
        ("business_permit", "requirements")
    ]
    assert "default_intent" in result.reasons


def test_thresholds_change_behaviour():
    tight = Gateway(config=GatewayConfig(max_chars=40, hard_max_chars=60))
    message = "please tell me the requirements for the business permit"  # 55 characters
    assert tight.process(message, SessionState(), 1.0).status == "echo_confirm"
    assert tight.process(message + " thank you", SessionState(), 1.0).reasons == ["too_long"]
    strict = Gateway(config=GatewayConfig(link_min_score=0.99))
    assert strict.process("requirements for mayors permit", SessionState(), 1.0).status != "ok"
