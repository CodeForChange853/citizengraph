"""Score a model's Cypher against the gold queries of the synthetic dataset.

For every example it computes, from the model output only (no Neo4j, no GPU needed here):

* guardrail-valid rate: ``validate_cypher`` accepts the query;
* exact match against the gold Cypher (whitespace differences ignored, a ```cypher fence around
  the query is stripped and counted separately);
* canonical rate: valid and identical to SOME canonical template (right query, wrong shape);
* literal-id rate: the query writes a string literal or the service id instead of ``$sid``.

Broken down by intent, shape, language, noise level and split (from the ``.meta.jsonl`` files).

Two ways to get outputs:

    # 1. a file of outputs (JSONL, one {"id": ..., "output": ...} per line; "id" optional,
    #    then lines are matched to examples by position)
    python -m training.eval_generate --data training/out/test_synthetic.jsonl \\
        --meta training/out/test_synthetic.meta.jsonl --outputs outputs.jsonl

    # 2. any OpenAI-compatible chat endpoint (llama.cpp `llama-server`, Ollama at /v1, vLLM)
    python -m training.eval_generate --data training/out/test_synthetic.jsonl \\
        --meta training/out/test_synthetic.meta.jsonl \\
        --endpoint http://localhost:8080/v1 --model core1 --limit 200

STATUS: the scoring code is tested on CPU (tests/test_training_eval.py, with a stub HTTP server).
It has NOT been run against a real model or a real llama.cpp/Ollama server: check the first
real run (prompt format accepted by the server, output free of extra text, timeouts).

Needs the repo installed (``pip install -e .``, or ``pip install --no-deps -e .`` plus pydantic
and pyyaml on a notebook) for the guardrail and the templates. Standard library only otherwise.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from citizengraph.core1 import templates as T
from citizengraph.guardrail.lexer import STRING, LexError, tokenize
from citizengraph.guardrail.validator import validate_cypher

_FENCE = re.compile(r"^```[A-Za-z]*\s*\n?(.*?)\n?```\s*$", re.DOTALL)
GROUP_KEYS = ("intent", "shape", "language", "noise", "split")


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
    gold: str
    meta: dict[str, Any] = field(default_factory=dict)


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
    items: list[Item], endpoint: str, model: str, *, timeout: float = 120.0, max_tokens: int = 400
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


def _writes_literals(query: str) -> bool:
    try:
        return any(t.kind == STRING for t in tokenize(query))
    except LexError:
        return False


@dataclass
class Tally:
    n: int = 0
    valid: int = 0
    exact: int = 0
    canonical: int = 0
    literal: int = 0
    fenced: int = 0

    def add(
        self, *, valid: bool, exact: bool, canonical: bool, literal: bool, fenced: bool
    ) -> None:
        self.n += 1
        self.valid += valid
        self.exact += exact
        self.canonical += canonical
        self.literal += literal
        self.fenced += fenced

    def rates(self) -> dict[str, float | int]:
        n = max(self.n, 1)
        return {
            "n": self.n,
            "guardrail_valid": round(self.valid / n, 4),
            "exact_match": round(self.exact / n, 4),
            "canonical": round(self.canonical / n, 4),
            "literal_ids": round(self.literal / n, 4),
            "fenced": round(self.fenced / n, 4),
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


def score(items: list[Item], outputs: list[str], *, max_failures: int = 20) -> Report:
    """Score ``outputs`` (one per item) against the gold queries."""
    if len(items) != len(outputs):
        raise ValueError("need exactly one output per example")
    canonical = {normalize(t.cypher) for t in T.TEMPLATES.values()}
    overall = Tally()
    groups: dict[str, dict[str, Tally]] = {k: defaultdict(Tally) for k in GROUP_KEYS}
    failures: list[dict[str, str]] = []
    for item, raw in zip(items, outputs, strict=True):
        query, fenced = strip_fences(raw)
        valid = validate_cypher(query).ok
        exact = normalize(query) == normalize(item.gold)
        is_canonical = valid and normalize(query) in canonical
        literal = _writes_literals(query) or str(item.meta.get("service_id", "\0")) in query
        tallies = [overall] + [groups[k][str(item.meta[k])] for k in GROUP_KEYS if k in item.meta]
        for tally in tallies:
            tally.add(
                valid=valid, exact=exact, canonical=is_canonical, literal=literal, fenced=fenced
            )
        if not exact and len(failures) < max_failures:
            failures.append({"id": item.id, "valid": str(valid), "gold": item.gold, "output": raw})
    return Report(overall, {k: dict(v) for k, v in groups.items() if v}, failures)


def format_report(report: Report) -> str:
    def line(name: str, t: Tally) -> str:
        r = t.rates()
        return (
            f"{name:<28} n={r['n']:<6} valid={r['guardrail_valid']:.3f} "
            f"exact={r['exact_match']:.3f} canonical={r['canonical']:.3f} "
            f"literal_ids={r['literal_ids']:.3f}"
        )

    lines = [line("OVERALL", report.overall)]
    for key, group in report.groups.items():
        lines.append(f"-- by {key}")
        lines += [line(f"  {name}", t) for name, t in sorted(group.items())]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", type=Path, required=True, help="split JSONL (chat format)")
    ap.add_argument("--meta", type=Path, help="the matching .meta.jsonl (for the breakdowns)")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--outputs", type=Path, help="JSONL of model outputs")
    src.add_argument("--endpoint", help="OpenAI-compatible base URL, e.g. http://localhost:8080/v1")
    ap.add_argument("--model", default="core1", help="model name sent to the endpoint")
    ap.add_argument("--limit", type=int, help="score only the first N examples")
    ap.add_argument("--report", type=Path, help="also write the full report as JSON")
    args = ap.parse_args(argv)

    items = load_items(args.data, args.meta)
    if args.limit:
        items = items[: args.limit]
    if args.outputs:
        outputs = load_outputs(args.outputs, items)
    else:
        outputs = endpoint_outputs(items, args.endpoint, args.model)
    report = score(items, outputs)
    print(format_report(report))
    if args.report:
        args.report.write_text(
            json.dumps(report.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
