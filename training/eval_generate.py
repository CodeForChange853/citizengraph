"""Score a model's completions against the gold completions of the synthetic dataset.

The completion is three header lines (intent, shape, variants) and the Cypher
(``core1/output.py``). For every example this computes, from the prediction alone:

* guardrail-valid: the Cypher passes ``validate_cypher``;
* exact match of the whole completion, and of the Cypher alone (whitespace ignored; a ```fence```
  around it is stripped and counted);
* intent accuracy (the intent line, ``fees+processing_time`` counts as one answer), shape accuracy
  and variants accuracy (the ``dimension:value`` ids as a set);
* canonical: ``check_completion`` accepts it and the query is exactly the template of its header;
* literal ids: the query writes a string literal instead of a parameter;

and, when an executor is given (a real Neo4j), EXECUTION accuracy: the predicted query and the
gold query are both run read-only with their parameters and their result sets are compared (as
multisets of rows, order ignored). A prediction that fails the check or raises counts as wrong.

Everything is broken down by query family (shape), intent, language, noise level, split and phrase
family. Two more ways to get predictions besides a file of outputs or a chat endpoint:
``--baseline`` runs the templates-only baseline (the gateway's rule-based intent mapped to the
canonical list templates, ``training/baseline.py``) on the same examples.

    python -m training.eval_generate --data training/out/test_synthetic.jsonl \\
        --meta training/out/test_synthetic.meta.jsonl --outputs outputs.jsonl
    python -m training.eval_generate --data ... --meta ... --baseline
    python -m training.eval_generate --data ... --meta ... --endpoint http://localhost:8080/v1 \\
        --model core1 --neo4j-uri bolt://localhost:7687 --neo4j-user neo4j \\
        --neo4j-password-env NEO4J_PASSWORD

STATUS: the scoring, the baseline and the execution comparison are tested on CPU (a stub HTTP
server, a fake executor, and a real embedded Neo4j once, see docs/training_notes.md). The model
path has NOT been run against a real model or a real llama.cpp/Ollama server: check the first real
run (prompt format accepted, output free of extra text, timeouts).

Needs the repo installed (``pip install -e .``, or ``pip install --no-deps -e .`` plus pydantic,
pyyaml and rapidfuzz on a notebook). The Neo4j path also needs the ``neo4j`` driver.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from citizengraph.core1.output import check_completion, parse_completion
from citizengraph.core1.targets import Request, parse_targets
from citizengraph.core1.templates import TEMPLATES
from citizengraph.guardrail.lexer import STRING, LexError, tokenize
from citizengraph.guardrail.validator import validate_cypher

_FENCE = re.compile(r"^```[A-Za-z]*\s*\n?(.*?)\n?```\s*$", re.DOTALL)
GROUP_KEYS = ("shape", "intent", "language", "noise", "split", "family")


def strip_fences(text: str) -> tuple[str, bool]:
    """(text without a surrounding ``` fence, whether there was one)."""
    stripped = text.strip()
    match = _FENCE.match(stripped)
    return (match.group(1).strip(), True) if match else (stripped, False)


def normalize(query: str) -> str:
    """Whitespace-insensitive form used for comparisons."""
    return " ".join(query.split())


@dataclass(frozen=True)
class Item:
    id: str
    messages: list[dict[str, str]]  # system + user (what the model sees)
    gold: str  # the gold completion: header lines and Cypher
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def request(self) -> Request | None:
        """The request the prompt was built from (needs the meta file)."""
        m = self.meta
        if "targets" not in m or "phrase" not in m:
            return None
        return Request(
            targets=parse_targets(", ".join(m["targets"])),
            phrase=m["phrase"],
            language=m["language"],
        )

    @property
    def gold_cypher(self) -> str:
        return parse_completion(self.gold).cypher


def load_items(data: Path, meta: Path | None = None) -> list[Item]:
    rows = [json.loads(x) for x in data.read_text(encoding="utf-8").splitlines() if x.strip()]
    metas = (
        [json.loads(x) for x in meta.read_text(encoding="utf-8").splitlines() if x.strip()]
        if meta
        else [{} for _ in rows]
    )
    if len(metas) != len(rows):
        raise ValueError(f"{meta} has {len(metas)} lines but {data} has {len(rows)}")
    items = []
    for i, (row, m) in enumerate(zip(rows, metas, strict=True)):
        msgs = row["messages"]
        if [x["role"] for x in msgs] != ["system", "user", "assistant"]:
            raise ValueError(f"line {i + 1}: expected system, user, assistant messages")
        items.append(Item(m.get("id", str(i)), msgs[:2], msgs[2]["content"], m))
    return items


def load_outputs(path: Path, items: list[Item]) -> list[str]:
    """Outputs aligned to ``items`` (by ``id`` when the lines carry one, else by position)."""
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    if rows and all("id" in r for r in rows):
        by_id = {str(r["id"]): r["output"] for r in rows}
        return [by_id.get(item.id, "") for item in items]
    if len(rows) != len(items):
        raise ValueError(f"{path} has {len(rows)} outputs for {len(items)} examples")
    return [r["output"] for r in rows]


def endpoint_outputs(
    items: list[Item], endpoint: str, model: str, *, timeout: float = 120.0, max_tokens: int = 600
) -> list[str]:
    """Ask an OpenAI-compatible ``/chat/completions`` endpoint (temperature 0) for each item.

    A failed request gives an empty output (scored as invalid) and a note on stderr.
    """
    url = endpoint.rstrip("/") + "/chat/completions"
    outputs = []
    for item in items:
        body = json.dumps(
            {
                "model": model,
                "messages": item.messages,
                "temperature": 0,
                "max_tokens": max_tokens,
                "stream": False,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            outputs.append(payload["choices"][0]["message"]["content"])
        except (urllib.error.URLError, TimeoutError, KeyError, IndexError, ValueError) as exc:
            print(f"request for {item.id} failed: {exc}", file=sys.stderr)
            outputs.append("")
    return outputs


def baseline_outputs(items: list[Item], baseline: Any | None = None) -> list[str]:
    """Completions of the templates-only baseline (needs the meta file for the requests)."""
    from training.baseline import TemplatesOnlyBaseline

    baseline = baseline or TemplatesOnlyBaseline()
    out = []
    for item in items:
        request = item.request
        if request is None:
            raise ValueError("the baseline needs the .meta.jsonl file (targets and phrase)")
        out.append(baseline.complete(request))
    return out


# ---- execution -------------------------------------------------------------------------------


class Executor(Protocol):
    def run(self, cypher: str, params: dict[str, Any]) -> list[dict[str, Any]]: ...


class Neo4jExecutor:
    """Read-only execution on a real Neo4j: ``execute_read`` with a per-query timeout."""

    def __init__(self, driver: Any, *, timeout: float = 10.0, database: str | None = None):
        self._driver = driver
        self._timeout = timeout
        self._database = database

    def run(self, cypher: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        from neo4j import unit_of_work

        @unit_of_work(timeout=self._timeout)
        def work(tx: Any) -> list[dict[str, Any]]:
            return [record.data() for record in tx.run(cypher, **params)]

        kwargs = {"database": self._database} if self._database else {}
        with self._driver.session(**kwargs) as session:
            return session.execute_read(work)


def rows_key(rows: list[dict[str, Any]]) -> Counter:
    """A result set as a multiset of rows (order ignored)."""
    return Counter(json.dumps(r, sort_keys=True, default=str) for r in rows)


class _Cache:
    """Runs each distinct (query, parameters) once; a failure is remembered as ``None``."""

    def __init__(self, executor: Executor):
        self._executor = executor
        self._seen: dict[str, tuple[Counter | None, str]] = {}

    def run(self, cypher: str, params: dict[str, Any]) -> tuple[Counter | None, str]:
        """(result set, "") or (None, error text)."""
        key = normalize(cypher) + "|" + json.dumps(params, sort_keys=True, default=str)
        if key not in self._seen:
            try:
                self._seen[key] = (rows_key(self._executor.run(cypher, params)), "")
            except Exception as exc:  # noqa: BLE001 - any failure is a wrong answer
                self._seen[key] = (None, str(exc)[:200])
        return self._seen[key]


def execution_matches(item: Item, prediction: str, cache: _Cache) -> bool:
    """Run prediction and gold and compare the result sets. False for anything that fails."""
    request = item.request
    if request is None:
        return False
    checked = check_completion(strip_fences(prediction)[0], request)
    if not checked.ok:
        return False
    gold, gold_error = cache.run(item.gold_cypher, item.meta["params"])
    if gold is None:  # the gold itself failed: a setup problem, say so loudly
        raise RuntimeError(f"gold query of {item.id} failed: {gold_error}")
    got, _ = cache.run(checked.cypher, checked.params)
    return got is not None and got == gold


# ---- scoring ------------------------------------------------------------------------------------


def _writes_literals(query: str) -> bool:
    try:
        return any(t.kind == STRING for t in tokenize(query))
    except LexError:
        return False


def _names_a_target(query: str, request: Request | None) -> bool:
    """The query spells out the id of a service, office or agency instead of a parameter."""
    return request is not None and any(
        t.kind != "document" and t.id in query for t in request.targets
    )


@dataclass
class Tally:
    n: int = 0
    valid: int = 0
    exact: int = 0
    cypher_exact: int = 0
    intent: int = 0
    shape: int = 0
    variants: int = 0
    canonical: int = 0
    literal: int = 0
    fenced: int = 0
    executed: int = 0
    execution_scored: int = 0

    def add(self, **flags: bool | None) -> None:
        self.n += 1
        for name, value in flags.items():
            if name == "executed":
                if value is not None:
                    self.execution_scored += 1
                    self.executed += bool(value)
            else:
                setattr(self, name, getattr(self, name) + bool(value))

    def rates(self) -> dict[str, float | int | None]:
        n = max(self.n, 1)
        return {
            "n": self.n,
            "guardrail_valid": round(self.valid / n, 4),
            "exact_match": round(self.exact / n, 4),
            "cypher_exact": round(self.cypher_exact / n, 4),
            "intent_accuracy": round(self.intent / n, 4),
            "shape_accuracy": round(self.shape / n, 4),
            "variants_accuracy": round(self.variants / n, 4),
            "canonical": round(self.canonical / n, 4),
            "literal_ids": round(self.literal / n, 4),
            "fenced": round(self.fenced / n, 4),
            "execution_accuracy": (
                round(self.executed / self.execution_scored, 4) if self.execution_scored else None
            ),
        }


@dataclass
class Report:
    overall: Tally
    groups: dict[str, dict[str, Tally]]
    failures: list[dict[str, str]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "overall": self.overall.rates(),
            "by": {
                key: {name: t.rates() for name, t in sorted(g.items())}
                for key, g in self.groups.items()
            },
            "failures": self.failures,
        }


def score(
    items: list[Item],
    outputs: list[str],
    *,
    executor: Executor | None = None,
    max_failures: int = 20,
) -> Report:
    """Score ``outputs`` (one per item) against the gold completions."""
    if len(items) != len(outputs):
        raise ValueError("need exactly one output per example")
    canonical_texts = {normalize(t.cypher) for t in TEMPLATES.values()}
    cache = _Cache(executor) if executor is not None else None
    overall = Tally()
    groups: dict[str, dict[str, Tally]] = {k: defaultdict(Tally) for k in GROUP_KEYS}
    failures: list[dict[str, str]] = []
    for item, raw in zip(items, outputs, strict=True):
        text, fenced = strip_fences(raw)
        parsed = parse_completion(text)
        gold = parse_completion(item.gold)
        valid = bool(parsed.cypher) and validate_cypher(parsed.cypher).ok
        exact = normalize(text) == normalize(item.gold)
        request = item.request
        checked = check_completion(text, request) if request is not None else None
        flags: dict[str, bool | None] = {
            "valid": valid,
            "exact": exact,
            "cypher_exact": normalize(parsed.cypher) == normalize(gold.cypher),
            "intent": not parsed.problems and parsed.intent_header == gold.intent_header,
            "shape": not parsed.problems and parsed.shape == gold.shape,
            "variants": not parsed.problems and set(parsed.variant_ids) == set(gold.variant_ids),
            "canonical": (
                checked.canonical
                if checked is not None
                else valid and normalize(parsed.cypher) in canonical_texts
            ),
            "literal": _writes_literals(parsed.cypher) or _names_a_target(parsed.cypher, request),
            "fenced": fenced,
            "executed": (
                execution_matches(item, raw, cache) if cache is not None and request else None
            ),
        }
        tallies = [overall] + [groups[k][str(item.meta[k])] for k in GROUP_KEYS if k in item.meta]
        for tally in tallies:
            tally.add(**flags)
        if not exact and len(failures) < max_failures:
            failures.append({"id": item.id, "valid": str(valid), "gold": item.gold, "output": raw})
    return Report(overall, {k: dict(v) for k, v in groups.items() if v}, failures)


def format_report(report: Report, *, keys: Sequence[str] = GROUP_KEYS[:-1]) -> str:
    def line(name: str, t: Tally) -> str:
        r = t.rates()
        ex = r["execution_accuracy"]
        return (
            f"{name:<34} n={r['n']:<5} valid={r['guardrail_valid']:.3f} "
            f"exact={r['exact_match']:.3f} intent={r['intent_accuracy']:.3f} "
            f"shape={r['shape_accuracy']:.3f} variants={r['variants_accuracy']:.3f} "
            f"exec={'-' if ex is None else f'{ex:.3f}'}"
        )

    lines = [line("OVERALL", report.overall)]
    for key in keys:
        if key in report.groups:
            lines.append(f"-- by {key}")
            lines += [line(f"  {name}", t) for name, t in sorted(report.groups[key].items())]
    return "\n".join(lines)


def compare(reports: dict[str, Report]) -> str:
    """Side by side: overall and per query family, one column per system."""
    names = list(reports)
    shapes = sorted({s for r in reports.values() for s in r.groups.get("shape", {})})
    rows = [["metric", *names]]
    for metric in ("guardrail_valid", "exact_match", "intent_accuracy", "execution_accuracy"):
        rows.append(
            [f"OVERALL {metric}"] + [_fmt(reports[n].overall.rates()[metric]) for n in names]
        )
    for shape in shapes:
        cells = []
        for name in names:
            tally = reports[name].groups.get("shape", {}).get(shape)
            rates = tally.rates() if tally else None
            cells.append(_fmt(rates["exact_match"]) if rates else "-")
        rows.append([f"exact [{shape}]", *cells])
    width = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    return "\n".join("  ".join(c.ljust(w) for c, w in zip(r, width, strict=True)) for r in rows)


def _fmt(value: float | None) -> str:
    return "-" if value is None else f"{value:.3f}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", type=Path, required=True, help="split JSONL (chat format)")
    ap.add_argument("--meta", type=Path, help="the matching .meta.jsonl (breakdowns, execution)")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--outputs", type=Path, help="JSONL of model outputs")
    src.add_argument("--endpoint", help="OpenAI-compatible base URL, e.g. http://localhost:8080/v1")
    src.add_argument("--baseline", action="store_true", help="the templates-only baseline")
    ap.add_argument("--model", default="core1", help="model name sent to the endpoint")
    ap.add_argument("--limit", type=int, help="score only the first N examples")
    ap.add_argument("--report", type=Path, help="also write the full report as JSON")
    ap.add_argument("--neo4j-uri", help="score execution accuracy against this Neo4j")
    ap.add_argument("--neo4j-user", default="neo4j")
    ap.add_argument("--neo4j-password-env", default="NEO4J_PASSWORD")
    args = ap.parse_args(argv)

    items = load_items(args.data, args.meta)
    if args.limit:
        items = items[: args.limit]
    if args.outputs:
        outputs = load_outputs(args.outputs, items)
    elif args.baseline:
        outputs = baseline_outputs(items)
    else:
        outputs = endpoint_outputs(items, args.endpoint, args.model)
    executor = None
    driver = None
    if args.neo4j_uri:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(
            args.neo4j_uri,
            auth=(args.neo4j_user, os.environ.get(args.neo4j_password_env, "")),
        )
        executor = Neo4jExecutor(driver)
    try:
        report = score(items, outputs, executor=executor)
    finally:
        if driver is not None:
            driver.close()
    print(format_report(report))
    if args.report:
        args.report.write_text(
            json.dumps(report.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
