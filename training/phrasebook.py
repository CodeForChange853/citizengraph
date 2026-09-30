"""The phrase book: questions in English, Filipino and Taglish, and how a phrase is built.

Two YAML files hold the wording: ``phrasebook.yaml`` (session 5: the shapes every service has) and
``phrasebook_shapes.yaml`` (session 5b: the new shapes, and the names of offices, agencies and
documents). Every Filipino and Taglish string is DRAFT (NEEDS-NATIVE-REVIEW); ``review_strings``
lists them all for ``docs/training_notes.md``.

A *family* is a group of paraphrases that always travels into ONE split, so paraphrases cannot
leak from train into the evaluation sets. Family ids are
``<intent>.<shape>.<language>.<index starting at 1>``.

Only questions live here: no answer text from the charters. Names of services, offices, agencies
and documents are inputs to a query (what the citizen asked about), not answers.
"""

from __future__ import annotations

import random
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

from citizengraph.core1 import templates as T
from citizengraph.core1.slots import LANGUAGES
from citizengraph.graph import InMemoryGraph
from citizengraph.graph.ids import clean_name, slug
from training.noise import SMS_FIL

ROOT = Path(__file__).resolve().parents[1]
TRAINING_DIR = Path(__file__).resolve().parent
PHRASEBOOK_PATHS = (TRAINING_DIR / "phrasebook.yaml", TRAINING_DIR / "phrasebook_shapes.yaml")
ALIASES_PATH = ROOT / "graph" / "seed" / "aliases.yaml"

OFFICIAL_NAME_SHARE = 0.15  # how often the official service name is used as it is
VARIANT_MENTION_SHARE = 0.85  # for shapes that ignore variants: how often they are still said

_ALTERNATIVES = re.compile(r"<([^<>]*)>")
_PLACEHOLDER = re.compile(r"\{([^{}]*)\}")
PLACEHOLDER_OF = {
    "sid": "service",
    "sid2": "service2",
    "oid": "office",
    "aid": "agency",
    "doc": "document",
}


class PhrasebookError(ValueError):
    """The phrase book is malformed or does not cover the templates."""


@dataclass(frozen=True)
class Family:
    id: str  # "<intent>.<shape>.<language>.<n>"
    intent: str
    shape: str
    language: str
    templates: tuple[str, ...]


Names = dict[str, dict[str, tuple[str, ...]]]


@dataclass(frozen=True)
class Phrasebook:
    service_names: Names
    variants: Names
    variant_frames: dict[str, tuple[str, ...]]
    variant_joiners: dict[str, tuple[str, ...]]
    families: dict[tuple[str, str, str], tuple[Family, ...]]  # (intent, shape, language)
    office_names: Names
    agency_names: Names
    document_names: Names


def _names(raw: Mapping[str, Mapping[str, list[str]]] | None) -> Names:
    return {k: {lang: tuple(v) for lang, v in d.items()} for k, d in (raw or {}).items()}


def load_phrasebook(paths: tuple[Path, ...] = PHRASEBOOK_PATHS) -> Phrasebook:
    merged: dict = {"families": {}}
    for path in paths:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        for key, value in raw.items():
            if key == "families":
                for intent, shapes in value.items():
                    for shape, languages in shapes.items():
                        slot = merged["families"].setdefault(intent, {})
                        if shape in slot:
                            raise PhrasebookError(f"shape {intent}.{shape} defined twice")
                        slot[shape] = languages
            elif isinstance(value, dict):
                merged.setdefault(key, {}).update(value)
            else:
                merged.setdefault(key, value)
    families: dict[tuple[str, str, str], tuple[Family, ...]] = {}
    for intent, shapes in merged["families"].items():
        for shape, languages in shapes.items():
            for language, groups in languages.items():
                families[(intent, shape, language)] = tuple(
                    Family(f"{intent}.{shape}.{language}.{i}", intent, shape, language, tuple(g))
                    for i, g in enumerate(groups, start=1)
                )
    book = Phrasebook(
        service_names=_names(merged["service_names"]),
        variants=_names(merged["variants"]),
        variant_frames={k: tuple(v) for k, v in merged["variant_frames"].items()},
        variant_joiners={k: tuple(v) for k, v in merged["variant_joiners"].items()},
        families=families,
        office_names=_names(merged.get("offices")),
        agency_names=_names(merged.get("agencies")),
        document_names=_names(merged.get("documents")),
    )
    problems = check_phrasebook(book)
    if problems:
        raise PhrasebookError("; ".join(problems))
    return book


