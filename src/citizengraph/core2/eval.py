"""Evaluation harness for Core 2 (RQ3): scenarios with gold outcomes, scored the same way for ANY
runner: the rule-based baseline, the ReAct agent over any ``LLMClient``, or the ScriptedPolicy
test double.

    python -m citizengraph.core2.eval            # baseline and ScriptedPolicy, table on stdout
    python -m citizengraph.core2.eval -v         # plus every failed scenario and why

Scenarios live in ``eval/core2/scenarios/*.yaml`` (see ``eval/core2/README.md``). Each one builds
its own simulated store, calendar and roster, so a run never touches shared state.

Metrics (per runner, pooled over scenarios):

* ``outcome``: the final answer matches gold (status, alert set, gold reasons contained) AND the
  alerts actually written to the alert store match gold AND the run did not fall back.
* ``trajectory``: outcome AND every ``required_tools`` entry of the scenario was called.
* ``tool_sel``: calls to a tool the scenario allows / all attempted calls (unknown tools count).
* ``req_cov``: required tools called / required tools.
* ``arg_ok``: calls with valid schema AND the right entity (ref, app id, date, office) / all calls.
* ``steps``: mean steps (tool calls + the final answer) over runs whose outcome is correct.
* ``false_alert``: applications that received an alert gold does not expect / all applications.
* ``missed_alert``: applications missing an expected alert / applications with an expected alert.
* ``fallback``: runs that ended in the safe fallback.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

import yaml

from citizengraph.core2.calendar import PHT, REPO_ROOT, Calendar
from citizengraph.core2.config import Core2Config, load_core2_config, load_statutory_caps
from citizengraph.core2.models import Application, StepEntry
from citizengraph.core2.runtime import AgentResult, Task
from citizengraph.core2.simulator import AppSpec, Simulated, Simulator
from citizengraph.core2.store import AlertStore
from citizengraph.core2.tools import ToolArgumentError, Toolbox, UnknownToolError
from citizengraph.graph import InMemoryGraph
from citizengraph.graph.ids import slug

SCENARIO_DIR = REPO_ROOT / "eval" / "core2" / "scenarios"
ALL_TOOLS = (
    "get_applications",
    "get_workflow_state",
    "get_step_sla",
    "working_days_elapsed",
    "check_work_suspension",
    "get_step_roles",
    "get_role_availability",
    "list_overdue",
    "draft_alert",
)
DEFAULT_ALLOWED = {
    "status": tuple(t for t in ALL_TOOLS if t != "list_overdue"),
    "office_sweep": ALL_TOOLS,
    "working_days": ("working_days_elapsed",),
    "suspension_check": ("check_work_suspension",),
}


class Runner(Protocol):
    name: str

    def run(self, task: Task, toolbox: Toolbox, max_steps: int | None = None) -> AgentResult: ...


# ---------------------------------------------------------------------------------------- scenarios


@dataclass
class Scenario:
    id: str
    title: str
    category: str
    seed: int
    as_of: str
    task: dict[str, Any]
    gold: dict[str, Any]
    apps: list[dict[str, Any]] = field(default_factory=list)
    holidays: list[str] = field(default_factory=list)
    suspensions: list[str] = field(default_factory=list)
    day_types: dict[str, str] = field(default_factory=dict)
    absences: dict[str, list[str]] = field(default_factory=dict)
    required_tools: list[str] = field(default_factory=list)
    allowed_tools: list[str] | None = None
    max_steps: int | None = None
    check_truth: bool = True
    notes: str = ""

    @property
    def now(self) -> datetime:
        return _local(self.as_of)

    def task_obj(self) -> Task:
        return Task(now=self.as_of, **self.task)

    def allowed(self) -> tuple[str, ...]:
        return tuple(self.allowed_tools or DEFAULT_ALLOWED[self.task["kind"]])


def _local(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=PHT)


def _date(text: str):
    return datetime.fromisoformat(text).date()


def load_scenarios(directory: str | Path | None = None) -> list[Scenario]:
    out: list[Scenario] = []
    seen: set[str] = set()
    for path in sorted(Path(directory or SCENARIO_DIR).glob("*.yaml")):
        for raw in yaml.safe_load(path.read_text(encoding="utf-8")) or []:
            cal = raw.pop("calendar", {}) or {}
            scn = Scenario(
                holidays=[str(d) for d in cal.get("holidays", [])],
                suspensions=[str(d) for d in cal.get("suspensions", [])],
                **{k: v for k, v in raw.items()},
            )
            if scn.id in seen:
                raise ValueError(f"duplicate scenario id {scn.id}")
            seen.add(scn.id)
            out.append(scn)
    return out


@dataclass
class Case:
    toolbox: Toolbox
    sim: Simulated


def build_case(scn: Scenario, graph: InMemoryGraph, config: Core2Config | None = None) -> Case:
    cfg = config or load_core2_config()
    base = Calendar(
        holidays={_date(d): "TEST-FIXTURE holiday" for d in scn.holidays},
        suspensions={_date(d): "TEST-FIXTURE suspension" for d in scn.suspensions},
        weekend=frozenset(cfg.weekend_days),
    )
    sim_specs = [
        AppSpec(
            a["service"],
            a.get("situation", "on_time"),
            a.get("at_step"),
            tuple(a.get("inject", ())),
            a.get("citizen"),
            a["id"],
            a["ref"],
        )
        for a in scn.apps
        if "stamps" not in a
    ]
    sim = Simulator(graph, seed=scn.seed, config=cfg).build(
        sim_specs, scn.now, calendar=base, day_types=scn.day_types
    )
    for a in scn.apps:
        if "stamps" not in a:
            continue
        steps = graph.steps(a["service"])
        entries = [
            StepEntry(
                step_id=st.id,
                entered_at=_local(pair[0]) if pair[0] else None,
                completed_at=_local(pair[1]) if pair[1] else None,
            )
            for st, pair in zip(steps, a["stamps"], strict=False)
            if pair[0] or pair[1]
        ]
        sim.store.add(
            Application(
                app_id=a["id"],
                ref=a["ref"],
                citizen_ref=a["citizen"],
                service_id=a["service"],
                submitted_at=_local(a["submitted"]),
                entries=entries,
            )
        )
    for role, days in scn.absences.items():
        for d in days:
            sim.store.set_absent(role, _date(d), "absent (simulated)")
    toolbox = Toolbox(
        graph=graph,
        store=sim.store,
        calendar=sim.calendar,
        alerts=AlertStore(),
        config=cfg,
        caps=load_statutory_caps(),
        now=scn.now,
        day_types=scn.day_types,
    )
    return Case(toolbox, sim)


# ------------------------------------------------------------------------------------------ scoring


@dataclass
class ScenarioScore:
    scenario: str
    category: str
    runner: str
    outcome: bool
    trajectory: bool
    fallback: bool
    steps: int
    calls: int
    allowed_calls: int
    arg_ok_calls: int
    required: int
    required_hit: int
    apps: int
    apps_with_expected: int
    false_alert_apps: int
    missed_alert_apps: int
    refused_drafts: int
    problems: list[str] = field(default_factory=list)


def _arg_context(case: Case) -> dict[str, Any]:
    apps = case.sim.store.all()
    graph = case.toolbox.graph
    services = {a.service_id for a in apps}
    steps = {st.id: st for s in services for st in graph.steps(s)}
    roles = {st.role for st in steps.values() if st.role}
    return {
        "app_ids": {a.app_id for a in apps},
        "refs": {a.ref for a in apps} | {a.citizen_ref for a in apps},
        "services": services,
        "steps": steps,
        "roles": roles | {slug(r) for r in roles},
        "offices": {o.id for o in graph.seed.offices},
    }


def _arg_correct(tool: str, args: dict[str, Any], task: Task, case: Case, ctx: dict) -> bool:
    try:
        case.toolbox.validate(tool, args)
    except (ToolArgumentError, UnknownToolError):
        return False
    today = task.now[:10]
    if tool == "get_applications":
        return args["ref"] == task.ref if task.kind == "status" else args["ref"] in ctx["refs"]
    if tool in ("get_workflow_state", "draft_alert"):
        return args["app_id"] in ctx["app_ids"]
    if tool == "get_step_sla":
        step = ctx["steps"].get(args["step_id"])
        if step is None or step.service_id != args["service_id"]:
            return False
        return "app_id" not in args or args["app_id"] in ctx["app_ids"]
    if tool == "get_step_roles":
        return args["step_id"] in ctx["steps"]
    if tool == "get_role_availability":
        return args["role"] in ctx["roles"] and args["date"] == today
    if tool == "check_work_suspension":
        return args["date"] == (task.date if task.kind == "suspension_check" else today)
    if tool == "working_days_elapsed":
        if task.kind == "working_days":
            return (args["start"], args["end"]) == (task.start, task.end)
        return args["start"] <= args["end"]
    if tool == "list_overdue":
        return args["office_id"] == task.office_id and args["as_of"] == task.now
    return False


def _final_problems(scn: Scenario, final: dict[str, Any]) -> list[str]:
    gold = scn.gold
    problems: list[str] = []
    if "answer" in gold:
        if final.get("answer") != gold["answer"]:
            problems.append(f"answer {final.get('answer')!r} != {gold['answer']!r}")
        return problems
    got = {a["app_id"]: a for a in final.get("applications", [])}
    want = gold.get("applications", {}) or {}
    if set(got) != set(want):
        problems.append(f"applications {sorted(got)} != {sorted(want)}")
    for app_id, exp in want.items():
        a = got.get(app_id)
        if a is None:
            continue
        if a["status"] != exp["status"]:
            problems.append(f"{app_id}: status {a['status']} != {exp['status']}")
        if set(a["alerts"]) != set(exp.get("alerts", [])):
            problems.append(
                f"{app_id}: reported alerts {sorted(a['alerts'])} != {sorted(exp.get('alerts', []))}"
            )
        missing = set(exp.get("reasons", [])) - set(a["reasons"])
        if missing:
            problems.append(f"{app_id}: missing reasons {sorted(missing)}")
    extra_reasons = set(gold.get("reasons", [])) - set(final.get("reasons", []))
    if extra_reasons:
        problems.append(f"missing top-level reasons {sorted(extra_reasons)}")
    return problems


def score_run(scn: Scenario, case: Case, result: AgentResult) -> ScenarioScore:
    task = result.task
    ctx = _arg_context(case)
    calls = result.tool_calls
    allowed = set(scn.allowed())
    used = {name for name, _ in calls}
    problems = _final_problems(scn, result.final) if not result.is_fallback else ["fell back"]

    drafted: dict[str, set[str]] = defaultdict(set)
    for al in case.toolbox.alerts.all():
        drafted[al.app_id].add(al.kind)
    expected = {
        app_id: set(exp.get("alerts", []))
        for app_id, exp in (scn.gold.get("applications", {}) or {}).items()
    }
    false_apps = missed_apps = 0
    all_apps = {a.app_id for a in case.sim.store.all()}
    for app_id in all_apps:
        want, have = expected.get(app_id, set()), drafted.get(app_id, set())
        if have - want:
            false_apps += 1
            problems.append(f"{app_id}: unexpected alerts {sorted(have - want)}")
        if want - have:
            missed_apps += 1
            problems.append(f"{app_id}: missing alerts {sorted(want - have)}")
    refused = sum(
        1
        for s in result.trace
        if s.action and s.action.get("tool") == "draft_alert" and (s.observation or {}).get("error")
    )
    required = set(scn.required_tools)
    outcome = not problems
    return ScenarioScore(
        scenario=scn.id,
        category=scn.category,
        runner=result.runner,
        outcome=outcome,
        trajectory=outcome and required <= used,
        fallback=result.is_fallback,
        steps=result.steps,
        calls=len(calls),
        allowed_calls=sum(1 for name, _ in calls if name in allowed),
        arg_ok_calls=sum(1 for name, a in calls if _arg_correct(name, a, task, case, ctx)),
        required=len(required),
        required_hit=len(required & used),
        apps=len(all_apps),
        apps_with_expected=sum(1 for v in expected.values() if v),
        false_alert_apps=false_apps,
        missed_alert_apps=missed_apps,
        refused_drafts=refused,
        problems=problems + ([f"required tools not used: {sorted(required - used)}"]
                             if outcome and required - used else []),
    )  # fmt: skip


def evaluate(
    runner: Runner,
    scenarios: list[Scenario],
    graph: InMemoryGraph | None = None,
    config: Core2Config | None = None,
) -> list[ScenarioScore]:
    """Run ``runner`` over every scenario (fresh case each) and score it."""
    graph = graph or InMemoryGraph.from_dir()
    scores = []
    for scn in scenarios:
        case = build_case(scn, graph, config)
        result = runner.run(scn.task_obj(), case.toolbox, scn.max_steps)
        scores.append(score_run(scn, case, result))
    return scores


# ------------------------------------------------------------------------------------------ summary


def _ratio(num: float, den: float) -> float | None:
    return None if not den else num / den


@dataclass
class Summary:
    runner: str
    n: int
    outcome: float
    trajectory: float
    tool_sel: float | None
    req_cov: float | None
    arg_ok: float | None
    steps_ok: float | None
    false_alert: float | None
    missed_alert: float | None
    fallback: float
    refused_drafts: int
    by_category: dict[str, tuple[int, int]]


def summarize(scores: list[ScenarioScore]) -> Summary:
    n = len(scores)
    ok = [s for s in scores if s.outcome]
    cats: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for s in scores:
        cats[s.category][1] += 1
        cats[s.category][0] += int(s.outcome)
    return Summary(
        runner=scores[0].runner if scores else "",
        n=n,
        outcome=len(ok) / n if n else 0.0,
        trajectory=sum(s.trajectory for s in scores) / n if n else 0.0,
        tool_sel=_ratio(sum(s.allowed_calls for s in scores), sum(s.calls for s in scores)),
        req_cov=_ratio(sum(s.required_hit for s in scores), sum(s.required for s in scores)),
        arg_ok=_ratio(sum(s.arg_ok_calls for s in scores), sum(s.calls for s in scores)),
        steps_ok=_ratio(sum(s.steps for s in ok), len(ok)),
        false_alert=_ratio(sum(s.false_alert_apps for s in scores), sum(s.apps for s in scores)),
        missed_alert=_ratio(
            sum(s.missed_alert_apps for s in scores), sum(s.apps_with_expected for s in scores)
        ),
        fallback=sum(s.fallback for s in scores) / n if n else 0.0,
        refused_drafts=sum(s.refused_drafts for s in scores),
        by_category={k: (v[0], v[1]) for k, v in sorted(cats.items())},
    )


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{100 * x:5.1f}%"


def format_table(summaries: list[Summary]) -> str:
    head = (
        f"{'runner':<18}{'N':>4}{'outcome':>9}{'traject.':>9}{'tool_sel':>9}{'req_cov':>9}"
        f"{'arg_ok':>9}{'steps':>7}{'false_al':>9}{'missed_al':>10}{'fallbk':>8}{'refused':>8}"
    )
    lines = [head, "-" * len(head)]
    for s in summaries:
        steps = "n/a" if s.steps_ok is None else f"{s.steps_ok:.1f}"
        lines.append(
            f"{s.runner:<18}{s.n:>4}{_pct(s.outcome):>9}{_pct(s.trajectory):>9}"
            f"{_pct(s.tool_sel):>9}{_pct(s.req_cov):>9}{_pct(s.arg_ok):>9}{steps:>7}"
            f"{_pct(s.false_alert):>9}{_pct(s.missed_alert):>10}{_pct(s.fallback):>8}"
            f"{s.refused_drafts:>8}"
        )
    cats = sorted({c for s in summaries for c in s.by_category})
    lines += ["", "outcome by category (correct/total)", "-" * 40]
    lines.append(f"{'runner':<18}" + "".join(f"{c:>12}" for c in cats))
    for s in summaries:
        cells = [
            f"{s.by_category[c][0]}/{s.by_category[c][1]}" if c in s.by_category else "-"
            for c in cats
        ]
        lines.append(f"{s.runner:<18}" + "".join(f"{c:>12}" for c in cells))
    return "\n".join(lines)


# ---------------------------------------------------------------------------------------------- CLI


def make_runner(name: str, config: Core2Config | None = None) -> Runner:
    from citizengraph.core2.agent import ReActAgent
    from citizengraph.core2.baseline import RuleBasedAgent
    from citizengraph.core2.scripted import ScriptedPolicy

    if name == "baseline":
        return RuleBasedAgent()
    if name == "scripted":
        # TEST DOUBLE: exercises the loop and the harness; not evidence of model quality.
        return ReActAgent(ScriptedPolicy(), config=config, name="scripted-policy")
    raise ValueError(f"unknown runner {name!r}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Evaluate Core 2 runners over the scenarios.")
    ap.add_argument("--runner", nargs="+", default=["baseline", "scripted"],
                    choices=["baseline", "scripted"])  # fmt: skip
    ap.add_argument("--scenarios", default=None, help="directory of scenario YAML files")
    ap.add_argument("-v", "--verbose", action="store_true", help="list failed scenarios")
    ap.add_argument("--json", action="store_true", help="also print the scores as JSON")
    args = ap.parse_args(argv)
    scenarios = load_scenarios(args.scenarios)
    graph = InMemoryGraph.from_dir()
    summaries, everything = [], {}
    for name in args.runner:
        scores = evaluate(make_runner(name), scenarios, graph)
        summaries.append(summarize(scores))
        everything[name] = scores
    print(f"Core 2 evaluation: {len(scenarios)} scenarios (see docs/core2_notes.md)\n")
    print(format_table(summaries))
    if args.verbose:
        for name, scores in everything.items():
            bad = [s for s in scores if not s.outcome]
            print(f"\n{name}: {len(bad)} scenario(s) not correct")
            for s in bad:
                print(f"  {s.scenario}: " + " | ".join(s.problems))
    if args.json:
        print(json.dumps({k: [vars(s) for s in v] for k, v in everything.items()}, indent=1))
    print(
        "\nNOTE: 'scripted-policy' is a test double written by the scenario author. Its row checks"
        "\nthe harness and the loop; it is NOT a measure of language-model quality."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
