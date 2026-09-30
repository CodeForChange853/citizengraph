"""Deterministic training-data generator for Core 1 (Text-to-Cypher).

Run from the repo root:

    python -m training.generate_dataset --seed 0

Everything is produced by our own code: phrase templates (``phrasebook.yaml``), noise injection
(``noise.py``), gold Cypher from ``core1/templates.py`` and model input from ``core1/prompt.py``.
No LLM or API is called, ``eval/heldout/`` is never read, and examples contain only questions and
Cypher: no answer text from the charters. The allowed labels, relationship types and properties
are read from ``guardrail/schema.py`` at runtime (through the templates and the schema slice).

One example = (service x intent/shape x variant combination) x language x noise level:

* service, intent, variant combination: every curated service in ``graph/seed/`` with every
  combination of its variant dimensions that exists in the seed (one value or none per dimension);
  derived shapes (count, per_step, go_first) only where the data for them exists;
* the gold completion is the canonical query for the shape the wording asks for, with ids left
  as ``$sid`` / ``$variant_ids`` (see ``core1/templates.py``);
* the user message is ``build_prompt`` over the slots (service_id, intent, variants, language and
  the noisy phrase), exactly as at inference.

Splits (``train``, ``validation``, ``test_synthetic``) are by phrase-template family: a family is
a group of paraphrases that stays together, so no family appears in two splits. Some variant
combinations are also withheld from ``train`` and appear only in validation and test.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from itertools import product
from pathlib import Path
from typing import Any

import yaml

from citizengraph.core1 import templates as T
from citizengraph.core1.prompt import (
    MAX_PROMPT_TOKENS,
    SchemaSlice,
    build_prompt,
    schema_slice,
)
from citizengraph.core1.slots import LANGUAGES, Slots
from citizengraph.graph import InMemoryGraph
from citizengraph.guardrail.schema import OFFICIAL_SCHEMA
from training.noise import NOISE_LEVELS, SMS_FIL, add_noise

ROOT = Path(__file__).resolve().parents[1]
TRAINING_DIR = Path(__file__).resolve().parent
PHRASEBOOK_PATH = TRAINING_DIR / "phrasebook.yaml"
ALIASES_PATH = ROOT / "graph" / "seed" / "aliases.yaml"
DEFAULT_OUT = TRAINING_DIR / "out"
SPLITS = ("train", "validation", "test_synthetic")

OFFICIAL_NAME_SHARE = 0.15  # how often the official service name is used as it is
VARIANT_MENTION_SHARE = 0.85  # how often a given variant combination is said in the phrase
SAMPLE_SIZE = 60

_ALTERNATIVES = re.compile(r"<([^<>]*)>")
_PLACEHOLDER = re.compile(r"\{([^{}]*)\}")


class PhrasebookError(ValueError):
    """The phrasebook is malformed or does not cover the templates."""


# ---- phrasebook ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class Family:
    id: str  # "<intent>.<shape>.<language>.<n>"
    intent: str
    shape: str
    language: str
    templates: tuple[str, ...]


@dataclass(frozen=True)
class Phrasebook:
    service_names: dict[str, dict[str, tuple[str, ...]]]
    variants: dict[str, dict[str, tuple[str, ...]]]
    variant_frames: dict[str, tuple[str, ...]]
    variant_joiners: dict[str, tuple[str, ...]]
    families: dict[tuple[str, str, str], tuple[Family, ...]]  # (intent, shape, language)


def load_phrasebook(path: Path = PHRASEBOOK_PATH) -> Phrasebook:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    families: dict[tuple[str, str, str], tuple[Family, ...]] = {}
    for intent, shapes in raw["families"].items():
        for shape, languages in shapes.items():
            for language, groups in languages.items():
                families[(intent, shape, language)] = tuple(
                    Family(f"{intent}.{shape}.{language}.{i}", intent, shape, language, tuple(g))
                    for i, g in enumerate(groups, start=1)
                )
    book = Phrasebook(
        service_names={
            k: {lg: tuple(v) for lg, v in d.items()} for k, d in raw["service_names"].items()
        },
        variants={k: {lg: tuple(v) for lg, v in d.items()} for k, d in raw["variants"].items()},
        variant_frames={k: tuple(v) for k, v in raw["variant_frames"].items()},
        variant_joiners={k: tuple(v) for k, v in raw["variant_joiners"].items()},
        families=families,
    )
    problems = check_phrasebook(book)
    if problems:
        raise PhrasebookError("; ".join(problems))
    return book


def check_phrasebook(book: Phrasebook, graph: InMemoryGraph | None = None) -> list[str]:
    """Everything that could make the generator fail or produce a bad phrase."""
    graph = graph or InMemoryGraph.from_dir()
    problems: list[str] = []
    for svc in graph.seed.services:
        for lang in ("en", "fil"):
            if not book.service_names.get(svc.id, {}).get(lang):
                problems.append(f"no {lang} name for service {svc.id}")
    for extra in set(book.service_names) - {s.id for s in graph.seed.services}:
        problems.append(f"phrasebook names an unknown service {extra}")
    for v in graph.seed.variants:
        for lang in ("en", "fil"):
            if not book.variants.get(v.id, {}).get(lang):
                problems.append(f"no {lang} phrase for variant {v.id}")
    for lang in LANGUAGES:
        if not book.variant_frames.get(lang) or not book.variant_joiners.get(lang):
            problems.append(f"no variant frames or joiners for {lang}")
        for frame in book.variant_frames.get(lang, ()):
            if "{base}" not in frame or "{variant}" not in frame:
                problems.append(f"variant frame {frame!r} needs {{base}} and {{variant}}")
    wanted = {(i, s) for (i, s, filtered) in T.TEMPLATES if not filtered}
    have = {(i, s) for (i, s, _) in book.families}
    for missing in sorted(wanted - have):
        problems.append(f"no phrase families for {missing}")
    for extra in sorted(have - wanted):
        problems.append(f"phrase families for {extra}, which has no template")
    for (intent, shape, lang), fams in book.families.items():
        if lang not in LANGUAGES:
            problems.append(f"unknown language {lang!r} in {intent}.{shape}")
        if len(fams) < 3:
            problems.append(f"{intent}.{shape}.{lang} needs at least 3 families to be split")
        for fam in fams:
            if not fam.templates:
                problems.append(f"family {fam.id} is empty")
            for tpl in fam.templates:
                holders = _PLACEHOLDER.findall(tpl)
                if holders != ["service"]:
                    problems.append(f"{fam.id}: {tpl!r} must contain exactly one {{service}}")
                stripped = _ALTERNATIVES.sub("", tpl)
                if "<" in stripped or ">" in stripped:
                    problems.append(f"{fam.id}: unbalanced <a|b> in {tpl!r}")
    return problems


def review_strings(book: Phrasebook) -> list[str]:
    """Every Filipino or Taglish string in the generator, in a stable order (NEEDS-NATIVE-REVIEW)."""
    out: list[str] = []
    for svc in sorted(book.service_names):
        out += [f"service name [{svc}]: {n}" for n in book.service_names[svc].get("fil", ())]
    for vid in sorted(book.variants):
        out += [f"variant phrase [{vid}]: {n}" for n in book.variants[vid].get("fil", ())]
    for lang in ("fil", "mixed"):
        out += [f"variant frame [{lang}]: {f}" for f in book.variant_frames[lang]]
        out += [f"variant joiner [{lang}]: {j!r}" for j in book.variant_joiners[lang]]
    for key in sorted(book.families):
        if key[2] in ("fil", "mixed"):
            for fam in book.families[key]:
                out += [f"family {fam.id}: {t}" for t in fam.templates]
    out += [f"sms spelling: {k} -> {v}" for k, v in sorted(SMS_FIL.items())]
    return out


def load_aliases(
    graph: InMemoryGraph, path: Path = ALIASES_PATH
) -> dict[str, dict[str, list[str]]]:
    """Service aliases from ``graph/seed/aliases.yaml`` when that file exists.

    Another session owns that file and its format was not fixed when this was written, so the
    reader is tolerant: a top-level list, or a mapping with an ``aliases`` list, of records with
    ``text``, ``lang`` (en|fil) and the service id under ``service_id``, ``target_id``, ``target``
    or ``for``. Records it cannot read are skipped; nothing here can fail the generator.
    """
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    records = data.get("aliases", []) if isinstance(data, dict) else data
    known = {s.id for s in graph.seed.services}
    out: dict[str, dict[str, list[str]]] = {}
    for rec in records if isinstance(records, list) else []:
        if not isinstance(rec, dict):
            continue
        sid = next((rec[k] for k in ("service_id", "target_id", "target", "for") if k in rec), None)
        text, lang = rec.get("text"), rec.get("lang")
        if sid in known and isinstance(text, str) and text.strip() and lang in ("en", "fil"):
            out.setdefault(sid, {}).setdefault(lang, []).append(" ".join(text.split()))
    return out


# ---- cells ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Cell:
    service_id: str
    intent: str
    shape: str
    combo: tuple[tuple[str, str], ...]  # sorted (dimension, value) pairs


def variant_combos(graph: InMemoryGraph, service_id: str) -> list[tuple[tuple[str, str], ...]]:
    """Every selection of at most one value per dimension that the service's records link."""
    dims: dict[str, set[str]] = {}
    for rec in (*graph.requirements(service_id), *graph.fees(service_id)):
        for vid in rec.variant_ids:
            dimension, _, value = vid.partition(":")
            dims.setdefault(dimension, set()).add(value)
    names = sorted(dims)
    options = [[None, *sorted(dims[d])] for d in names]
    combos = []
    for choice in product(*options):
        combos.append(tuple((d, v) for d, v in zip(names, choice, strict=True) if v is not None))
    return combos