def expected_placeholders(template: T.Template) -> list[str]:
    """The placeholders a phrase for this template has to contain (each exactly once)."""
    return sorted(PLACEHOLDER_OF[p] for p in template.needs)


def check_phrasebook(
    book: Phrasebook,
    graph: InMemoryGraph | None = None,
    held_out: frozenset[str] = frozenset(),
) -> list[str]:
    """Everything that could make the generator fail or produce a bad phrase."""
    graph = graph or InMemoryGraph.from_dir()
    problems: list[str] = []

    def need(kind: str, names: Names, ids: list[str]) -> None:
        for ident in ids:
            for lang in ("en", "fil"):
                if not names.get(ident, {}).get(lang):
                    problems.append(f"no {lang} name for {kind} {ident}")
        for extra in sorted(set(names) - set(ids)):
            problems.append(f"phrasebook names an unknown {kind} {extra}")

    need("service", book.service_names, [s.id for s in graph.seed.services])
    need("variant", book.variants, [v.id for v in graph.seed.variants])
    need("office", book.office_names, [o.id for o in graph.seed.offices])
    agencies = {slug(r.secured_at) for r in graph.seed.requirements if r.secured_at}
    need("agency", book.agency_names, sorted(book.agency_names))
    for aid in book.agency_names:
        if aid not in agencies:
            problems.append(f"agency {aid} is not an Agency of the seed")
    need("document", book.document_names, sorted(book.document_names))
    texts = [r.text.lower() for r in graph.seed.requirements]
    for doc in book.document_names:
        if not any(doc in t for t in texts):
            problems.append(f"document words {doc!r} occur in no requirement text")
        if doc != doc.lower() or not re.fullmatch(r"[a-z0-9][a-z0-9 ]*[a-z0-9]", doc):
            problems.append(f"document key {doc!r} must be lowercase words")

    for lang in LANGUAGES:
        if not book.variant_frames.get(lang) or not book.variant_joiners.get(lang):
            problems.append(f"no variant frames or joiners for {lang}")
        for frame in book.variant_frames.get(lang, ()):
            if "{base}" not in frame or "{variant}" not in frame:
                problems.append(f"variant frame {frame!r} needs {{base}} and {{variant}}")

    wanted = {(i, s): t for (i, s, filtered), t in T.TEMPLATES.items() if not filtered}
    have = {(i, s) for (i, s, _) in book.families}
    for missing in sorted(set(wanted) - have):
        problems.append(f"no phrase families for {missing}")
    for extra in sorted(have - set(wanted)):
        problems.append(f"phrase families for {extra}, which has no template")
    for (intent, shape, lang), fams in book.families.items():
        template = wanted.get((intent, shape))
        if lang not in LANGUAGES:
            problems.append(f"unknown language {lang!r} in {intent}.{shape}")
        minimum = 1 if shape in held_out else 3
        if len(fams) < minimum:
            problems.append(f"{intent}.{shape}.{lang} needs at least {minimum} families")
        for fam in fams:
            if not fam.templates:
                problems.append(f"family {fam.id} is empty")
            for tpl in fam.templates:
                holders = sorted(_PLACEHOLDER.findall(tpl))
                if template is not None and holders != expected_placeholders(template):
                    problems.append(
                        f"{fam.id}: {tpl!r} must contain exactly "
                        f"{['{' + h + '}' for h in expected_placeholders(template)]}"
                    )
                if "<" in _ALTERNATIVES.sub("", tpl) or ">" in _ALTERNATIVES.sub("", tpl):
                    problems.append(f"{fam.id}: unbalanced <a|b> in {tpl!r}")
    return problems


def review_strings(book: Phrasebook) -> list[str]:
    """Every Filipino or Taglish string in the generator, in a stable order (NEEDS-NATIVE-REVIEW)."""
    out: list[str] = []
    for label, names in (
        ("service name", book.service_names),
        ("office name", book.office_names),
        ("agency name", book.agency_names),
        ("document name", book.document_names),
        ("variant phrase", book.variants),
    ):
        for key in sorted(names):
            out += [f"{label} [{key}]: {n}" for n in names[key].get("fil", ())]
    for lang in ("fil", "mixed"):
        out += [f"variant frame [{lang}]: {f}" for f in book.variant_frames[lang]]
        out += [f"variant joiner [{lang}]: {j!r}" for j in book.variant_joiners[lang]]
    for key in sorted(book.families):
        if key[2] in ("fil", "mixed"):
            for fam in book.families[key]:
                out += [f"family {fam.id}: {t}" for t in fam.templates]
    out += [f"sms spelling: {k} -> {v}" for k, v in sorted(SMS_FIL.items())]
    return out


