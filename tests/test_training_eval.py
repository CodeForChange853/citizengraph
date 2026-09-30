"""eval_generate: guardrail validity, exact match, intent accuracy and execution accuracy, per
family, from a file of outputs, a chat endpoint or the templates-only baseline."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from test_training_common import load

from citizengraph.core1 import templates as T
from citizengraph.core1.output import format_completion

E = load("eval_generate")
G = load("generate_dataset")


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    ds = G.build_dataset(seed=0, eval_fraction=0.05)
    out = tmp_path_factory.mktemp("eval")
    G.write_dataset(ds, out)
    return out


@pytest.fixture(scope="module")
def items(data):
    rows = E.load_items(data / "test_synthetic.jsonl", data / "test_synthetic.meta.jsonl")
    step = max(1, len(rows) // 80)
    return rows[::step][:80]


def one(items, shape, *, plain=False):
    return next(
        i for i in items if i.meta["shape"] == shape and (not plain or not i.meta["variants"])
    )


def test_perfect_output_scores_one_everywhere(items):
    report = E.score(items, [i.gold for i in items])
    r = report.overall.rates()
    assert r["n"] == len(items)
    for key in (
        "guardrail_valid",
        "exact_match",
        "cypher_exact",
        "intent_accuracy",
        "shape_accuracy",
        "variants_accuracy",
        "canonical",
    ):
        assert r[key] == 1.0, key
    assert r["literal_ids"] == 0.0 and r["execution_accuracy"] is None
    assert not report.failures
    assert set(report.groups) == set(E.GROUP_KEYS)
    assert "shape" in report.groups and "family" in report.groups


def test_whitespace_and_fences_do_not_break_an_exact_match_but_fences_are_counted(items):
    outs = ["```cypher\n" + i.gold + "\n```" for i in items]
    r = E.score(items, outs).overall.rates()
    assert r["exact_match"] == 1.0 and r["fenced"] == 1.0
    squeezed = [" ".join(i.gold.split()) for i in items]  # one line: header lines run together
    assert E.score(items, squeezed).overall.rates()["exact_match"] == 1.0


def test_right_intent_wrong_shape_is_not_exact(items):
    item = one(items, "count")
    wrong = format_completion(T.TEMPLATES[("requirements", "list", False)], [])
    if "steps" in item.gold.split("\n")[0]:
        wrong = format_completion(T.TEMPLATES[("steps", "list", False)], [])
    r = E.score([item], [wrong]).overall.rates()
    assert r["intent_accuracy"] == 1.0 and r["shape_accuracy"] == 0.0
    assert r["exact_match"] == 0.0 and r["guardrail_valid"] == 1.0


def test_right_header_wrong_query_counts_for_intent_but_not_for_the_query(items):
    item = one(items, "list")
    head = "\n".join(item.gold.split("\n")[:3])
    wrong = head + "\nMATCH (s:Service {id: $sid})\nRETURN s.name\nLIMIT 1"
    r = E.score([item], [wrong]).overall.rates()
    assert r["intent_accuracy"] == r["shape_accuracy"] == 1.0
    assert r["cypher_exact"] == 0.0 and r["exact_match"] == 0.0 and r["guardrail_valid"] == 1.0
    assert r["canonical"] == 0.0


def test_variants_are_scored_as_a_set(items):
    with_variants = next(i for i in items if i.meta["variants"])
    lines = with_variants.gold.split("\n")
    flipped = ["variants: " + ", ".join(reversed(lines[2].removeprefix("variants: ").split(", ")))]
    same = "\n".join([*lines[:2], *flipped, *lines[3:]])
    assert E.score([with_variants], [same]).overall.rates()["variants_accuracy"] == 1.0
    none = "\n".join([*lines[:2], "variants: none", *lines[3:]])
    assert E.score([with_variants], [none]).overall.rates()["variants_accuracy"] == 0.0


def test_invalid_malformed_and_literal_outputs_are_flagged(items):
    outs = [
        "MATCH (n) DETACH DELETE n",
        "",
        "not cypher at all",
        (
            "intent: office\nshape: list\nvariants: none\n"
            "MATCH (s:Service {id: 'business_permit'}) RETURN s.name LIMIT 1"
        ),
    ]
    report = E.score(items[:4], outs)
    r = report.overall.rates()
    assert r["guardrail_valid"] == 0.25 and r["exact_match"] == 0.0
    assert r["intent_accuracy"] <= 0.25 and r["literal_ids"] >= 0.25
    assert len(report.failures) == 4 and report.failures[0]["valid"] == "False"


def test_breakdowns_are_per_query_family_intent_language_noise_and_split(items):
    report = E.score(items, [i.gold for i in items])
    for key in E.GROUP_KEYS:
        assert sum(t.n for t in report.groups[key].values()) == len(items)
    assert {"list", "count"} <= set(report.groups["shape"])
    text = E.format_report(report)
    assert "OVERALL" in text and "by shape" in text and "by language" in text
    both = E.compare({"model": report, "baseline": report})
    assert "model" in both and "baseline" in both and "exact [count]" in both


def test_sizes_must_match(items):
    with pytest.raises(ValueError):
        E.score(items, ["x"])


# ---- execution accuracy ----------------------------------------------------------------------


class FakeExecutor:
    """Returns the rows a table says for a query (any query not in it fails)."""

    def __init__(self, table):
        self.table = table
        self.calls = []

    def run(self, cypher, params):
        self.calls.append((" ".join(cypher.split()), dict(params)))
        key = " ".join(cypher.split())
        if key not in self.table:
            raise RuntimeError("syntax error")
        return self.table[key]


def test_execution_accuracy_compares_result_sets_not_text(items):
    item = one(items, "list", plain=True)
    gold_cypher = item.gold_cypher
    alt = "MATCH (s:Service {id: $sid})-[:REQUIRES]->(r:Requirement) RETURN r.id ORDER BY r.id LIMIT 50"
    head = "\n".join(item.gold.split("\n")[:3])
    alt_completion = head + "\n" + alt
    rows = [{"r.id": "a"}, {"r.id": "b"}]
    ex = FakeExecutor(
        {" ".join(gold_cypher.split()): rows, " ".join(alt.split()): list(reversed(rows))}
    )
    r = E.score([item], [alt_completion], executor=ex).overall.rates()
    assert r["execution_accuracy"] == 1.0  # another query, the same rows (order ignored)
    assert r["cypher_exact"] == 0.0
    assert ex.calls[0][1] == item.meta["params"]  # gold ran with the gold parameters


def test_a_query_with_different_rows_or_an_error_is_wrong(items):
    item = one(items, "list", plain=True)
    gold = " ".join(item.gold_cypher.split())
    other = "MATCH (s:Service {id: $sid}) RETURN s.id LIMIT 1"
    head = "\n".join(item.gold.split("\n")[:3])
    ex = FakeExecutor({gold: [{"x": 1}], other: [{"x": 2}]})
    assert (
        E.score([item], [head + "\n" + other], executor=ex).overall.rates()["execution_accuracy"]
        == 0.0
    )
    failing = head + "\nMATCH (s:Service {id: $sid}) RETURN s.id, s.name LIMIT 1"
    assert E.score([item], [failing], executor=ex).overall.rates()["execution_accuracy"] == 0.0
    assert E.score([item], [""], executor=ex).overall.rates()["execution_accuracy"] == 0.0


def test_prediction_is_run_with_the_parameters_its_own_header_asks_for(items):
    item = next(i for i in items if i.meta["variants"])
    ids = item.meta["variants"]
    ex = FakeExecutor({" ".join(item.gold_cypher.split()): [{"n": 1}]})
    E.score([item], [item.gold], executor=ex)
    assert all(params.get("variant_ids") == ids for _, params in ex.calls)


def test_a_failing_gold_query_is_a_loud_setup_error(items):
    item = one(items, "list", plain=True)
    with pytest.raises(RuntimeError, match="gold query"):
        E.score([item], [item.gold], executor=FakeExecutor({}))


def test_the_executor_is_used_once_per_distinct_query(items):
    item = one(items, "list", plain=True)
    ex = FakeExecutor({" ".join(item.gold_cypher.split()): [{"n": 1}]})
    E.score([item, item, item], [item.gold] * 3, executor=ex)
    assert len(ex.calls) == 1


# ---- outputs, endpoint, baseline -------------------------------------------------------------


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


def test_items_need_the_three_chat_messages_and_a_matching_meta(tmp_path, data):
    bad = tmp_path / "bad.jsonl"
    bad.write_text(json.dumps({"messages": [{"role": "user", "content": "hi"}]}) + "\n")
    with pytest.raises(ValueError):
        E.load_items(bad)
    with pytest.raises(ValueError):
        E.load_items(data / "validation.jsonl", data / "test_synthetic.meta.jsonl")


def test_an_item_rebuilds_its_request_from_the_meta(items):
    item = items[0]
    request = item.request
    assert request is not None and request.phrase == item.meta["phrase"]
    assert [str(t) for t in request.targets] == item.meta["targets"]
    assert E.load_items.__name__  # the loader is exported
    assert E.Item(id="x", messages=[], gold="g").request is None


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
        return 200, {"choices": [{"message": {"content": gold[body["messages"][1]["content"]]}}]}

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


def test_the_baseline_is_scored_on_the_same_items_and_loses_to_a_perfect_model(items):
    outs = E.baseline_outputs(items)
    assert len(outs) == len(items)
    base = E.score(items, outs).overall.rates()
    perfect = E.score(items, [i.gold for i in items]).overall.rates()
    assert base["exact_match"] < 0.35 < perfect["exact_match"]
    assert base["intent_accuracy"] < perfect["intent_accuracy"]


def test_command_line_with_an_outputs_file_and_with_the_baseline(data, tmp_path, capsys):
    items = E.load_items(data / "validation.jsonl", data / "validation.meta.jsonl")[:10]
    out = tmp_path / "o.jsonl"
    out.write_text(
        "\n".join(json.dumps({"output": i.gold}) for i in items) + "\n", encoding="utf-8"
    )
    report = tmp_path / "r.json"
    base = [
        "--data", str(data / "validation.jsonl"),
        "--meta", str(data / "validation.meta.jsonl"),
        "--limit", "10",
    ]  # fmt: skip
    assert E.main([*base, "--outputs", str(out), "--report", str(report)]) == 0
    assert "OVERALL" in capsys.readouterr().out
    assert json.loads(report.read_text(encoding="utf-8"))["overall"]["exact_match"] == 1.0
    assert E.main([*base, "--baseline"]) == 0
    assert "OVERALL" in capsys.readouterr().out