def withheld_combos(
    graph: InMemoryGraph, service_id: str, seed: int
) -> set[tuple[tuple[str, str], ...]]:
    """Non-empty combinations kept out of train (only for services with at least 3 of them)."""
    nonempty = [c for c in variant_combos(graph, service_id) if c]
    if len(nonempty) < 3:
        return set()
    rng = random.Random(f"{seed}|withheld|{service_id}")
    return set(rng.sample(nonempty, max(1, round(len(nonempty) / 3))))


def _has_go_first_data(graph: InMemoryGraph, service_id: str) -> bool:
    for req in graph.requirements(service_id):
        if graph.satisfied_by(req.id):
            return True
        if req.secured_at and graph.office_for_agency(req.secured_at):
            return True
    return False


def enumerate_cells(graph: InMemoryGraph) -> list[Cell]:
    cells = []
    for svc in graph.seed.services:
        leaf_requirements = [r for r in graph.requirements(svc.id) if not r.group]
        has = {
            ("requirements", "count"): bool(leaf_requirements),
            ("fees", "per_step"): any(f.step_id for f in graph.fees(svc.id)),
            ("where_to_secure", "go_first"): _has_go_first_data(graph, svc.id),
        }
        shapes = [
            (intent, shape)
            for intent in T.CORE1_INTENTS
            for shape in T.shapes_for(intent)
            if has.get((intent, shape), True)
        ]
        for combo in variant_combos(graph, svc.id):
            cells += [Cell(svc.id, intent, shape, combo) for intent, shape in shapes]
    return cells


