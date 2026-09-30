"""eval_generate: scoring model output against gold Cypher, from a file or an endpoint."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from test_training_common import load

from citizengraph.core1 import templates as T

E = load("eval_generate")
G = load("generate_dataset")


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    ds = G.build_dataset(seed=0, train_rounds=1, eval_fraction=0.05)
    out = tmp_path_factory.mktemp("eval")
    G.write_dataset(ds, out)
    return out


@pytest.fixture(scope="module")
def items(data):
    return E.load_items(data / "test_synthetic.jsonl", data / "test_synthetic.meta.jsonl")[:60]


def test_perfect_output_scores_one_everywhere(items):
    report = E.score(items, [i.gold for i in items])
    r = report.overall.rates()
    assert r["n"] == 60 and r["guardrail_valid"] == r["exact_match"] == r["canonical"] == 1.0
    assert r["literal_ids"] == 0.0
    assert not report.failures
    assert set(report.groups) == set(E.GROUP_KEYS)


def test_whitespace_and_fences_do_not_break_an_exact_match_but_fences_are_counted(items):
    outs = ["```cypher\n" + " ".join(i.gold.split()) + "\n```" for i in items]
    r = E.score(items, outs).overall.rates()
    assert r["exact_match"] == 1.0 and r["fenced"] == 1.0


def test_wrong_but_valid_shape_is_canonical_not_exact(items):
    other = T.TEMPLATES[("office", "list", False)].cypher
    bad = [i for i in items if i.gold != other]
    r = E.score(bad, [other] * len(bad)).overall.rates()
    assert r["guardrail_valid"] == 1.0 and r["canonical"] == 1.0 and r["exact_match"] == 0.0


def test_invalid_and_literal_outputs_are_flagged(items):
    outs = [
        "MATCH (n) DETACH DELETE n",
        "",
        "not cypher at all",
        "MATCH (s:Service {id: 'business_permit'}) RETURN s.name LIMIT 1",
    ]
    report = E.score(items[:4], outs)
    r = report.overall.rates()
    assert r["guardrail_valid"] == 0.25 and r["exact_match"] == 0.0
    assert r["literal_ids"] >= 0.25
    assert len(report.failures) == 4 and report.failures[0]["valid"] == "False"


def test_breakdowns_split_the_examples(items):
    report = E.score(items, [i.gold for i in items])
    assert sum(t.n for t in report.groups["language"].values()) == 60
    assert {"en", "fil", "mixed"} >= set(report.groups["language"])
    text = E.format_report(report)
    assert "OVERALL" in text and "by intent" in text


def test_outputs_file_by_id_position_and_length_check(items, tmp_path):
    path = tmp_path / "o.jsonl"
    rows = [{"id": i.id, "output": i.gold} for i in items]
    path.write_text("\n".join(json.dumps(r) for r in reversed(rows)) + "\n", encoding="utf-8")
    assert E.load_outputs(path, items) == [i.gold for i in items]
    path.write_text(
        "\n".join(json.dumps({"output": i.gold}) for i in items) + "\n", encoding="utf-8"
    )
    assert E.load_outputs(path, items) == [i.gold for i in items]
    path.write_text(json.dumps({"output": "x"}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        E.load_outputs(path, items)
    with pytest.raises(ValueError):
        E.score(items, ["x"])


def test_items_need_the_three_chat_messages(tmp_path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text(json.dumps({"messages": [{"role": "user", "content": "hi"}]}) + "\n")
    with pytest.raises(ValueError):
        E.load_items(bad)


# ---- endpoint, against a stub server ----------------------------------------------------------


class _Server:
    def __init__(self, answer):
        outer = self
        self.requests: list[dict] = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.requests.append(body)
                status, payload = answer(body)
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass

        self.httpd = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}/v1"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *a):
        self.httpd.shutdown()
        self.httpd.server_close()


def test_endpoint_outputs_send_system_and_user_at_temperature_zero(items):
    gold = {i.messages[1]["content"]: i.gold for i in items[:5]}

    def answer(body):
        user = body["messages"][1]["content"]
        return 200, {"choices": [{"message": {"content": gold[user]}}]}

    with _Server(answer) as server:
        outs = E.endpoint_outputs(items[:5], server.url, "core1")
    assert outs == [i.gold for i in items[:5]]
    sent = server.requests[0]
    assert [m["role"] for m in sent["messages"]] == ["system", "user"]
    assert sent["temperature"] == 0 and sent["model"] == "core1"


def test_a_failing_endpoint_scores_as_invalid_instead_of_crashing(items, capsys):
    with _Server(lambda body: (500, {"error": "boom"})) as server:
        outs = E.endpoint_outputs(items[:3], server.url, "core1", timeout=5)
    assert outs == ["", "", ""]
    assert "failed" in capsys.readouterr().err
    assert E.score(items[:3], outs).overall.rates()["guardrail_valid"] == 0.0


def test_command_line_with_an_outputs_file(data, tmp_path, capsys):
    items = E.load_items(data / "validation.jsonl", data / "validation.meta.jsonl")[:10]
    out = tmp_path / "o.jsonl"
    out.write_text(
        "\n".join(json.dumps({"output": i.gold}) for i in items) + "\n", encoding="utf-8"
    )
    report = tmp_path / "r.json"
    rc = E.main(
        [
            "--data",
            str(data / "validation.jsonl"),
            "--meta",
            str(data / "validation.meta.jsonl"),
            "--outputs",
            str(out),
            "--limit",
            "10",
            "--report",
            str(report),
        ]
    )
    assert rc == 0
    assert "OVERALL" in capsys.readouterr().out
    assert json.loads(report.read_text(encoding="utf-8"))["overall"]["exact_match"] == 1.0
