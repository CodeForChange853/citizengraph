"""Load and validate ``graph/seed/aliases.yaml``.

The table has two parts: a registry of every charter service (``in_graph`` says whether the
service is curated in the graph) and one row per alias phrase. The loader reports every problem at
once (like ``graph.load_seed``): unknown targets, empty text, duplicates, ids that do not exist in
the graph, missing native-review marks.

It imports the graph package read-only and is not wired into ``graph/load.py`` (a later session
does that).
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from citizengraph.gateway.text import fold, is_word, tokenize
from citizengraph.graph import DEFAULT_SEED_DIR, InMemoryGraph

LANGS = ("en", "fil")
KINDS = ("name", "synonym", "abbreviation", "everyday")
KIND_WEIGHT = {"name": 1.00, "synonym": 0.97, "abbreviation": 0.95, "everyday": 0.93}
ALIASES_FILE = "aliases.yaml"


@dataclass(frozen=True)
class AliasIssue:
    code: str
    message: str

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


class AliasError(ValueError):
    """The alias table has one or more problems; ``issues`` lists all of them."""

    def __init__(self, issues: list[AliasIssue]):
        self.issues = issues
        super().__init__(
            f"{len(issues)} problem(s) in {ALIASES_FILE}:\n" + "\n".join(f"  {i}" for i in issues)
        )


@dataclass(frozen=True)
class ServiceEntry:
    id: str
    charter_ref: str
    office_id: str
    in_graph: bool
    name: str | None = None
    cues_en: tuple[str, ...] = ()
    cues_fil: tuple[str, ...] = ()


@dataclass(frozen=True)
class Alias:
    target: str
    lang: str
    text: str
    kind: str
    needs_native_review: bool = False


@dataclass(frozen=True)
class AliasTable:
    services: dict[str, ServiceEntry]
    aliases: tuple[Alias, ...]
    office_ids: frozenset[str] = field(default_factory=frozenset)

    def is_office(self, target: str) -> bool:
        return target in self.office_ids

    def for_target(self, target: str) -> list[Alias]:
        return [a for a in self.aliases if a.target == target]


def _norm_key(text: str) -> str:
    return " ".join(t for t in tokenize(fold(text)) if is_word(t))


def parse_aliases(
    raw: Any,
    *,
    office_ids: Collection[str],
    graph_services: Mapping[str, tuple[str, str]] | None = None,
) -> AliasTable:
    """Validate parsed YAML. ``graph_services`` maps each graph service id to
    ``(charter_ref, office_id)``; when given, the registry is checked against it both ways."""
    issues: list[AliasIssue] = []

    def bad(code: str, msg: str) -> None:
        issues.append(AliasIssue(code, msg))

    if not isinstance(raw, dict):
        raise AliasError([AliasIssue("schema", "top level must be a mapping")])
    for key in ("services", "aliases"):
        if not isinstance(raw.get(key), list):
            bad("schema", f"'{key}:' must be a list")
    if issues:
        raise AliasError(issues)

    offices = frozenset(office_ids)
    services: dict[str, ServiceEntry] = {}
    refs: dict[str, str] = {}
    for i, row in enumerate(raw["services"]):
        where = f"services[{i}]"
        if not isinstance(row, dict):
            bad("schema", f"{where}: expected a mapping")
            continue
        sid, ref, office = row.get("id"), row.get("charter_ref"), row.get("office_id")
        if not isinstance(sid, str) or not sid.strip():
            bad("schema", f"{where}: id must be a non-empty string")
            continue
        where = f"services[{sid}]"
        if not isinstance(ref, str) or not ref.strip():
            bad("schema", f"{where}: charter_ref must be a non-empty string")
        if office not in offices:
            bad("unknown_office", f"{where}: office_id {office!r} is not an office")
        if not isinstance(row.get("in_graph"), bool):
            bad("schema", f"{where}: in_graph must be true or false")
        name = row.get("name")
        if name is not None and (not isinstance(name, str) or not name.strip()):
            bad("schema", f"{where}: name must be a non-empty string when given")
        if row.get("in_graph") is False and not name:
            bad("schema", f"{where}: a service that is not in the graph needs a name")
        cues: dict[str, tuple[str, ...]] = {}
        for lang in ("cues_en", "cues_fil"):
            value = row.get(lang, [])
            if not isinstance(value, list) or not all(
                isinstance(v, str) and v.strip() for v in value
            ):
                bad("schema", f"{where}: {lang} must be a list of non-empty strings")
                value = []
            cues[lang] = tuple(value)
        if sid in services:
            bad("duplicate_service", f"{where}: listed twice")
            continue
        if isinstance(ref, str):
            if ref in refs:
                bad("duplicate_service", f"{where}: charter_ref {ref} already used by {refs[ref]}")
            refs[ref] = sid
        services[sid] = ServiceEntry(
            id=sid,
            charter_ref=str(ref),
            office_id=str(office),
            in_graph=row.get("in_graph") is True,
            name=name,
            cues_en=cues["cues_en"],
            cues_fil=cues["cues_fil"],
        )

    if graph_services is not None:
        for sid, entry in services.items():
            if entry.in_graph:
                if sid not in graph_services:
                    bad(
                        "unknown_service",
                        f"services[{sid}]: in_graph is true but the graph has no such service",
                    )
                else:
                    g_ref, g_office = graph_services[sid]
                    if entry.charter_ref != g_ref:
                        bad(
                            "graph_mismatch",
                            f"services[{sid}]: charter_ref {entry.charter_ref} != graph {g_ref}",
                        )
                    if entry.office_id != g_office:
                        bad(
                            "graph_mismatch",
                            f"services[{sid}]: office_id {entry.office_id} != graph {g_office}",
                        )
            elif sid in graph_services:
                bad(
                    "graph_mismatch",
                    f"services[{sid}]: in_graph is false but the graph has this service",
                )
        for sid in graph_services:
            if sid not in services:
                bad("missing_service", f"graph service {sid} has no row in services:")

    aliases: list[Alias] = []
    seen: dict[tuple[str, str, str], int] = {}
    for i, row in enumerate(raw["aliases"]):
        where = f"aliases[{i}]"
        if not isinstance(row, dict):
            bad("schema", f"{where}: expected a mapping")
            continue
        target, lang, text, kind = (
            row.get("target"),
            row.get("lang"),
            row.get("text"),
            row.get("kind"),
        )
        if not isinstance(text, str) or not _norm_key(text):
            bad("empty_text", f"{where} (target {target!r}): text is empty")
            continue
        where = f"aliases[{i}] {text!r}"
        if target not in services and target not in offices:
            bad("unknown_target", f"{where}: target {target!r} is neither a service nor an office")
        if lang not in LANGS:
            bad("bad_lang", f"{where}: lang must be one of {LANGS}, got {lang!r}")
        if kind not in KINDS:
            bad("bad_kind", f"{where}: kind must be one of {KINDS}, got {kind!r}")
        review = row.get("needs_native_review", False)
        if not isinstance(review, bool):
            bad("schema", f"{where}: needs_native_review must be true or false")
        elif lang == "fil" and not review:
            bad("missing_review_mark", f"{where}: Filipino rows must set needs_native_review: true")
        elif lang == "en" and review:
            bad("schema", f"{where}: only Filipino rows carry needs_native_review")
        key = (str(target), str(lang), _norm_key(text))
        if key in seen:
            bad(
                "duplicate_alias",
                f"{where}: same as aliases[{seen[key]}] (target {target}, lang {lang})",
            )
        else:
            seen[key] = i
        aliases.append(Alias(str(target), str(lang), text.strip(), str(kind), review is True))
    if issues:
        raise AliasError(issues)
    return AliasTable(services=services, aliases=tuple(aliases), office_ids=offices)


def load_aliases(
    path: Path | str | None = None,
    graph: InMemoryGraph | None = None,
) -> AliasTable:
    """Read ``graph/seed/aliases.yaml`` and validate it (against ``graph`` when given)."""
    target = Path(path) if path else DEFAULT_SEED_DIR / ALIASES_FILE
    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise AliasError([AliasIssue("bad_yaml", f"{target.name}: {exc}")]) from exc
    if graph is None:
        graph = InMemoryGraph.from_dir()
    return parse_aliases(
        raw,
        office_ids=[o.id for o in graph.seed.offices],
        graph_services={s.id: (s.charter_ref, s.office_id) for s in graph.services()},
    )