# ---- splits ---------------------------------------------------------------------------------------


def assign_splits(book: Phrasebook, seed: int) -> dict[str, str]:
    """Family id -> split. In every (intent, shape, language) group one family goes to
    test_synthetic, one to validation and the rest to train."""
    out: dict[str, str] = {}
    for fams in book.families.values():
        ordered = sorted(fams, key=lambda f: hashlib.sha256(f"{seed}|{f.id}".encode()).hexdigest())
        out[ordered[0].id] = "test_synthetic"
        out[ordered[1].id] = "validation"
        for fam in ordered[2:]:
            out[fam.id] = "train"
    return out


# ---- phrases --------------------------------------------------------------------------------------


def _expand(template: str, rng: random.Random) -> str:
    return _ALTERNATIVES.sub(lambda m: rng.choice(m.group(1).split("|")), template)


def _service_name(
    rng: random.Random,
    book: Phrasebook,
    aliases: dict[str, dict[str, list[str]]],
    graph: InMemoryGraph,
    service_id: str,
    language: str,
) -> str:
    names = book.service_names[service_id]
    extra = aliases.get(service_id, {})
    en = [*names["en"], *extra.get("en", ())]
    fil = [*names["fil"], *extra.get("fil", ())]
    pool = {"en": en, "fil": fil, "mixed": en + fil}[language]
    if language != "fil" and rng.random() < OFFICIAL_NAME_SHARE:
        return " ".join(graph.service(service_id).name.split())
    return rng.choice(pool)


