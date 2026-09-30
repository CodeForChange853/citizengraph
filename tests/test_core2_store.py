"""Workflow store, role roster, alert store and Core 2 config."""

from datetime import date, datetime

import pytest

from citizengraph.core2.calendar import PHT
from citizengraph.core2.config import Core2Config, load_core2_config, load_statutory_caps
from citizengraph.core2.models import Application, StepEntry
from citizengraph.core2.store import Alert, AlertStore, WorkflowStore


def app(app_id="A1", ref="CG-SIM-0001", citizen="CIT-0001", service="business_permit"):
    return Application(
        app_id=app_id,
        ref=ref,
        citizen_ref=citizen,
        service_id=service,
        submitted_at=datetime(2026, 3, 2, 9, 0, tzinfo=PHT),
        entries=[
            StepEntry(step_id=f"{service}-S01", entered_at=datetime(2026, 3, 2, 9, 0, tzinfo=PHT))
        ],
    )


class TestConfig:
    def test_shipped_config_loads_with_documented_defaults(self):
        cfg = load_core2_config()
        assert cfg.max_steps == 8
        assert cfg.invalid_json_retries == 1
        assert cfg.minor_delay_ratio > 1
        assert cfg.day_type_overrides == {}
        assert "birth_registration_delayed-S04" in cfg.posting_step_ids
        assert cfg.weekend_days == frozenset({5, 6})

    def test_statutory_caps_are_read_from_sla_yaml_and_marked_unverified(self):
        caps = load_statutory_caps()
        assert caps.working_days == {"SIMPLE": 3, "COMPLEX": 7, "HIGHLY_TECHNICAL": 20}
        assert caps.basis == "statutory_cap_unverified"

    def test_missing_file_fails_closed_to_defaults_not_to_guesses(self, tmp_path):
        cfg = load_core2_config(tmp_path / "nope.yaml")
        assert cfg == Core2Config()
        assert cfg.max_steps == 8

    @pytest.mark.parametrize(
        "text",
        [
            "core2: {max_steps: 0}",
            "core2: {max_steps: 'eight'}",
            "core2: {minor_delay_ratio: 0.5}",
            "core2: {day_type_overrides: {x: maybe}}",
            "core2: {weekend_days: [7]}",
            "core2: {row_limit: 0}",
        ],
    )
    def test_invalid_values_are_rejected(self, tmp_path, text):
        p = tmp_path / "c.yaml"
        p.write_text(text, encoding="utf-8")
        with pytest.raises(ValueError):
            load_core2_config(p)


class TestWorkflowStore:
    def test_lookup_by_id_by_reference_and_by_citizen(self):
        s = WorkflowStore()
        s.add(app("A1", "CG-1", "CIT-1"))
        s.add(app("A2", "CG-2", "CIT-1"))
        s.add(app("A3", "CG-3", "CIT-2"))
        assert s.get("A1").ref == "CG-1"
        assert s.get("nope") is None
        assert [a.app_id for a in s.find("CIT-1")] == ["A1", "A2"]
        assert [a.app_id for a in s.find("CG-3")] == ["A3"]
        assert s.find("unknown") == []

    def test_duplicate_ids_are_rejected(self):
        s = WorkflowStore()
        s.add(app("A1"))
        with pytest.raises(ValueError):
            s.add(app("A1", "CG-9"))

    def test_roles_have_an_absence_roster(self):
        s = WorkflowStore()
        s.set_absent("BPLO Chief", date(2026, 3, 4), "on leave (simulated)")
        assert s.absence("BPLO Chief", date(2026, 3, 4)) == "on leave (simulated)"
        assert s.absence("BPLO Chief", date(2026, 3, 5)) is None
        assert s.absence("Someone Else", date(2026, 3, 4)) is None

    def test_json_round_trip(self):
        s = WorkflowStore()
        s.add(app("A1"))
        s.set_absent("BPLO Chief", date(2026, 3, 4), "x")
        again = WorkflowStore.from_json(s.to_json())
        assert again.get("A1") == s.get("A1")
        assert again.absence("BPLO Chief", date(2026, 3, 4)) == "x"

    def test_reference_codes_must_look_simulated(self):
        with pytest.raises(ValueError):
            Application(
                app_id="A1",
                ref="real person 09171234567",
                citizen_ref="CIT-1",
                service_id="s",
                submitted_at=datetime(2026, 3, 2, tzinfo=PHT),
            )


class TestAlertStore:
    def alert(self, kind="citizen_delay_notice", app_id="A1"):
        return Alert(
            alert_id=f"AL-{app_id}-{kind}",
            app_id=app_id,
            kind=kind,
            audience="citizen",
            text_en="en",
            text_fil="fil",
            created_at=datetime(2026, 3, 4, 10, 0, tzinfo=PHT),
        )

    def test_append_and_read_back_in_memory(self):
        s = AlertStore()
        assert s.add(self.alert()) is True
        assert [a.kind for a in s.all()] == ["citizen_delay_notice"]

    def test_same_app_and_kind_is_not_stored_twice(self):
        s = AlertStore()
        assert s.add(self.alert()) is True
        assert s.add(self.alert()) is False
        assert len(s.all()) == 1

    def test_jsonl_file_is_the_only_thing_written(self, tmp_path):
        p = tmp_path / "sub" / "alerts.jsonl"
        s = AlertStore(p)
        s.add(self.alert())
        s.add(self.alert("missing_data_flag"))
        assert len(p.read_text(encoding="utf-8").splitlines()) == 2
        again = AlertStore(p)  # survives a restart
        assert {a.kind for a in again.all()} == {"citizen_delay_notice", "missing_data_flag"}
        assert again.add(self.alert()) is False

    def test_unknown_kind_is_rejected(self):
        with pytest.raises(ValueError):
            self.alert("shout_at_staff")


def test_default_store_paths_come_from_the_config(tmp_path):
    from citizengraph.core2.config import resolve_path

    cfg = Core2Config(alert_store=str(tmp_path / "a.jsonl"))
    store = AlertStore.from_config(cfg)
    assert store.all() == []
    assert resolve_path("data/simulated/x.jsonl").is_absolute()
    assert resolve_path(str(tmp_path)) == tmp_path
    assert not resolve_path(Core2Config().alert_store).exists()  # tests never write it
