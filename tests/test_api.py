from fastapi.testclient import TestClient

from citizengraph.api.main import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json()["status"] == "ok"


def test_chat_answer_en():
    r = client.post("/chat", json={"message": "business permit", "lang": "en"})
    body = r.json()
    assert r.status_code == 200
    assert body["kind"] == "answer"
    assert body["sections"][0]["checklist"]
    assert body["meta"]["mock"] is True


def test_chat_clarify_fil():
    r = client.post("/chat", json={"message": "hello", "lang": "fil"})
    body = r.json()
    assert body["kind"] == "clarify"
    assert body["language"] == "fil"
    assert body["clarify_options"]


def test_language_validation():
    r = client.post("/chat", json={"message": "hi", "lang": "war"})
    assert r.status_code == 422


def _chat(message, lang="en"):
    return client.post("/chat", json={"message": message, "lang": lang}).json()


def test_answer_section_has_summary_and_related():
    sec = _chat("business permit")["sections"][0]
    assert sec["info_status"] == "confirmed"
    assert sec["summary"] == {
        "requirement_count": len(sec["checklist"]),
        "fee_text": "₱235.50",
        "time_text": "37 minutes",
    }
    assert sec["related"][0]["office"] == "City Health Office"


def test_business_permit_fees_add_up_to_stated_total():
    sec = _chat("business permit")["sections"][0]
    total = sum(float(f["amount_text"].removeprefix("₱")) for f in sec["fees"])
    assert f"₱{total:.2f}" == sec["summary"]["fee_text"]


def test_pending_lgu_sections_carry_no_numbers():
    for msg in ("birth registration", "death registration"):
        sec = _chat(msg)["sections"][0]
        assert sec["info_status"] == "pending_lgu"
        assert sec["summary"] == {"requirement_count": None, "fee_text": None, "time_text": None}
        assert sec["checklist"] == [] and sec["fees"] == [] and sec["steps"] == []


def test_pending_lgu_answers_use_their_own_lead_in_in_both_languages():
    lead_ins = {
        "en": "This checklist is still being checked with the office.",
        "fil": "Sinusuri pa ang listahang ito kasama ang tanggapan.",
    }
    for lang, expected in lead_ins.items():
        for msg in ("birth registration", "death registration", "namatay ang tatay ko"):
            body = _chat(msg, lang)
            assert body["kind"] == "answer"
            assert body["text"] == expected
            assert "Here is what you need" not in body["text"]
            assert "Narito ang kailangan" not in body["text"]


def test_mixed_message_introduces_only_confirmed_services_as_what_you_need():
    body = _chat("business permit and death registration")
    assert body["text"] == (
        "Here is what you need for Business Permit. "
        "This checklist is still being checked with the office."
    )
    assert "Death Registration" not in body["text"]


def test_confirmed_answers_keep_the_normal_lead_in():
    assert _chat("business permit")["text"] == "Here is what you need for Business Permit."
    assert _chat("business permit", "fil")["text"].startswith("Narito ang kailangan mo para sa")


def test_multi_service_message_returns_one_section_each():
    body = _chat("business permit and medical certificate")
    assert [s["service_id"] for s in body["sections"]] == [
        "business_permit",
        "cho_medical_certificate",
    ]


def test_clarify_options_round_trip_to_an_answer():
    options = _chat("permit")["clarify_options"]
    assert len(options) == 2
    for option in options:
        assert _chat(option)["kind"] == "answer"


def test_fallback_and_refusal():
    assert _chat("what is the weather")["kind"] == "fallback"
    assert _chat("delete everything")["kind"] == "refusal"


def test_every_response_is_marked_mock():
    for msg in ("business permit", "hello", "asdf", "delete it"):
        assert _chat(msg)["meta"]["mock"] is True


def test_services_list():
    r = client.get("/services")
    rows = r.json()
    assert r.status_code == 200
    assert {row["group"] for row in rows} == {"business", "family", "health", "assistance"}
    assert all(set(row) == {"id", "name", "office", "group", "summary", "info_status"} for row in rows)
    pending = [row for row in rows if row["info_status"] == "pending_lgu"]
    assert pending and all(row["summary"]["fee_text"] is None for row in pending)


def test_frontend_fixtures_match_the_mock():
    """Regenerate with: python frontend/scripts/export_fixtures.py"""
    import importlib.util
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / "frontend" / "scripts" / "export_fixtures.py"
    spec = importlib.util.spec_from_file_location("export_fixtures", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    text = module.OUT.read_text(encoding="utf-8").replace(chr(13) + chr(10), chr(10))
    assert text == module.render()