def _variant_text(rng: random.Random, book: Phrasebook, combo, language: str) -> str:
    parts = []
    for dimension, value in combo:
        forms = book.variants[f"{dimension}:{value}"]
        lang = rng.choice(("en", "fil")) if language == "mixed" else language
        parts.append(rng.choice(forms[lang]))
    return rng.choice(book.variant_joiners[language]).join(parts)


def build_phrase(
    rng: random.Random,
    book: Phrasebook,
    aliases: dict[str, dict[str, list[str]]],
    graph: InMemoryGraph,
    family: Family,
    cell: Cell,
) -> str:
    """The clean (noise-free) citizen phrase for one cell and family."""
    name = _service_name(rng, book, aliases, graph, cell.service_id, family.language)
    text = _expand(rng.choice(family.templates), rng).replace("{service}", name)
    if cell.combo and rng.random() < VARIANT_MENTION_SHARE:
        end = "?" if text.endswith("?") else ""
        base = text.rstrip("?. ")
        variant = _variant_text(rng, book, cell.combo, family.language)
        frame = rng.choice(book.variant_frames[family.language])
        text = frame.replace("{base}", base).replace("{variant}", variant) + end
    return " ".join(text.split())


# ---- dataset --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Example:
    id: str
    split: str
    slots: Slots
    shape: str
    template_key: str  # "intent/shape/filtered"
    noise: int
    family: str
    combo_withheld: bool
    clean_phrase: str
    system: str
    user: str
    cypher: str
    params: dict[str, Any]
    tokens: int

    def messages(self) -> dict[str, Any]:
        return {
            "messages": [
                {"role": "system", "content": self.system},
                {"role": "user", "content": self.user},
                {"role": "assistant", "content": self.cypher},
            ]
        }

    def meta(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "split": self.split,
            "service_id": self.slots.service_id,
            "intent": self.slots.intent,
            "shape": self.shape,
            "template": self.template_key,
            "variants": dict(sorted(self.slots.variants.items())),
            "language": self.slots.language,
            "noise": self.noise,
            "family": self.family,
            "combo_withheld": self.combo_withheld,
            "clean_phrase": self.clean_phrase,
            "params": self.params,
            "prompt_tokens": self.tokens,
        }


@dataclass
class Dataset:
    seed: int
    examples: dict[str, list[Example]]
    family_split: dict[str, str]
    withheld: dict[str, list[dict[str, str]]]
    aliases_used: int
    train_rounds: int
    eval_fraction: float
    cells: int
    schema_fingerprint: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


def schema_fingerprint() -> str:
    text = json.dumps(
        [
            sorted(OFFICIAL_SCHEMA.labels),
            sorted(OFFICIAL_SCHEMA.relationship_types),
            sorted(OFFICIAL_SCHEMA.properties),
        ]
    )
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def _dedupe_key(slots: Slots, shape: str) -> tuple:
    return (
        slots.service_id,
        slots.intent,
        shape,
        tuple(sorted(slots.variants.items())),
        slots.language,
        " ".join(slots.phrase.casefold().split()),
    )


