import { useTranslation } from "react-i18next";
import { cypherChars, DEMO_CYPHER, DEMO_QUESTION, ENTER_AT, GUARD_CHECKS, guardTicks, LINE_MS, typedChars } from "./demo";
import { easeOutCubic } from "./ease";
import { useTimelineValue } from "./hooks";

/**
 * Beats 1 and 4: the prompt line with its caret, the typed question, then the illustrative query and
 * the guardrail checks. Screen readers get the whole text at once; the typing is visual only.
 */
export function Terminal() {
  const { t } = useTranslation();
  const line = useTimelineValue((tl) => Math.round(easeOutCubic(tl.into("ask") / LINE_MS) * 24) / 24);
  const typed = useTimelineValue((tl) => typedChars(tl.into("ask")));
  const sent = useTimelineValue((tl) => tl.into("ask") >= ENTER_AT);
  const code = useTimelineValue((tl) => cypherChars(tl.into("query")));
  const ticks = useTimelineValue((tl) => guardTicks(tl.into("query")));
  // While typing, the word in progress is highlighted; once the question is complete nothing is.
  const wordStart = typed >= DEMO_QUESTION.length ? typed : DEMO_QUESTION.lastIndexOf(" ", typed - 1) + 1;

  return (
    <div className="lp-term">
      <p className="lp-term-label">{t("landing.questionLabel")}</p>
      <p className="lp-ask">
        <span className="lp-sr">{DEMO_QUESTION}</span>
        <span aria-hidden="true" data-testid="lp-typed" data-count={typed}>
          <span className="lp-prompt">&gt; </span>
          {DEMO_QUESTION.slice(0, wordStart)}
          <span className="lp-new">{DEMO_QUESTION.slice(wordStart, typed)}</span>
          {code === 0 ? <span className="lp-caret" /> : null}
          <span className="lp-ghost">{DEMO_QUESTION.slice(typed)}</span>
          {/* The canvas reads this marker: rings ripple from here and the trail starts here. */}
          <span data-lp-origin="" />
          <span className="lp-enter" style={{ opacity: sent ? 1 : 0 }}>
            ↵
          </span>
        </span>
      </p>
      <div className="lp-amber" style={{ transform: `scaleX(${line})` }} />

      <div className="lp-cypher" style={{ opacity: code > 0 ? 1 : 0 }}>
        <p className="lp-term-label">{t("landing.cypherLabel")}</p>
        <pre className="lp-code">
          <code>
            <span className="lp-sr">{DEMO_CYPHER}</span>
            <span aria-hidden="true" data-testid="lp-code" data-count={code}>
              {DEMO_CYPHER.slice(0, code)}
              {code > 0 && code < DEMO_CYPHER.length ? <span className="lp-caret" /> : null}
              <span className="lp-ghost">{DEMO_CYPHER.slice(code)}</span>
            </span>
          </code>
        </pre>
        <ul className="lp-guard" aria-label={t("landing.guardTitle")}>
          {GUARD_CHECKS.map((key, i) => (
            <li key={key} data-on={i < ticks} style={{ opacity: i < ticks ? 1 : 0 }}>
              <span className="lp-tick" aria-hidden="true">
                ✓
              </span>
              {t(`landing.guard.${key}`)}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
