"""Deterministic training-data generator for Core 1 (Text-to-Cypher), redesigned in session 5b.

Run from the repo root:

    python -m training.generate_dataset --seed 0

Everything is produced by our own code: phrase templates (``phrasebook*.yaml``), noise injection
(``noise.py``), gold Cypher from ``core1/templates.py``, model input from ``core1/prompt.py``. No
LLM or API is called, ``eval/heldout/`` is never read, and examples hold only questions and
Cypher: no answer text from the charters. The allowed labels, relationship types and properties
are read from ``guardrail/schema.py`` at runtime.

What changed from session 5. The model used to be given the intent and the variants, so its output
was a function of the prompt and fine-tuning would have taught a lookup table (17 distinct
queries). Now (prompt v2) it receives only the linked TARGETS (service, office, agency, document),
the language and the cleaned phrase. It has to work out from the wording:

* the INTENT (and whether the question asks for two things at once: "magkano at gaano katagal"),
* the query SHAPE (38 canonical queries: lists, counts, totals, comparisons, reverse lookups,
  office listings, cross-office prerequisites, ...),
* the VARIANTS the citizen stated (``business_type:corporation``), which become the filter,
* and which target fills which parameter (``$sid`` / ``$sid2`` / ``$oid`` / ``$aid`` / ``$doc``).

The completion is three header lines (intent, shape, variants) and the Cypher (``core1/output.py``).
The same examples are also written with the intent and variants GIVEN in the prompt
(``out/slots_given/``): the "slots given" side of the ablation.

One example = cell (shape x targets x variants stated) x language x noise level x family. The phrase
is built from a template family, given noise at 0, 10 or 30 percent, and then cleaned the way the
gateway cleans text (lower case, ASCII words, no punctuation, at most 160 characters). Entity words
(names of services, offices, agencies, documents and variants) are not given noise: the gateway's
lexicon repairs those before the model sees them.

Splits (``train``, ``validation``, ``test_synthetic``) are by phrase-template family: no family is
in two splits. Some variant combinations are withheld from train. Two rare shapes (``office_who``,
``compare_time``) are held out entirely as ``test_unseen_shape``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from citizengraph.core1 import templates as T
from citizengraph.core1.output import format_completion
from citizengraph.core1.prompt import (
    MAX_PHRASE_CHARS_V2,
    MAX_PROMPT_TOKENS,
    build_prompt_slots_given,
    build_prompt_v2,
)
from citizengraph.core1.slots import LANGUAGES
from citizengraph.core1.targets import Request, build_request_query
from citizengraph.gateway.text import fold, is_word, tokenize
from citizengraph.graph import InMemoryGraph
from citizengraph.guardrail.schema import OFFICIAL_SCHEMA
from training.cells import (
    HELD_OUT_SHAPES,
    Cell,
    enumerate_cells,
    has_go_first_data,
    variant_combos,
    withheld_combos,
)
from training.noise import NOISE_LEVELS, add_noise
from training.phrasebook import (
    ALIASES_PATH,
    PHRASEBOOK_PATHS,
    VARIANT_MENTION_SHARE,
    Family,
    Phrasebook,
    PhrasebookError,
    build_phrase,
    check_phrasebook,
    load_aliases,
    load_phrasebook,
    review_strings,
)

ROOT = Path(__file__).resolve().parents[1]
TRAINING_DIR = Path(__file__).resolve().parent
DEFAULT_OUT = TRAINING_DIR / "out"
UNSEEN = "test_unseen_shape"
SPLITS = ("train", "validation", "test_synthetic", UNSEEN)
EVAL_SPLITS = SPLITS[1:]
SAMPLE_SIZE = 70
MIN_EVAL_CELLS = 6  # see build_dataset

__all__ = [
    "ALIASES_PATH",
    "HELD_OUT_SHAPES",
    "PHRASEBOOK_PATHS",
    "SPLITS",
    "UNSEEN",
    "Dataset",
    "Example",
    "Family",
    "Phrasebook",
    "PhrasebookError",
    "build_dataset",
    "check_phrasebook",
    "enumerate_cells",
    "has_go_first_data",
    "load_aliases",
    "load_phrasebook",
    "main",
    "review_strings",
    "variant_combos",
]


def gateway_clean(text: str, max_chars: int = MAX_PHRASE_CHARS_V2) -> str:
    """The phrase as the gateway hands it over: lower-case ASCII words, no punctuation, apostrophes
    and hyphens dropped, at most ``max_chars`` (``gateway.max_phrase_chars``). No typo repair here
    (the gateway repairs some typos; leaving them makes the model's job harder, not easier)."""
    words = [t for t in tokenize(fold(text)) if is_word(t)]
    return " ".join(words)[:max_chars].rstrip()


# ---- splits -----------------------------------------------------------------------------------


def assign_splits(
    book: Phrasebook, seed: int, held_out: frozenset[str] = HELD_OUT_SHAPES
) -> dict[str, str]:
    """Family id -> split. In every (intent, shape, language) group one family goes to
    test_synthetic, one to validation and the rest to train; every family of a held-out shape goes
    to test_unseen_shape."""
    out: dict[str, str] = {}
    for (_, shape, _), fams in book.families.items():
        if shape in held_out:
            out.update({f.id: UNSEEN for f in fams})
            continue
        ordered = sorted(fams, key=lambda f: hashlib.sha256(f"{seed}|{f.id}".encode()).hexdigest())
        out[ordered[0].id] = "test_synthetic"
        out[ordered[1].id] = "validation"
        out.update({f.id: "train" for f in ordered[2:]})
    return out


# ---- dataset ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Example:
    id: str
    split: str
    request: Request
    intent_header: str  # "fees" or "fees+processing_time"
    shape: str
    variant_ids: tuple[str, ...]
    template_key: str  # "intent/shape/filtered"
    noise: int
    family: str
    combo_withheld: bool
    raw_phrase: str  # the question before noise and cleaning
    system: str
    user: str  # prompt v2: targets, language, phrase
    user_slots_given: str  # the same plus the intent and variants
    completion: str  # three header lines and the Cypher
    cypher: str
    params: dict[str, Any]
    tokens: int

    @property
    def intents(self) -> tuple[str, ...]:
        return tuple(self.intent_header.split("+"))

    @property
    def language(self) -> str:
        return self.request.language

    @property
    def targets_text(self) -> str:
        return ", ".join(str(t) for t in self.request.targets)

    def messages(self, *, slots_given: bool = False) -> dict[str, Any]:
        return {
            "messages": [
                {"role": "system", "content": self.system},
                {"role": "user", "content": self.user_slots_given if slots_given else self.user},
                {"role": "assistant", "content": self.completion},
            ]
        }

    def meta(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "split": self.split,
            "intent": self.intent_header,
            "shape": self.shape,
            "template": self.template_key,
            "variants": list(self.variant_ids),
            "language": self.language,
            "noise": self.noise,
            "family": self.family,
            "targets": [str(t) for t in self.request.targets],
            "combo_withheld": self.combo_withheld,
            "raw_phrase": self.raw_phrase,
            "phrase": self.request.phrase,
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
    held_out: tuple[str, ...]
    schema_fingerprint: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def all(self) -> list[Example]:
        return [e for s in SPLITS for e in self.examples[s]]


def schema_fingerprint() -> str:
    text = json.dumps(
        [
            sorted(OFFICIAL_SCHEMA.labels),
            sorted(OFFICIAL_SCHEMA.relationship_types),
            sorted(OFFICIAL_SCHEMA.properties),
        ]
    )
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def _dedupe_key(request: Request, completion: str) -> tuple:
    return (request.targets, request.language, request.phrase, completion)


def _make_example(
    split: str,
    cell: Cell,
    family: Family,
    level: int,
    rng: random.Random,
    book: Phrasebook,
    aliases,
    graph: InMemoryGraph,
    withheld: bool,
) -> Example:
    mention = cell.filtered or rng.random() < VARIANT_MENTION_SHARE
    raw, protect = build_phrase(
        rng, book, aliases, graph, family, cell.entity_map, cell.combo, mention
    )
    noisy = add_noise(raw, level, rng, protect)
    phrase = gateway_clean(noisy) or gateway_clean(raw)
    request = Request(targets=cell.targets, phrase=phrase, language=family.language)

    variant_ids = tuple(sorted(f"{d}:{v}" for d, v in cell.combo)) if cell.filtered else ()
    template = T.TEMPLATES[(cell.intent, cell.shape, cell.filtered)]
    query = build_request_query(request, cell.intent, cell.shape, variant_ids)
    prompt = build_prompt_v2(request)
    given = build_prompt_slots_given(
        request, template.intent_header, dict(cell.combo) if cell.filtered else {}
    )
    return Example(
        id="",
        split=split,
        request=request,
        intent_header=template.intent_header,
        shape=cell.shape,
        variant_ids=variant_ids,
        template_key=f"{cell.intent}/{cell.shape}/{str(cell.filtered).lower()}",
        noise=level,
        family=family.id,
        combo_withheld=withheld,
        raw_phrase=raw,
        system=prompt.system,
        user=prompt.user,
        user_slots_given=given.user,
        completion=format_completion(template, variant_ids),
        cypher=query.cypher,
        params=query.params,
        tokens=prompt.tokens,
    )


def build_dataset(
    seed: int = 0,
    *,
    train_rounds: int = 1,
    eval_fraction: float = 0.15,
    book: Phrasebook | None = None,
    graph: InMemoryGraph | None = None,
    held_out: frozenset[str] = HELD_OUT_SHAPES,
) -> Dataset:
    graph = graph or InMemoryGraph.from_dir()
    book = book or load_phrasebook()
    problems = check_phrasebook(book, graph, held_out)
    if problems:
        raise PhrasebookError("; ".join(problems))
    aliases = load_aliases(graph)
    cells = enumerate_cells(graph, book, seed)
    family_split = assign_splits(book, seed, held_out)
    withheld = {s.id: withheld_combos(graph, s.id, seed) for s in graph.seed.services}

    def is_withheld(cell: Cell) -> bool:
        sid = next((t.id for t in cell.targets if t.kind == "service"), None)
        return bool(cell.combo) and sid is not None and cell.combo in withheld.get(sid, set())

    per_shape = Counter((c.intent, c.shape) for c in cells)

    def keep_share(cell: Cell) -> float:
        """Share of a shape's ordinary cells kept for validation and test: ``eval_fraction``, but
        at least about MIN_EVAL_CELLS cells of a shape with few cells (an office has only 8)."""
        return max(eval_fraction, min(1.0, MIN_EVAL_CELLS / per_shape[(cell.intent, cell.shape)]))

    examples: dict[str, list[Example]] = {split: [] for split in SPLITS}
    seen: set[tuple] = set()
    for split in SPLITS:
        rounds = train_rounds if split == "train" else 1
        for cell in cells:
            if (cell.shape in held_out) != (split == UNSEEN):
                continue
            held = is_withheld(cell)
            if split == "train" and held:
                continue
            sampled_out = (
                split in ("validation", "test_synthetic")
                and not held
                and random.Random(f"{seed}|keep|{split}|{cell.key}").random() >= keep_share(cell)
            )
            if sampled_out:
                continue
            for language in LANGUAGES:
                families = [
                    f
                    for f in book.families[(cell.intent, cell.shape, language)]
                    if family_split[f.id] == split
                ]
                for level in NOISE_LEVELS:
                    for rnd in range(rounds):
                        rng = random.Random(f"{seed}|{split}|{cell.key}|{language}|{level}|{rnd}")
                        family = rng.choice(families)
                        example = _make_example(
                            split, cell, family, level, rng, book, aliases, graph, held
                        )
                        key = _dedupe_key(example.request, example.completion)
                        if key in seen:
                            continue
                        seen.add(key)
                        examples[split].append(example)
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
        held_out=tuple(sorted(held_out)),
        schema_fingerprint=schema_fingerprint(),
    )


# ---- non-triviality ------------------------------------------------------------------------------


def distinct_queries(rows: list[Example]) -> int:
    return len({e.cypher for e in rows})


def slots_only_ceiling(train: list[Example], test: list[Example]) -> float:
    """Exact-match rate of the best predictor that sees only the prompt's slots (the targets and
    the language, not the wording): for each (targets, language) it answers with the most common
    training completion. If the output were a function of the slots this would be near 1."""
    votes: dict[tuple, Counter] = defaultdict(Counter)
    kinds: dict[tuple, Counter] = defaultdict(Counter)
    for e in train:
        votes[(e.targets_text, e.language)][e.completion] += 1
        kinds[(tuple(t.kind for t in e.request.targets), e.language)][e.completion] += 1
    hits = 0
    for e in test:
        pool = votes.get((e.targets_text, e.language)) or kinds.get(
            (tuple(t.kind for t in e.request.targets), e.language)
        )
        hits += bool(pool) and pool.most_common(1)[0][0] == e.completion
    return hits / max(len(test), 1)


def completions_per_slot_group(rows: list[Example]) -> dict[str, int]:
    """For each (targets, language) group: how many different completions it leads to."""
    groups: dict[tuple, set[str]] = defaultdict(set)
    for e in rows:
        groups[(e.targets_text, e.language)].add(e.completion)
    return {f"{t} | {lang}": len(v) for (t, lang), v in groups.items()}


# ---- output -----------------------------------------------------------------------------------


def _dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def jsonl(rows: list[Example], *, meta: bool = False, slots_given: bool = False) -> str:
    """Stable text: one JSON object per line, ``\\n`` newlines on every platform."""
    return "".join(
        _dump(r.meta() if meta else r.messages(slots_given=slots_given)) + "\n" for r in rows
    )


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def write_dataset(ds: Dataset, out_dir: Path) -> list[Path]:
    """``<split>.jsonl`` (prompt v2), ``<split>.meta.jsonl`` and ``slots_given/<split>.jsonl``."""
    written = []
    for split, rows in ds.examples.items():
        for path, text in (
            (out_dir / f"{split}.jsonl", jsonl(rows)),
            (out_dir / f"{split}.meta.jsonl", jsonl(rows, meta=True)),
            (out_dir / "slots_given" / f"{split}.jsonl", jsonl(rows, slots_given=True)),
        ):
            _write(path, text)
            written.append(path)
    return written


def pick_sample(ds: Dataset, size: int = SAMPLE_SIZE) -> list[Example]:
    """About ``size`` examples covering every shape, language, noise level and split."""
    rng = random.Random(f"{ds.seed}|sample")
    chosen: list[Example] = []
    taken: set[str] = set()

    def take(pool: list[Example], n: int) -> None:
        pool = [e for e in pool if e.id not in taken]
        for e in rng.sample(pool, min(n, len(pool))):
            taken.add(e.id)
            chosen.append(e)

    keys = sorted({(e.intent_header, e.shape) for e in ds.all() if e.split != UNSEEN})
    for i, (intent, shape) in enumerate(keys):
        language = LANGUAGES[i % len(LANGUAGES)]
        in_shape = [
            e for e in ds.examples["train"] if (e.intent_header, e.shape) == (intent, shape)
        ]
        take([e for e in in_shape if e.language == language] or in_shape, 1)
        split = ("validation", "test_synthetic")[i % 2]  # one evaluation example per shape
        take([e for e in ds.examples[split] if (e.intent_header, e.shape) == (intent, shape)], 1)
    for shape in sorted(HELD_OUT_SHAPES):
        take([e for e in ds.examples[UNSEEN] if e.shape == shape], 3)
    for level in NOISE_LEVELS:
        take([e for e in ds.all() if e.noise == level and e.variant_ids], 2)
    take([e for e in ds.all() if e.combo_withheld], 2)
    return sorted(chosen, key=lambda e: (SPLITS.index(e.split), e.id))


# ---- dataset card -------------------------------------------------------------------------------


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
    every = ds.all()

    def counts(key) -> dict[str, dict[str, int]]:
        out: dict[str, Counter] = {}
        for e in every:
            out.setdefault(str(key(e)), Counter())[e.split] += 1
        return {k: dict(v) for k, v in sorted(out.items())}

    train, test = ds.examples["train"], ds.examples["test_synthetic"]
    ceiling = slots_only_ceiling(train, test)
    groups = completions_per_slot_group(every)
    service_groups = {k: v for k, v in groups.items() if k.startswith("service:")}
    fam_counts = {s: sum(1 for v in ds.family_split.values() if v == s) for s in SPLITS}
    tokens = [e.tokens for e in every]
    alias_note = "" if ds.aliases_used else " (file absent or no readable records)"
    withheld_lines = [
        f"- `{sid}`: " + "; ".join(", ".join(f"{d}={v}" for d, v in c.items()) for c in combos)
        for sid, combos in sorted(ds.withheld.items())
    ]
    lines = [
        "# Dataset card: Core 1 synthetic Text-to-Cypher data (prompt v2, slots inferred)",
        "",
        _p(
            "Generated by `python -m training.generate_dataset` (do not edit by hand; ",
            "regenerate). Everything comes from our own templates, rules and noise injection: ",
            "no LLM or API wrote an example, the held-out inquiries were never read, and ",
            "examples hold only questions and Cypher (no answer text from the charters).",
        ),
        "",
        "## What the model must learn",
        "",
        _p(
            "The prompt gives only the linked targets, the language and the cleaned phrase. The ",
            "model has to infer, from the wording, the intent (one or two), the query shape, ",
            "the variants the citizen states and which target fills which parameter, and then ",
            "write the Cypher. The same service with different wording leads to different ",
            "queries; the same wording with a different target kind (service, office, agency, ",
            "document) leads to a different query too. Ambiguity is deliberate: for example ",
            '"magkano at gaano katagal" asks for fee and time together (`fees+processing_time`).',
        ),
        "",
        _p(
            f"- distinct gold queries: {distinct_queries(every)} (train "
            f"{distinct_queries(train)}, validation "
            f"{distinct_queries(ds.examples['validation'])}, test_synthetic "
            f"{distinct_queries(test)}, test_unseen_shape "
            f"{distinct_queries(ds.examples[UNSEEN])}); distinct completions (header plus query): "
            f"{len({e.completion for e in every})}",
        ),
        _p(
            "- a predictor that sees only the slots (targets and language) and answers with the ",
            f"most common training completion scores {ceiling:.3f} exact match on test_synthetic ",
            "(if the output were a function of the slots this would be near 1)",
        ),
        _p(
            "- service-linked prompts lead to "
            f"{min(service_groups.values(), default=0)} to {max(service_groups.values(), default=0)} ",
            "different completions per (targets, language) group",
        ),
        _p(
            "- held out entirely (`test_unseen_shape`): "
            + ", ".join(f"`{s}`" for s in ds.held_out)
            + ". The model never sees these query shapes in training; the split measures ",
            "whether it still produces a valid, sensible query.",
        ),
        "",
        "## Settings",
        "",
        _p(
            f"- seed: {ds.seed}; train rounds: {ds.train_rounds}; ",
            f"validation/test share of ordinary cells: {ds.eval_fraction}",
        ),
        f"- cells (shape x targets x stated variants): {ds.cells}",
        _p(
            f"- guardrail schema fingerprint: `{ds.schema_fingerprint}` ",
            "(labels, relationship types and properties read at runtime)",
        ),
        f"- alias records used from `graph/seed/aliases.yaml`: {ds.aliases_used}{alias_note}",
        f"- noise levels (percent of words): {', '.join(str(n) for n in NOISE_LEVELS)}",
        _p(
            f"- prompt budget: estimated tokens max {max(tokens)}, ",
            f"mean {sum(tokens) / len(tokens):.0f} (ceiling {MAX_PROMPT_TOKENS}); the system ",
            "message is identical in every example",
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
    lines += _table("By intent", counts(lambda e: e.intent_header), columns)
    lines += _table(
        "By shape (query family)", counts(lambda e: f"{e.intent_header}/{e.shape}"), columns
    )
    lines += _table("By language", counts(lambda e: e.language), columns)
    lines += _table("By noise level", counts(lambda e: e.noise), columns)
    lines += _table(
        "By stated variants", counts(lambda e: "filter" if e.variant_ids else "no filter"), columns
    )
    lines += _table(
        "By target kinds",
        counts(lambda e: "+".join(t.kind for t in e.request.targets) or "none"),
        columns,
    )
    lines += [
        "## Splits",
        "",
        _p(
            "Split by phrase-template family (paraphrases of one wording stay together): ",
            ", ".join(f"{s}: {n} families" for s, n in fam_counts.items()),
            ". In each (intent, shape, language) group one family is in test_synthetic, one in ",
            "validation and the rest in train; every family of a held-out shape is in ",
            "test_unseen_shape. No family is in two splits, and no example is identical across ",
            "splits.",
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
            "instruction plus the whole schema (identical for every example); the user message ",
            "is `language`, `targets` and the cleaned phrase; the assistant message is the ",
            "intent, shape and variants header lines and the canonical Cypher with parameters ",
            "(never literal ids). `slots_given/<split>.jsonl` holds the same examples with the ",
            "intent and variants added to the prompt (the ablation). A parallel ",
            "`<split>.meta.jsonl` (same line order) holds id, shape, noise, family, the phrase ",
            "before noise, targets and query parameters.",
        ),
        "",
        "## Known limits",
        "",
        _p(
            "- The gold Cypher is still a fixed template per (intent, shape, filter): the model ",
            "learns to classify the wording and to pick the right template and parameters; it ",
            "does not compose new queries. `test_unseen_shape` measures composition.",
        ),
        _p(
            "- Filipino and Taglish wording is unreviewed (NEEDS-NATIVE-REVIEW); the list is in ",
            "`docs/training_notes.md`.",
        ),
        _p(
            "- Phrases are short single questions written by us: no multi-request messages, no ",
            "gibberish, no out-of-scope or mutation requests (the front end handles those). ",
            "Entity words carry no noise, because the gateway repairs them first.",
        ),
        _p(
            "- Agency, document and second-service targets are not produced by the session 4 ",
            "gateway yet (it links services and offices); see `docs/training_notes.md`.",
        ),
        _p(
            "- Validation and test contain more variant-bearing examples than train, because the ",
            "withheld combinations are always kept there.",
        ),
        "",
    ]
    return "\n".join(lines)


def write_docs(ds: Dataset, directory: Path = TRAINING_DIR) -> list[Path]:
    sample_dir = directory / "sample"
    rows = pick_sample(ds)
    paths = []
    for meta in (False, True):
        path = sample_dir / f"sample{'.meta' if meta else ''}.jsonl"
        _write(path, jsonl(rows, meta=meta))
        paths.append(path)
    card = directory / "DATASET_CARD.md"
    _write(card, dataset_card(ds))
    return [*paths, card]


# ---- command line -------------------------------------------------------------------------------

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
    ap.add_argument("--train-rounds", type=int, default=1)
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