def build_dataset(
    seed: int = 0,
    *,
    train_rounds: int = 2,
    eval_fraction: float = 0.15,
    book: Phrasebook | None = None,
    graph: InMemoryGraph | None = None,
) -> Dataset:
    graph = graph or InMemoryGraph.from_dir()
    book = book or load_phrasebook()
    aliases = load_aliases(graph)
    cells = enumerate_cells(graph)
    family_split = assign_splits(book, seed)
    withheld = {s.id: withheld_combos(graph, s.id, seed) for s in graph.seed.services}
    slices: dict[str, SchemaSlice] = {i: schema_slice(i) for i in T.CORE1_INTENTS}

    examples: dict[str, list[Example]] = {split: [] for split in SPLITS}
    seen: set[tuple] = set()
    for split in SPLITS:
        rounds = train_rounds if split == "train" else 1
        for cell in cells:
            is_withheld = cell.combo in withheld[cell.service_id]
            if split == "train" and is_withheld:
                continue
            if split != "train" and not is_withheld:
                keep = random.Random(f"{seed}|keep|{split}|{cell}").random()
                if keep >= eval_fraction:
                    continue
            for language in LANGUAGES:
                families = [
                    f
                    for f in book.families[(cell.intent, cell.shape, language)]
                    if family_split[f.id] == split
                ]
                for level in NOISE_LEVELS:
                    for rnd in range(rounds):
                        rng = random.Random(f"{seed}|{split}|{cell}|{language}|{level}|{rnd}")
                        family = rng.choice(families)
                        clean = build_phrase(rng, book, aliases, graph, family, cell)
                        phrase = " ".join(add_noise(clean, level, rng).split()) or clean
                        slots = Slots(
                            service_id=cell.service_id,
                            intent=cell.intent,
                            variants=dict(cell.combo),
                            phrase=phrase,
                            language=language,
                        )
                        key = _dedupe_key(slots, cell.shape)
                        if key in seen:
                            continue
                        seen.add(key)
                        template = T.select_template(slots, cell.shape)
                        prompt = build_prompt(slots, slices[cell.intent])
                        query = T.build_query(slots, cell.shape)
                        examples[split].append(
                            Example(
                                id="",
                                split=split,
                                slots=slots,
                                shape=cell.shape,
                                template_key="/".join(
                                    (
                                        template.intent,
                                        template.shape,
                                        str(template.filtered).lower(),
                                    )
                                ),
                                noise=level,
                                family=family.id,
                                combo_withheld=is_withheld,
                                clean_phrase=clean,
                                system=prompt.system,
                                user=prompt.user,
                                cypher=query.cypher,
                                params=query.params,
                                tokens=prompt.tokens,
                            )
                        )
    # stable ids, assigned after generation so they do not depend on the loop layout
    for split, rows in examples.items():
        examples[split] = [
            Example(**{**row.__dict__, "id": f"{split}-{i:05d}"}) for i, row in enumerate(rows)
        ]
    return Dataset(
        seed=seed,
        examples=examples,
        family_split=family_split,
        withheld={
            sid: [dict(c) for c in sorted(combos)] for sid, combos in withheld.items() if combos
        },
        aliases_used=sum(len(v) for langs in aliases.values() for v in langs.values()),
        train_rounds=train_rounds,
        eval_fraction=eval_fraction,
        cells=len(cells),
        schema_fingerprint=schema_fingerprint(),
    )


# ---- output ---------------------------------------------------------------------------------------


def _dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def jsonl(rows: list[Example], *, meta: bool = False) -> str:
    """Stable text: one JSON object per line, ``\\n`` newlines on every platform."""
    return "".join(_dump(r.meta() if meta else r.messages()) + "\n" for r in rows)