# ---- aliases ----------------------------------------------------------------------------------

Aliases = dict[str, dict[str, list[str]]]


def load_aliases(graph: InMemoryGraph, path: Path = ALIASES_PATH) -> Aliases:
    """Service and office aliases from ``graph/seed/aliases.yaml`` (the gateway's table), as
    target id -> language -> texts. Records it cannot read are skipped; nothing here can fail the
    generator. Alias text is a NAME, never charter answer text. Aliases of kind ``everyday`` are
    left out: they are situations or verb phrases ("magbukas ng negosyo") that do not fit into a
    sentence where a service name goes."""
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    records = data.get("aliases", []) if isinstance(data, dict) else data
    known = {s.id for s in graph.seed.services} | {o.id for o in graph.seed.offices}
    out: Aliases = {}
    for rec in records if isinstance(records, list) else []:
        if not isinstance(rec, dict):
            continue
        target = next(
            (rec[k] for k in ("target", "service_id", "target_id", "for") if k in rec), None
        )
        text, lang = rec.get("text"), rec.get("lang")
        if rec.get("kind") == "everyday":
            continue
        if target in known and isinstance(text, str) and text.strip() and lang in ("en", "fil"):
            out.setdefault(target, {}).setdefault(lang, []).append(" ".join(text.split()))
    return out


# ---- building a phrase --------------------------------------------------------------------------


def _expand(template: str, rng: random.Random) -> str:
    return _ALTERNATIVES.sub(lambda m: rng.choice(m.group(1).split("|")), template)


def _pool(names: Mapping[str, tuple[str, ...]], extra: Mapping[str, list[str]], language: str):
    en = [*names.get("en", ()), *extra.get("en", ())]
    fil = [*names.get("fil", ()), *extra.get("fil", ())]
    return {"en": en, "fil": fil, "mixed": en + fil}[language]


def entity_name(
    rng: random.Random,
    book: Phrasebook,
    aliases: Aliases,
    graph: InMemoryGraph,
    kind: str,
    ident: str,
    language: str,
) -> str:
    """How a citizen might name a service, office, agency or document."""
    if kind == "service":
        if language != "fil" and rng.random() < OFFICIAL_NAME_SHARE:
            return " ".join(graph.service(ident).name.split())
        return rng.choice(_pool(book.service_names[ident], aliases.get(ident, {}), language))
    table = {
        "office": (book.office_names, aliases),
        "agency": (book.agency_names, {}),
        "document": (book.document_names, {}),
    }[kind]
    names, extra = table
    return rng.choice(_pool(names[ident], extra.get(ident, {}), language))


def variant_text(rng: random.Random, book: Phrasebook, combo, language: str) -> str:
    parts = []
    for dimension, value in combo:
        forms = book.variants[f"{dimension}:{value}"]
        lang = rng.choice(("en", "fil")) if language == "mixed" else language
        parts.append(rng.choice(forms[lang]))
    return rng.choice(book.variant_joiners[language]).join(parts)


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", text.lower())}


def build_phrase(
    rng: random.Random,
    book: Phrasebook,
    aliases: Aliases,
    graph: InMemoryGraph,
    family: Family,
    entities: Mapping[str, str],
    combo,
    mention_variants: bool,
) -> tuple[str, frozenset[str]]:
    """The clean phrase for one cell and family, and the words that must not get noise.

    ``entities`` maps a placeholder (``service``, ``service2``, ``office``, ``agency``,
    ``document``) to the id of what the phrase names.
    """
    text = _expand(rng.choice(family.templates), rng)
    protected: set[str] = set()
    for holder in _PLACEHOLDER.findall(text):
        kind = "service" if holder.startswith("service") else holder
        name = entity_name(rng, book, aliases, graph, kind, entities[holder], family.language)
        protected |= _words(name)
        text = text.replace("{" + holder + "}", name)
    if combo and mention_variants:
        end = "?" if text.endswith("?") else ""
        base = text.rstrip("?. ")
        variant = variant_text(rng, book, combo, family.language)
        protected |= _words(variant)
        frame = rng.choice(book.variant_frames[family.language])
        text = frame.replace("{base}", base).replace("{variant}", variant) + end
    return " ".join(text.split()), frozenset(protected)


__all__ = [
    "Aliases",
    "Family",
    "Phrasebook",
    "PhrasebookError",
    "build_phrase",
    "check_phrasebook",
    "clean_name",
    "entity_name",
    "expected_placeholders",
    "load_aliases",
    "load_phrasebook",
    "review_strings",
    "variant_text",
]
