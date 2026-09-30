"""Templates-only baseline: the gateway's rule-based intent mapped to the canonical templates.

No model. It reads the same request as the model (targets, language, cleaned phrase) and answers in
the same completion format, so ``eval_generate`` scores it on the same test set:

1. the gateway's own normalizer, linker and intent detector run on the phrase (the very code the
   front end uses), and the first Core 1 intent found is taken;
2. the variants come from the gateway's variant cues, resolved against the variants the target
   service really has (``VariantCatalog``);
3. the query is the plain ``list`` template of that intent (filtered when variants were found and
   the intent can be filtered). The ids come from the given targets.

What it cannot do, by construction: pick any shape other than ``list`` (counts, totals,
comparisons, reverse lookups, office listings, cross-office prerequisites), answer two intents at
once (it takes the first), or run without the parameter its list template needs (an office-only or
document-only request has no ``$sid``), in which case it gives no answer. That is the gap the
model has to close.
"""

from __future__ import annotations

from citizengraph.core1 import templates as T
from citizengraph.core1.output import format_completion
from citizengraph.core1.targets import Request
from citizengraph.gateway import Gateway, default_gateway


class TemplatesOnlyBaseline:
    def __init__(self, gateway: Gateway | None = None):
        self.gateway = gateway or default_gateway()

    def infer(self, request: Request) -> tuple[str | None, dict[str, str]]:
        """(intent, variants) the gateway's rules find in the phrase; intent None if none."""
        gw = self.gateway
        norm = gw.normalizer(request.phrase)
        mentions = gw.linker.link(norm)
        hits = gw.detector.detect(norm, mentions)
        intent = next((h.intent for h in hits if h.intent in T.CORE1_INTENTS), None)
        services = request.of_kind("service")
        variants: dict[str, str] = {}
        if services:
            supported, unsupported = gw.detector.variant_cues(norm)
            variants, _ = gw.catalog.resolve(
                services[0],
                [(d, v) for _, d, v in supported],
                [(d, v) for _, d, v in unsupported],
            )
        return intent, variants

    def complete(self, request: Request) -> str:
        """A completion in the model's format, or ``""`` when the baseline has no answer."""
        intent, variants = self.infer(request)
        if intent is None or (intent, "list", False) not in T.TEMPLATES:
            return ""
        filtered = bool(variants) and T.supports_variants(intent, "list")
        template = T.TEMPLATES[(intent, "list", filtered)]
        if any(p != "sid" for p in template.needs) or not request.of_kind("service"):
            return ""  # no $sid to run the list template with
        ids = sorted(f"{d}:{v}" for d, v in variants.items()) if filtered else []
        return format_completion(template, ids)