def write_dataset(ds: Dataset, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for split, rows in ds.examples.items():
        for meta in (False, True):
            path = out_dir / f"{split}{'.meta' if meta else ''}.jsonl"
            with path.open("w", encoding="utf-8", newline="\n") as fh:
                fh.write(jsonl(rows, meta=meta))
            written.append(path)
    return written


def pick_sample(ds: Dataset, size: int = SAMPLE_SIZE) -> list[Example]:
    """About ``size`` examples covering every intent/shape, language, noise level and split."""
    rng = random.Random(f"{ds.seed}|sample")
    chosen: list[Example] = []
    taken: set[str] = set()

    def take(pool: list[Example], n: int) -> None:
        pool = [e for e in pool if e.id not in taken]
        for e in rng.sample(pool, min(n, len(pool))):
            taken.add(e.id)
            chosen.append(e)

    everything = [e for split in SPLITS for e in ds.examples[split]]
    keys = sorted({(e.slots.intent, e.shape) for e in everything})
    for intent, shape in keys:
        for language in LANGUAGES:
            take(
                [
                    e
                    for e in ds.examples["train"]
                    if (e.slots.intent, e.shape, e.slots.language) == (intent, shape, language)
                ],
                1,
            )
    for split in ("validation", "test_synthetic"):
        for intent, shape in keys:
            take([e for e in ds.examples[split] if (e.slots.intent, e.shape) == (intent, shape)], 1)
    for level in NOISE_LEVELS:
        take([e for e in everything if e.noise == level and e.slots.variants], 2)
    take([e for e in everything if e.combo_withheld], 2)
    return sorted(chosen, key=lambda e: (SPLITS.index(e.split), e.id))[: size + 10]


def _table(title: str, rows: dict[str, dict[str, int]], columns: list[str]) -> list[str]:
    lines = [
        f"### {title}",
        "",
        "| | " + " | ".join(columns) + " | total |",
        "|---|" + "---:|" * (len(columns) + 1),
    ]
    for name, counts in rows.items():
        cells = [str(counts.get(c, 0)) for c in columns]
        lines.append(f"| {name} | " + " | ".join(cells) + f" | {sum(counts.values())} |")
    return [*lines, ""]


def _p(*parts: str) -> str:
    """One paragraph written as several source strings."""
    return "".join(parts)


def dataset_card(ds: Dataset) -> str:
    """The text of training/DATASET_CARD.md (generated; contains no timestamps)."""
    every = [e for s in SPLITS for e in ds.examples[s]]

    def counts(key) -> dict[str, dict[str, int]]:
        out: dict[str, Counter] = {}
        for e in every:
            out.setdefault(str(key(e)), Counter())[e.split] += 1
        return {k: dict(v) for k, v in sorted(out.items())}

    def kind(e: Example) -> str:
        return "filtered" if e.template_key.endswith("true") else "plain"

    def variant_use(e: Example) -> str:
        return "with variants" if e.slots.variants else "no variants"

    fam_counts = {s: sum(1 for v in ds.family_split.values() if v == s) for s in SPLITS}
    tokens = [e.tokens for e in every]
    alias_note = "" if ds.aliases_used else " (file absent or no readable records)"
    withheld_lines = [
        f"- `{sid}`: " + "; ".join(", ".join(f"{d}={v}" for d, v in c.items()) for c in combos)
        for sid, combos in sorted(ds.withheld.items())
    ]
    lines = [
        "# Dataset card: Core 1 synthetic Text-to-Cypher data",
        "",
        _p(
            "Generated by `python -m training.generate_dataset` (do not edit by hand; ",
            "regenerate). Everything comes from our own templates, rules and noise injection: ",
            "no LLM or API wrote an example, the held-out inquiries were never read, and ",
            "examples hold only questions and Cypher (no answer text from the charters).",
        ),
        "",
        "## Settings",
        "",
        _p(
            f"- seed: {ds.seed}; train rounds: {ds.train_rounds}; ",
            f"validation/test share of ordinary cells: {ds.eval_fraction}",
        ),
        f"- cells (service x intent/shape x variant combination): {ds.cells}",
        _p(
            f"- guardrail schema fingerprint: `{ds.schema_fingerprint}` ",
            "(labels, relationship types and properties read at runtime)",
        ),
        f"- alias records used from `graph/seed/aliases.yaml`: {ds.aliases_used}{alias_note}",
        f"- noise levels (percent of words): {', '.join(str(n) for n in NOISE_LEVELS)}",
        _p(
            f"- prompt budget: estimated tokens max {max(tokens)}, ",
            f"mean {sum(tokens) / len(tokens):.0f} (ceiling {MAX_PROMPT_TOKENS})",
        ),
        "",
        "## Counts",
        "",
        "| split | examples |",
        "|---|---:|",
        *[f"| {s} | {len(ds.examples[s])} |" for s in SPLITS],
        f"| **all** | **{len(every)}** |",
        "",
    ]
    columns = list(SPLITS)
    lines += _table("By intent", counts(lambda e: e.slots.intent), columns)
    lines += _table(
        "By shape (query template)", counts(lambda e: f"{e.slots.intent}/{e.shape}"), columns
    )
    lines += _table("By language", counts(lambda e: e.slots.language), columns)
    lines += _table("By noise level", counts(lambda e: e.noise), columns)
    lines += _table("By variant use", counts(variant_use), columns)
    lines += _table("By gold query kind", counts(kind), columns)
    lines += [
        "## Splits",
        "",
        _p(
            "Split by phrase-template family (paraphrases of one wording stay together): ",
            ", ".join(f"{s}: {n} families" for s, n in fam_counts.items()),
            ". In each (intent, shape, language) group one family is in test_synthetic, one in ",
            "validation and the rest in train. No family is in two splits, and no example ",
            "prompt is identical across splits.",
        ),
        "",
        "Variant combinations withheld from train (present only in validation and test):",
        "",
        *withheld_lines,
        "",
        _p(
            "Examples whose combination is withheld: ",
            f"{sum(1 for e in every if e.combo_withheld)} (validation/test only).",
        ),
        "",
        "## What is in an example",
        "",
        _p(
            '`{"messages": [system, user, assistant]}`: the system message is the fixed ',
            "instruction plus the schema slice of the intent, the user message lists service, ",
            "intent, variants, language and the noisy phrase, and the assistant message is the ",
            "canonical Cypher with `$sid` / `$variant_ids` (never literal ids). A parallel ",
            "`<split>.meta.jsonl` (same line order) holds id, shape, noise level, family, ",
            "clean phrase and query parameters.",
        ),
        "",
        "## Known limits",
        "",
        _p(
            "- Filipino and Taglish wording is unreviewed (NEEDS-NATIVE-REVIEW); the list is in ",
            "`docs/training_notes.md`.",
        ),
        _p(
            "- The shape (list, count, per_step, go_first) must be inferred from the wording ",
            "alone; the variant filter depends on whether variants are given, and steps, times, ",
            "offices and who-may-avail ignore variants (no variant links in the graph).",
        ),
        _p(
            "- Service names are colloquial names plus the official names; aliases from ",
            "`graph/seed/aliases.yaml` are used when that file exists.",
        ),
        _p(
            "- Phrases are short single questions: no multi-request messages, no gibberish, no ",
            "out-of-scope or mutation requests (those are handled before the model).",
        ),
        "",
    ]
    return "\n".join(lines)


def write_docs(ds: Dataset, directory: Path = TRAINING_DIR) -> list[Path]:
    sample_dir = directory / "sample"
    sample_dir.mkdir(parents=True, exist_ok=True)
    rows = pick_sample(ds)
    paths = []
    for meta in (False, True):
        path = sample_dir / f"sample{'.meta' if meta else ''}.jsonl"
        with path.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(jsonl(rows, meta=meta))
        paths.append(path)
    card = directory / "DATASET_CARD.md"
    with card.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(dataset_card(ds))
    return [*paths, card]


# ---- command line ---------------------------------------------------------------------------------

REVIEW_BEGIN = "<!-- BEGIN REVIEW LIST (generated: python -m training.generate_dataset --write-review-list) -->"
REVIEW_END = "<!-- END REVIEW LIST -->"


def render_review_block(book: Phrasebook) -> str:
    items = review_strings(book)
    body = "\n".join(f"{i}. {s}" for i, s in enumerate(items, start=1))
    return f"{REVIEW_BEGIN}\n\n{body}\n\n{REVIEW_END}"


def write_review_list(notes: Path, book: Phrasebook) -> None:
    text = notes.read_text(encoding="utf-8")
    start, end = text.index(REVIEW_BEGIN), text.index(REVIEW_END) + len(REVIEW_END)
    notes.write_text(text[:start] + render_review_block(book) + text[end:], encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="where the JSONL files go")
    ap.add_argument(
        "--docs-dir", type=Path, default=TRAINING_DIR, help="where sample/ and DATASET_CARD.md go"
    )
    ap.add_argument("--no-docs", action="store_true", help="do not write the sample and the card")
    ap.add_argument("--train-rounds", type=int, default=2)
    ap.add_argument("--eval-fraction", type=float, default=0.15)
    ap.add_argument(
        "--list-review",
        action="store_true",
        help="print the Filipino strings that need native review and exit",
    )
    ap.add_argument(
        "--write-review-list",
        type=Path,
        metavar="NOTES_MD",
        help="refresh the generated review list inside the notes file and exit",
    )
    args = ap.parse_args(argv)

    if args.list_review or args.write_review_list:
        book = load_phrasebook()
        if args.write_review_list:
            write_review_list(args.write_review_list, book)
        else:
            print(render_review_block(book))
        return 0

    started = time.perf_counter()
    ds = build_dataset(args.seed, train_rounds=args.train_rounds, eval_fraction=args.eval_fraction)
    paths = write_dataset(ds, args.out)
    if not args.no_docs:
        paths += write_docs(ds, args.docs_dir)
    for split in SPLITS:
        print(f"{split}: {len(ds.examples[split])} examples")
    print(f"wrote {len(paths)} files in {time.perf_counter() - started:.1f}s", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
