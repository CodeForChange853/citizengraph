"""Export gold trajectories from the reference policy as chat-message JSONL.

SYNTHETIC and produced by CODE. No language model wrote any of it (CLAUDE.md rule 5): every action
comes from ``reference_plan`` (``scripted.py``) and every observation from the real tools running
on a simulated store. Each line is one step, because inference is stateless: the prompt holds the
task and the history so far, and the assistant turn is the next action (or the final answer).

    {"messages": [{"role": "system", "content": <rules and tools>},
                  {"role": "user", "content": "TASK: ...\\nHISTORY:\\n...\\nNEXT:"},
                  {"role": "assistant", "content": "{\\"tool\\": ...}"}],
     "meta": {"synthetic": true, "generated_by_llm": false, "produced_by": "code: ...", ...}}

so one adapter can later be trained on Core 1 and Core 2 data.

Trajectories come from simulator populations, NOT from the evaluation scenarios: seeds used by
``eval/core2/scenarios`` are refused, and a test checks that no training prompt equals an evaluation
prompt. The gold policy is the reference policy: a model trained on this imitates that policy; it
does not learn an independent notion of correctness.

    python -m citizengraph.core2.traces --out data/simulated/core2_gold_traces.jsonl --apps 200 --seed 9000
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

from citizengraph.core2.agent import build_preamble, build_prompt
from citizengraph.core2.calendar import PHT
from citizengraph.core2.config import Core2Config, load_core2_config, load_statutory_caps
from citizengraph.core2.eval import load_scenarios
from citizengraph.core2.runtime import Task
from citizengraph.core2.scripted import reference_plan
from citizengraph.core2.simulator import Simulator
from citizengraph.core2.store import AlertStore
from citizengraph.core2.tools import Toolbox
from citizengraph.graph import InMemoryGraph

EVAL_SEEDS = frozenset(s.seed for s in load_scenarios())
AS_OF = datetime(2026, 3, 4, 14, 0, tzinfo=PHT)
_COMPACT = {"separators": (",", ":"), "ensure_ascii": False}
PRODUCED_BY = "code: citizengraph.core2.traces (reference_plan over simulated data)"


def _dumps(obj: Any) -> str:
    return json.dumps(obj, **_COMPACT)


def episode(
    task: Task, toolbox: Toolbox, max_steps: int | None = None, meta: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """The training examples for one task: one per step, ending with the final answer."""
    cfg = toolbox.config
    cap = max_steps or cfg.max_steps
    preamble = build_preamble(toolbox)
    plan = reference_plan(task)
    history: list[tuple[str, str]] = []
    out: list[dict[str, Any]] = []

    def example(action: dict[str, Any], step: int) -> dict[str, Any]:
        user = build_prompt(task, preamble, history)[len(preamble) + 1 :]
        return {
            "messages": [
                {"role": "system", "content": preamble},
                {"role": "user", "content": user},
                {"role": "assistant", "content": _dumps(action)},
            ],
            "meta": {
                "synthetic": True,
                "generated_by_llm": False,
                "produced_by": PRODUCED_BY,
                "core": 2,
                "task_kind": task.kind,
                "step": step,
                **(meta or {}),
            },
        }

    try:
        action = next(plan)
        for step in range(1, cap + 1):
            out.append(example(action, step))
            obs = toolbox.call(action["tool"], action["args"])
            history.append((_dumps(action), _dumps(obs)))
            action = plan.send(obs)
    except StopIteration as done:
        out.append(example({"final": done.value}, len(history) + 1))
        return out
    return []  # ran past the step cap: not a usable gold episode


def generate(
    n_apps: int, seed: int, graph: InMemoryGraph | None = None, config: Core2Config | None = None
) -> Iterator[dict[str, Any]]:
    """Gold examples for a simulated population of ``n_apps`` applications plus sweeps and
    calendar questions. Refuses seeds used by the evaluation scenarios."""
    if seed in EVAL_SEEDS:
        raise ValueError(f"seed {seed} is used by an evaluation scenario; pick another")
    graph = graph or InMemoryGraph.from_dir()
    cfg = config or load_core2_config()
    rng = random.Random(f"traces-{seed}")
    sim = Simulator(graph, seed=seed, config=cfg).population(n_apps, AS_OF)
    now = AS_OF.strftime("%Y-%m-%dT%H:%M")

    def toolbox() -> Toolbox:
        return Toolbox(
            graph=graph, store=sim.store, calendar=sim.calendar, alerts=AlertStore(),
            config=cfg, caps=load_statutory_caps(), now=AS_OF, day_types=sim.day_types,
        )  # fmt: skip

    def keep(eps: list[dict[str, Any]]) -> bool:
        limit = cfg.max_prompt_chars
        return bool(eps) and all(
            len(e["messages"][0]["content"]) + len(e["messages"][1]["content"]) <= limit
            for e in eps
        )

    tasks: list[tuple[Task, int]] = []
    seen_citizens: set[str] = set()
    for app in sim.store.all():
        tasks.append((Task(kind="status", now=now, ref=app.ref), 14))
        if app.citizen_ref not in seen_citizens and len(sim.store.find(app.citizen_ref)) > 1:
            seen_citizens.add(app.citizen_ref)
            tasks.append((Task(kind="status", now=now, ref=app.citizen_ref), 30))
    for office in graph.seed.offices:
        tasks.append((Task(kind="office_sweep", now=now, office_id=office.id), 30))
    tasks.append((Task(kind="status", now=now, ref="CG-SIM-9999"), 8))  # nothing found
    week = [f"2026-03-{d:02d}" for d in range(2, 10)]
    for _ in range(max(4, n_apps // 10)):
        a, b = sorted(rng.sample(week, 2))
        tasks.append((Task(kind="working_days", now=now, start=a, end=b), 8))
        tasks.append((Task(kind="suspension_check", now=now, date=rng.choice(week)), 8))
    for task, cap in tasks:
        eps = episode(task, toolbox(), cap, {"seed": seed})
        if keep(eps):
            yield from eps


def write_jsonl(path: str | Path, examples: Iterator[dict[str, Any]] | list[dict[str, Any]]) -> int:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with p.open("w", encoding="utf-8") as fh:
        for ex in examples:
            fh.write(json.dumps(ex, ensure_ascii=False) + "\n")
            n += 1
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Export synthetic Core 2 gold trajectories.")
    ap.add_argument("--out", required=True)
    ap.add_argument("--apps", type=int, default=200)
    ap.add_argument("--seed", type=int, default=9000)
    args = ap.parse_args(argv)
    n = write_jsonl(args.out, generate(args.apps, args.seed))
    print(f"wrote {n} synthetic examples (produced by code, not by a language model) to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
