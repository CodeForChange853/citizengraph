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
