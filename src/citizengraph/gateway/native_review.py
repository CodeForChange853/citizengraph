"""List every Filipino string in the gateway's data that needs native-speaker review.

``python -m citizengraph.gateway.native_review`` prints the list as Markdown; the same text sits
between the markers at the end of ``docs/gateway_notes.md`` (a test keeps them in step, so the
notes can never miss a string). The gateway itself produces no Filipino sentences: replies are the
composer's job. Everything here is matching vocabulary.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import yaml

from citizengraph.gateway.lexicon import LEXICON_DIR, read_yaml
from citizengraph.graph import DEFAULT_SEED_DIR

BEGIN = "<!-- BEGIN native-review (generated: python -m citizengraph.gateway.native_review) -->"
END = "<!-- END native-review -->"

Section = tuple[str, list[str]]


def _section(title: str, items: Iterable[object]) -> Section:
    return title, [str(i) for i in items]


def collect(directory: Path | None = None, seed_dir: Path | None = None) -> list[Section]:
    lex = directory or LEXICON_DIR
    aliases = yaml.safe_load(((seed_dir or DEFAULT_SEED_DIR) / "aliases.yaml").read_text("utf-8"))
    out: list[Section] = []

    by_target: dict[str, list[str]] = {}
    for row in aliases["aliases"]:
        if row["lang"] == "fil":
            by_target.setdefault(row["target"], []).append(row["text"])
    for target, texts in by_target.items():
        out.append(_section(f"graph/seed/aliases.yaml, Filipino aliases of `{target}`", texts))
    cues = [
        f"{s['id']}: {cue}" for s in aliases["services"] for cue in s.get("cues_fil", [])
    ]
    out.append(_section("graph/seed/aliases.yaml, `cues_fil`", cues))

    sms = read_yaml("sms.yaml", lex)["sms_fil"]
    out.append(_section("lexicon/sms.yaml, `sms_fil` (typed -> canonical)", [f"{k} -> {v}" for k, v in sms.items()]))

    vocab = read_yaml("vocab.yaml", lex)
    for key in ("fil_function", "fil_common"):
        out.append(_section(f"lexicon/vocab.yaml, `{key}`", vocab[key]))
    for key in ("greetings", "confirm_yes", "confirm_no", "conjunctions", "menu_requests"):
        out.append(_section(f"lexicon/vocab.yaml, `{key}` (Filipino entries)", vocab[key]["fil"]))

    for intent, langs in read_yaml("intents.yaml", lex).items():
        out.append(_section(f"lexicon/intents.yaml, `{intent}` Filipino phrases", langs["fil"]))

    variants = read_yaml("variants.yaml", lex)
    for part in ("cues", "unsupported"):
        for dimension, values in variants[part].items():
            for value, langs in values.items():
                if langs.get("fil"):
                    out.append(
                        _section(
                            f"lexicon/variants.yaml, {part} `{dimension}:{value}` Filipino phrases",
                            langs["fil"],
                        )
                    )

    spam = read_yaml("spam.yaml", lex)
    out.append(_section("lexicon/spam.yaml, `injection.fil` patterns (regex)", spam["injection"]["fil"]))
    out.append(_section("lexicon/spam.yaml, `mutation.strong.fil` verbs", spam["mutation"]["strong"]["fil"]))
    out.append(_section("lexicon/spam.yaml, `mutation.weak.fil` verbs", spam["mutation"]["weak"]["fil"]))
    return [(title, items) for title, items in out if items]


def render(directory: Path | None = None, seed_dir: Path | None = None) -> str:
    sections = collect(directory, seed_dir)
    lines: list[str] = []
    for title, items in sections:
        lines.append(f"**{title}** ({len(items)})")
        lines.append("")
        if "regex" in title:
            lines.extend(f"- `{item}`" for item in items)
        else:
            lines.append(" · ".join(f"`{item}`" for item in items))
        lines.append("")
    total = sum(len(items) for _, items in sections)
    header = f"{total} strings in {len(sections)} lists."
    return header + "\n\n" + "\n".join(lines).rstrip() + "\n"


if __name__ == "__main__":
    print(render(), end="")
