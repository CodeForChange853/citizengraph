"""The gateway pipeline: ``process(message, session, now=None) -> GatewayResult``.

Order: spam screen -> normalize -> link -> intents and variants -> split -> clarify / echo.
Deterministic (same message and session state in, same result out, apart from ``timings_ms``) and
model-free: nothing in this package calls a model or the network.

What each status means for the caller:

* ``ok``            answer ``sub_requests`` (Core 1, or Core 2 for ``status`` intents);
* ``clarify``       ask the question in ``clarify_options``; the tapped option's ``id`` comes back
                    as the next message (typed answers are understood too);
* ``echo_confirm``  read ``echo`` back; the citizen answers yes/no (``confirm:yes`` / ``confirm:no``
                    or typed); long or noisy input always takes this path;
* ``refuse``        mutation, injection, code-like text, or over the hard length cap: no further
                    processing, nothing echoed;
* ``fallback``      no usable request (gibberish, greeting, empty): show the service menu;
* ``rate_limited``  too many or repeated messages: throttled reply;
* ``out_of_scope``  not a charter service, or a service the graph cannot answer yet
                    (``unavailable`` names it and its office).
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache

from citizengraph.gateway.aliases import AliasTable, load_aliases
from citizengraph.gateway.config import GatewayConfig, load_config
from citizengraph.gateway.intents import IntentDetector, VariantCatalog
from citizengraph.gateway.lexicon import Lexicon
from citizengraph.gateway.linker import Linker, Mention
from citizengraph.gateway.normalize import Normalized, Normalizer
from citizengraph.gateway.spam import (
    SpamPatterns,
    check_rate,
    check_repeat,
    digest,
    gibberish_score,
    note_message,
    screen_text,
)
from citizengraph.gateway.splitter import split
from citizengraph.gateway.types import (
    INTENTS,
    ClarifyOption,
    Draft,
    Echo,
    EchoItem,
    GatewayResult,
    Language,
    Pending,
    SessionState,
    SubRequest,
    Unavailable,
)
from citizengraph.graph import InMemoryGraph

CARRY_OVER_MAX_WORDS = 10
CARRY_OVER_MAX_UNKNOWN = 0.2
CONFIRM_MAX_WORDS = 4
ASKABLE_INTENTS = tuple(i for i in INTENTS if i != "status")


def _seconds(now: float | datetime | None) -> float:
    if now is None:
        return time.time()
    if isinstance(now, datetime):
        return now.timestamp()
    return float(now)


def guess_language(norm: Normalized, lexicon: Lexicon) -> Language:
    """en / fil / mixed from words that belong to one language only. A Filipino frame around
    English nouns ("magkano ang marriage license") is Taglish, so mixed."""
    en = fil = 0
    for tok in norm.words:
        lang = lexicon.lang_of.get(tok.text)
        en += lang == "en"
        fil += lang == "fil"
    if en and fil:
        return "mixed"
    return "fil" if fil else "en"


class _Timer:
    def __init__(self) -> None:
        self._ms: dict[str, float] = {}

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        start = time.perf_counter()
        try:
            yield
        finally:
            self._ms[name] = self._ms.get(name, 0.0) + (time.perf_counter() - start) * 1000.0

    def timings(self) -> dict[str, float]:
        return {k: round(v, 3) for k, v in self._ms.items()}


@dataclass
class _Ctx:
    language: Language = "en"
    needs_echo: bool = False
    reasons: list[str] = field(default_factory=list)
    unavailable: list[Unavailable] = field(default_factory=list)


class Gateway:
    """Build once (loads the graph, the alias table and the lexicon), then call ``process``."""

    def __init__(
        self,
        graph: InMemoryGraph | None = None,
        table: AliasTable | None = None,
        config: GatewayConfig | None = None,
        lexicon: Lexicon | None = None,
    ):
        self.graph = graph or InMemoryGraph.from_dir()
        self.cfg = config or load_config()
        self.table = table or load_aliases(graph=self.graph)
        self.lexicon = lexicon or Lexicon(self.table)
        self.normalizer = Normalizer(self.lexicon)
        self.linker = Linker(self.table, self.lexicon, self.cfg)
        self.detector = IntentDetector(self.lexicon)
        self.catalog = VariantCatalog(self.graph)
        self.patterns = SpamPatterns()
        self._office_names = {o.id: o.name for o in self.graph.seed.offices}

    # ---------------------------------------------------------------------- entry point

    def process(
        self,
        message: str,
        session: SessionState,
        now: float | datetime | None = None,
    ) -> GatewayResult:
        timer = _Timer()
        result = self._process(message, session, _seconds(now), timer)
        return result.model_copy(update={"timings_ms": timer.timings()})

    def _process(
        self, message: str, session: SessionState, now: float, timer: _Timer
    ) -> GatewayResult:
        cfg = self.cfg
        if not isinstance(message, str):
            return GatewayResult(status="fallback", reasons=["not_text"])

        with timer.stage("spam"):
            limited = check_rate(session, now, cfg)
            tap = self._match_tap(session, message)
            dig = digest(message)
            repeated = (
                tap is None and session.pending is None and check_repeat(session, now, cfg, dig)
            )
            note_message(session, now, cfg, None if tap is not None else dig)
            if limited:
                return GatewayResult(
                    status="rate_limited", reasons=[limited[0]], retry_after_s=limited[1]
                )
            if repeated:
                return GatewayResult(status="rate_limited", reasons=["repeated_message"])
            screen = None if tap is not None else screen_text(message, cfg, self.patterns)
        if tap is not None:
            return self._apply_option(session, tap)
        assert screen is not None
        if screen.status != "ok":
            return GatewayResult(status=screen.status, reasons=list(screen.reasons))  # type: ignore[arg-type]

        ctx = _Ctx()
        with timer.stage("normalize"):
            norm = self.normalizer(message)
            ctx.language = guess_language(norm, self.lexicon)
        with timer.stage("gibberish"):
            gibberish = gibberish_score([(t.text, t.known) for t in norm.words], message)
        noisy = (
            len(norm.words) >= cfg.noisy_min_tokens
            and norm.unknown_ratio() >= cfg.noisy_unknown_ratio
        )
        if screen.long_input:
            ctx.reasons.append("long_input")
        if noisy:
            ctx.reasons.append("noisy_input")
        if norm.repairs:
            ctx.reasons.append("typo_repaired")
        ctx.needs_echo = screen.long_input or noisy

        if session.pending is not None:
            answered = self._answer_typed(session, norm, ctx)
            if answered is not None:
                return answered
            session.pending = None
            ctx.reasons.append("pending_dropped")

        with timer.stage("link"):
            mentions = self._drop_inside_other_services(norm, self.linker.link(norm), ctx)
        with timer.stage("intents"):
            intents = self.detector.detect(norm, mentions)
            cues, unsupported = self.detector.variant_cues(norm)
        with timer.stage("split"):
            drafts, split_reasons = split(
                norm, mentions, intents, cues, unsupported, self.lexicon, cfg,
                ctx.language, drop_unknown=ctx.needs_echo,
            )  # fmt: skip
            ctx.reasons.extend(split_reasons)
            for m in mentions:
                if m.resolved_by:
                    ctx.reasons.append(f"{m.resolved_by}_disambiguated")
        with timer.stage("clarify"):
            return self._route(session, norm, mentions, intents, cues, unsupported, drafts,
                               gibberish, ctx)  # fmt: skip

    def _drop_inside_other_services(
        self, norm: Normalized, mentions: list[Mention], ctx: _Ctx
    ) -> list[Mention]:
        """ "building permit" is not the business permit: a mention that only overlaps the words
        of a service nobody here offers, and is no better than a bare everyday word, goes."""
        others = self.lexicon.other_services.scan(norm.texts)
        if not others:
            return mentions
        kept = [
            m
            for m in mentions
            if m.best.kind != "everyday"
            or not any(h.start < m.end and m.start < h.end for h in others)
        ]
        if len(kept) != len(mentions):
            ctx.reasons.append("other_service_ignored")
        return kept

    # ----------------------------------------------------------------- routing

    def _route(
        self,
        session: SessionState,
        norm: Normalized,
        mentions: list[Mention],
        intents,
        cues,
        unsupported,
        drafts: list[Draft],
        gibberish: float,
        ctx: _Ctx,
    ) -> GatewayResult:
        words = [t.text for t in norm.words]
        if not drafts and self.lexicon.other_services.scan(words):
            ctx.reasons.append("other_service")
            return GatewayResult(
                status="out_of_scope", reasons=_unique(ctx.reasons), language=ctx.language
            )
        if drafts:
            return self._finish(session, drafts, ctx)
        phrase = " ".join(t.text for t in norm.words if t.known)[: self.cfg.max_phrase_chars]
        offices = sorted({m.best.target for m in mentions if m.is_office})

        if any(h.intent == "status" for h in intents):
            draft = Draft(
                intent="status", phrase=phrase, language=ctx.language,
                office_id=offices[0] if len(offices) == 1 else None,
            )  # fmt: skip
            return self._finish(session, [draft], ctx)

        if offices:
            intent = intents[0].intent if intents else None
            drafts = []
            for office_id in offices:
                ids = [s.id for s in self.graph.services(office_id)]
                if ids:
                    drafts.append(
                        Draft(candidates=ids, intent=intent, phrase=phrase, language=ctx.language)
                    )
                    break
            if drafts:
                ctx.reasons.append("office_only")
                return self._finish(session, drafts, ctx)
            ctx.reasons.append("office_without_services")
            return GatewayResult(
                status="out_of_scope", reasons=_unique(ctx.reasons), language=ctx.language
            )

        carried = self._carry_over(session, norm, intents, cues, unsupported, phrase, ctx)
        if carried:
            return self._finish(session, carried, ctx)

        def stop(status: str, reason: str) -> GatewayResult:
            ctx.reasons.append(reason)
            return GatewayResult(
                status=status,  # type: ignore[arg-type]
                reasons=_unique(ctx.reasons),
                language=ctx.language,
            )

        if self.lexicon.menu_requests.scan(words):
            return stop("fallback", "menu_request")
        if words and all(w in self.lexicon.greetings for w in words):
            return stop("fallback", "greeting")
        answers = self.lexicon.confirm_yes | self.lexicon.confirm_no
        if words and all(w in answers or w in self.lexicon.greetings for w in words):
            return stop("fallback", "no_pending_question")
        if gibberish >= self.cfg.gibberish_threshold:
            return stop("fallback", "gibberish")
        if intents and norm.unknown_ratio() <= 0.25:
            return stop("fallback", "no_service_named")
        return stop("out_of_scope", "no_service_match")

    def _carry_over(
        self, session, norm, intents, cues, unsupported, phrase: str, ctx: _Ctx
    ) -> list[Draft] | None:
        """A short follow-up ("and the fees?", "for corporation") about the service the session
        already resolved."""
        sid = session.resolved_service_id
        if sid is None or len(norm.words) > CARRY_OVER_MAX_WORDS:
            return None
        if norm.unknown_ratio() > CARRY_OVER_MAX_UNKNOWN or not self._available(sid):
            return None
        dims = self.catalog.dimensions(sid)
        new_cues = [(d, v) for _, d, v in cues if v in dims.get(d, ())]
        if not intents and not new_cues:
            return None
        names: list[str] = []
        for h in intents:
            if h.intent not in names:
                names.append(h.intent)
        if not names and session.last_intent:
            names = [session.last_intent]
        fresh_dims = {d for d, _ in new_cues}
        carried = [(d, v) for d, v in session.resolved_variants.items() if d not in fresh_dims]
        ctx.reasons.append("service_from_session")
        return [
            Draft(
                service_id=sid, intent=intent, cues=sorted({*carried, *new_cues}),
                unsupported=sorted({(d, v) for _, d, v in unsupported}),
                phrase=phrase, language=ctx.language,
            )
            for intent in names or [None]
        ]  # fmt: skip

    # ----------------------------------------------------------------- finishing

    def _available(self, service_id: str) -> bool:
        entry = self.table.services.get(service_id)
        return bool(entry and entry.in_graph and service_id not in self.cfg.withheld_services)

    def _service_name(self, service_id: str) -> str | None:
        entry = self.table.services.get(service_id)
        if entry is None:
            return None
        if entry.in_graph:
            return self.graph.service(service_id).name
        return entry.name

    def _unavailable(self, service_id: str) -> Unavailable:
        entry = self.table.services[service_id]
        return Unavailable(
            service_id=service_id,
            name=self._service_name(service_id),
            office_id=entry.office_id,
            office_name=self._office_names.get(entry.office_id),
            reason="not_in_graph" if not entry.in_graph else "withheld",
        )

    def _service_options(self, candidates: list[str]) -> list[ClarifyOption]:
        options = [
            ClarifyOption(
                id=f"service:{sid}",
                kind="service",
                label=self._service_name(sid) or sid,
                service_id=sid,
                in_graph=self._available(sid),
                office_id=self.table.services[sid].office_id,
            )
            for sid in candidates
        ]
        order = {sid: i for i, sid in enumerate(self.table.services)}  # charter order
        options.sort(key=lambda o: (not o.in_graph, order.get(o.service_id or "", 0)))
        return options  # answerable ones first

    def _finish(self, session: SessionState, drafts: list[Draft], ctx: _Ctx) -> GatewayResult:
        unavailable = list(ctx.unavailable)
        kept: list[Draft] = []
        for d in drafts:
            if d.service_id is not None and not self._available(d.service_id):
                if all(u.service_id != d.service_id for u in unavailable):
                    unavailable.append(self._unavailable(d.service_id))
                continue
            kept.append(d)
        ctx.unavailable = unavailable
        drafts = kept

        def build(status: str, **kw) -> GatewayResult:
            return GatewayResult(
                status=status,  # type: ignore[arg-type]
                reasons=_unique(ctx.reasons),
                language=ctx.language,
                unavailable=unavailable,
                **kw,
            )

        if not drafts:
            ctx.reasons.append("service_not_available")
            return build("out_of_scope")

        for d in drafts:
            if d.intent == "status" and d.service_id is None and d.candidates:
                d.candidates = []
                ctx.reasons.append("status_service_unresolved")
            if d.intent is None and self.cfg.default_intent:
                d.intent = self.cfg.default_intent
                ctx.reasons.append("default_intent")

        for d in drafts:
            if d.service_id is None and d.candidates:
                options = self._service_options(d.candidates)
                session.pending = Pending(
                    kind="service", drafts=drafts, options=options,
                    needs_echo=ctx.needs_echo, reasons=_unique(ctx.reasons),
                )  # fmt: skip
                return build("clarify", clarify_options=options, clarify_kind="service")

        if any(d.intent is None for d in drafts):
            options = [
                ClarifyOption(id=f"intent:{i}", kind="intent", label=i, intent=i)  # type: ignore[arg-type]
                for i in ASKABLE_INTENTS
            ]
            session.pending = Pending(
                kind="intent", drafts=drafts, options=options,
                needs_echo=ctx.needs_echo, reasons=_unique(ctx.reasons),
            )  # fmt: skip
            return build("clarify", clarify_options=options, clarify_kind="intent")

        subs: list[SubRequest] = []
        for d in drafts:
            variants: dict[str, str] = {}
            if d.service_id is not None:
                variants, vreasons = self.catalog.resolve(d.service_id, d.cues, d.unsupported)
                ctx.reasons.extend(vreasons)
            subs.append(
                SubRequest(
                    service_id=d.service_id,
                    intent=d.intent,  # type: ignore[arg-type]
                    variants=variants,
                    phrase=d.phrase,
                    language=d.language,
                    office_id=(
                        self.table.services[d.service_id].office_id
                        if d.service_id is not None
                        else d.office_id
                    ),
                )
            )
        needs_echo = ctx.needs_echo or any(d.low_confidence for d in drafts)
        if any(d.low_confidence for d in drafts):
            ctx.reasons.append("low_confidence_match")
        if needs_echo:
            return self._ask_confirm(session, subs, ctx, unavailable)
        self._remember(session, subs)
        session.pending = None
        return build("ok", sub_requests=subs)

    def _ask_confirm(
        self,
        session: SessionState,
        subs: list[SubRequest],
        ctx: _Ctx,
        unavailable: list[Unavailable],
    ) -> GatewayResult:
        items = [
            EchoItem(
                service_id=s.service_id,
                service_name=self._service_name(s.service_id) if s.service_id else None,
                intent=s.intent,
                variants=s.variants,
            )
            for s in subs
        ]
        parts = [
            f"{i.service_name or 'your application'} ({i.intent.replace('_', ' ')})" for i in items
        ]
        echo = Echo(items=items, text=f"I understood: {'; '.join(parts)}. Correct?")
        options = [
            ClarifyOption(id="confirm:yes", kind="confirm", label="yes"),
            ClarifyOption(id="confirm:no", kind="confirm", label="no"),
        ]
        session.pending = Pending(
            kind="confirm", options=options, sub_requests=subs, reasons=_unique(ctx.reasons)
        )
        return GatewayResult(
            status="echo_confirm",
            sub_requests=subs,
            clarify_options=options,
            clarify_kind="confirm",
            echo=echo,
            unavailable=unavailable,
            reasons=_unique(ctx.reasons),
            language=ctx.language,
        )

    @staticmethod
    def _remember(session: SessionState, subs: list[SubRequest]) -> None:
        withs = [s for s in subs if s.service_id is not None]
        if withs:
            session.resolved_service_id = withs[-1].service_id
            session.resolved_variants = dict(withs[-1].variants)
        if subs:
            session.last_intent = subs[-1].intent

    # ---------------------------------------------------------- answers to a question

    @staticmethod
    def _match_tap(session: SessionState, message: str) -> ClarifyOption | None:
        if session.pending is None:
            return None
        wanted = message.strip().lower()
        return next((o for o in session.pending.options if o.id.lower() == wanted), None)

    def _apply_option(self, session: SessionState, option: ClarifyOption) -> GatewayResult:
        pending = session.pending
        assert pending is not None
        ctx = _Ctx(needs_echo=pending.needs_echo, reasons=list(pending.reasons))
        ctx.reasons.append("answered_option")
        if pending.kind == "confirm":
            session.pending = None
            language = pending.sub_requests[0].language if pending.sub_requests else "en"
            if option.id == "confirm:yes":
                self._remember(session, pending.sub_requests)
                ctx.reasons.append("echo_confirmed")
                return GatewayResult(
                    status="ok", sub_requests=pending.sub_requests,
                    reasons=_unique(ctx.reasons), language=language,
                )  # fmt: skip
            ctx.reasons.append("echo_rejected")
            return GatewayResult(status="fallback", reasons=_unique(ctx.reasons), language=language)
        drafts = pending.drafts
        if pending.kind == "service":
            target = next((d for d in drafts if d.service_id is None and d.candidates), None)
            if target is not None:
                target.service_id, target.candidates = option.service_id, []
        else:
            for d in drafts:
                if d.intent is None:
                    d.intent = option.intent
        ctx.language = drafts[0].language if drafts else "en"
        session.pending = None
        return self._finish(session, drafts, ctx)

    def _answer_typed(
        self, session: SessionState, norm: Normalized, ctx: _Ctx
    ) -> GatewayResult | None:
        """Understand a typed reply to the pending question; None if it is not an answer."""
        pending = session.pending
        assert pending is not None
        words = [t.text for t in norm.words]
        options = {o.id: o for o in pending.options}
        chosen: ClarifyOption | None = None
        if pending.kind == "confirm":
            if 0 < len(words) <= CONFIRM_MAX_WORDS:
                yes = any(w in self.lexicon.confirm_yes for w in words)
                no = any(w in self.lexicon.confirm_no for w in words)
                if yes != no:
                    chosen = options["confirm:yes" if yes else "confirm:no"]
        elif pending.kind == "service":
            wanted = {o.service_id: o for o in pending.options if o.service_id}
            found = {
                c.target for m in self.linker.link(norm) for c in m.candidates if c.target in wanted
            }
            if len(found) == 1:
                chosen = wanted[next(iter(found))]
            else:
                winner = self.linker.cue_winner(words, list(wanted))
                chosen = wanted[winner] if winner else None
        else:
            found_intents = {h.intent for h in self.detector.detect(norm)}
            picks = [options[f"intent:{i}"] for i in found_intents if f"intent:{i}" in options]
            chosen = picks[0] if len(picks) == 1 else None
        if chosen is None:
            return None
        if ctx.reasons:
            pending.reasons = _unique([*pending.reasons, *ctx.reasons])
        return self._apply_option(session, chosen)


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


@lru_cache(maxsize=1)
def default_gateway() -> Gateway:
    """The gateway built from the repo's seed, aliases and config (built on first use)."""
    return Gateway()


def process(
    message: str, session: SessionState, now: float | datetime | None = None
) -> GatewayResult:
    """Turn one citizen message into a ``GatewayResult`` using the default gateway."""
    return default_gateway().process(message, session, now)
