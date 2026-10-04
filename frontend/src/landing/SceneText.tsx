// The nine scenes as real text: one labelled section each, in reading order. The picture behind them is
// decoration; every fact is here. Timings come from beats.ts, the same numbers the picture uses.
import type { CSSProperties, ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { SampleDataTag } from "../components/SampleDataTag";
import { BEAT, SUPPORT } from "./beats";
import { useHookShown, usePlayheadValue, useShown, useStill, wordsWindow } from "./hooks";
import { Kinetic } from "./Kinetic";
import { Poster } from "./Poster";
import { SCENES, sceneIndex, type SceneId } from "./scenes";

/** The sample question, shown as glowing words. Citizens write mixed messages, so it is Taglish. */
// NEEDS-NATIVE-REVIEW: Taglish sample question, not yet checked by a native speaker.
export const SAMPLE_QUESTION: { word: string; key?: boolean }[] = [
  { word: "Ano" },
  { word: "po" },
  { word: "ang" },
  { word: "requirements", key: true },
  { word: "para" },
  { word: "sa" },
  { word: "business", key: true },
  { word: "permit?", key: true },
];

type Vars = CSSProperties & Record<`--${string}`, string | number>;

/** CSS variables for an element that fades in over [a, b] on the playhead. */
export const fadeIn = (a: number, b: number): Vars => ({ "--a": a, "--b": b });
/** In over [a, b], out over [c, d]. */
export const fadeWindow = (a: number, b: number, c: number, d: number): Vars => ({ "--a": a, "--b": b, "--c": c, "--d": d });

function Frame({ id, children, label }: { id: SceneId; children: ReactNode; label: string }) {
  const index = sceneIndex(id);
  const still = useStill();
  return (
    <section
      className="lp-scene"
      data-scene={id}
      data-index={index}
      data-core={SCENES[index]!.core}
      data-active={still ? "true" : "false"}
      aria-labelledby={`lp-h-${id}`}
    >
      <div className="lp-poster">
        <Poster scene={id} label={label} />
      </div>
      {children}
    </section>
  );
}

/** Kicker, headline and support text of an ordinary scene. */
function Copy({ id, level = 2 }: { id: SceneId; level?: 1 | 2 }) {
  const { t } = useTranslation();
  const index = sceneIndex(id);
  const [from, to] = wordsWindow(index);
  const scrolled = useShown(from, to);
  const hooked = useHookShown();
  const shown = index === 0 ? hooked : scrolled;
  const Heading = level === 1 ? "h1" : "h2";
  const support = index === 0 ? ({ "--t": shown >= 1 ? 1 : 0 } as Vars) : fadeIn(index + SUPPORT[0], index + SUPPORT[1]);
  return (
    <div className="lp-copy">
      <p className="lp-kicker">{t(`landing.scenes.${id}.kicker`)}</p>
      <Heading id={`lp-h-${id}`} className="lp-headline" data-landed={shown > 0}>
        <Kinetic text={t(`landing.scenes.${id}.headline`)} shown={shown} />
      </Heading>
      <p className={index === 0 ? "lp-support lp-in" : "lp-support lp-t lp-in"} style={support}>
        {t(`landing.scenes.${id}.support`)}
      </p>
    </div>
  );
}

function Title() {
  const { t } = useTranslation();
  const hint = usePlayheadValue((p) => p.hook >= 1 && p.pos < 0.08);
  return (
    <Frame id="title" label={t("landing.scenes.title.poster")}>
      <Copy id="title" level={1} />
      <p className="lp-hint" data-on={hint} aria-hidden={!hint}>
        {t("landing.scroll")} <span aria-hidden="true">↓</span>
      </p>
    </Frame>
  );
}

function Guide() {
  const { t } = useTranslation();
  const langs = t("landing.scenes.guide.langs", { returnObjects: true }) as string[];
  return (
    <Frame id="guide" label={t("landing.scenes.guide.poster")}>
      <Copy id="guide" />
      <ul className="lp-subject lp-langs" aria-hidden="true">
        {langs.map((lang, i) => (
          <li key={lang} className="lp-callout lp-t lp-in" data-n={i} style={fadeIn(BEAT.langs[i]!, BEAT.langs[i]! + 0.06)}>
            {lang}
          </li>
        ))}
      </ul>
    </Frame>
  );
}

function ServiceIcon() {
  return (
    <svg viewBox="0 0 48 48" width="44" height="44" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M7 20 10 9h28l3 11" />
      <path d="M7 20a5.7 5.7 0 0 0 11.3 0 5.7 5.7 0 0 0 11.4 0A5.7 5.7 0 0 0 41 20" />
      <path d="M10 25v14h28V25" />
      <path d="M20 39V30h8v9" />
    </svg>
  );
}

function Shot({ n }: { n: number }) {
  const { t } = useTranslation();
  const start = 3 + n / 4;
  const [from, to] = wordsWindow(start, 0.25);
  const shown = useShown(from, to);
  const last = n === 3;
  return (
    <div className="lp-shot lp-win" style={fadeWindow(start, start + 0.015, last ? 5 : start + 0.225, last ? 6 : start + 0.245)}>
      <h3 className="lp-headline" data-landed={shown > 0}>
        <Kinetic text={t(`landing.scenes.journey.shots.${n}.headline`)} shown={shown} />
      </h3>
      <p className="lp-support lp-t lp-in" style={fadeIn(start + 0.075, start + 0.095)}>
        {t(`landing.scenes.journey.shots.${n}.support`)}
      </p>
    </div>
  );
}

function Journey() {
  const { t } = useTranslation();
  const offices = t("landing.scenes.journey.offices", { returnObjects: true }) as string[];
  const [q0, q1] = BEAT.question;
  const step = (q1 - q0) / SAMPLE_QUESTION.length;
  return (
    <Frame id="journey" label={t("landing.scenes.journey.poster")}>
      <div className="lp-copy">
        <h2 id="lp-h-journey" className="lp-kicker">
          {t("landing.scenes.journey.kicker")}
        </h2>
        <div className="lp-shots">
          {[0, 1, 2, 3].map((n) => (
            <Shot key={n} n={n} />
          ))}
        </div>
      </div>
      <div className="lp-subject lp-ask">
        <div
          className="lp-askbox"
          style={{ "--a2": BEAT.sweep[0] + 0.02, "--b2": BEAT.sweep[1] - 0.03, "--a3": BEAT.chips[0], "--b3": BEAT.chips[1], "--a4": BEAT.icon[0], "--b4": BEAT.icon[1], "--a5": BEAT.iconFly[0], "--b5": BEAT.iconFly[1] } as Vars}
        >
          <p className="lp-asklabel lp-win" style={fadeWindow(q0 - 0.02, q0, BEAT.chips[0], BEAT.chips[1])}>
            {t("landing.scenes.journey.askLabel")}
          </p>
          <p className="lp-question" lang="fil">
            {SAMPLE_QUESTION.map(({ word, key }, i) => (
              <span key={i} className="lp-qw lp-t" data-key={!!key} style={fadeIn(q0 + i * step, q0 + (i + 1.6) * step)}>
                {word}{" "}
              </span>
            ))}
          </p>
          <p className="lp-checked lp-win" style={fadeWindow(BEAT.checked[0], BEAT.checked[1], BEAT.chips[0], BEAT.chips[1])}>
            <span aria-hidden="true">✓</span> {t("landing.scenes.journey.checked")}
          </p>
          <p className="lp-service">
            <ServiceIcon />
            <span>{t("landing.scenes.journey.service")}</span>
          </p>
        </div>
      </div>
      <ul className="lp-offices">
        {offices.map((office, i) => (
          <li key={office} className="lp-label" data-anchor={`office${i}`} data-n={i}>
            {office}
          </li>
        ))}
      </ul>
      <p className="lp-label lp-label-hot" data-anchor="service" aria-hidden="true">
        {t("landing.scenes.journey.service")}
      </p>
    </Frame>
  );
}

function Answer() {
  const { t } = useTranslation();
  const still = useStill();
  const rows = t("landing.scenes.answer.rows", { returnObjects: true }) as string[];
  const counted = usePlayheadValue((p) => BEAT.ticks.filter((at) => p.pos >= at).length);
  const ticked = still ? rows.length : counted;
  const [a0, a1, a2, a3] = BEAT.arc;
  return (
    <Frame id="answer" label={t("landing.scenes.answer.poster")}>
      <Copy id="answer" />
      <div className="lp-subject lp-orbzone">
        <svg className="lp-arc lp-win" viewBox="0 0 200 200" aria-hidden="true" style={fadeWindow(a0, a1, a2, a3)}>
          <path id="lp-arc-path" d="M 22 100 A 78 78 0 0 1 178 100" fill="none" />
          <text>
            <textPath href="#lp-arc-path" startOffset="50%" textAnchor="middle">
              {t("landing.scenes.answer.arc")}
            </textPath>
          </text>
        </svg>
        <div className="lp-card lp-t" style={fadeIn(BEAT.card[0], BEAT.card[1])}>
          <div className="lp-cardhead">
            <p className="lp-cardtitle">{t("landing.scenes.answer.cardTitle")}</p>
            <SampleDataTag meta={{ mock: true }} />
          </div>
          <ul className="lp-rows">
            {rows.map((row, i) => (
              <li key={row} className="lp-row" data-on={i < ticked}>
                <span className="lp-box" aria-hidden="true" />
                <span className="lp-rowname">{row}</span>
                <span className="lp-rowvalue">{t("landing.scenes.answer.rowValue")}</span>
              </li>
            ))}
          </ul>
          <p className="lp-cardnote">{t("landing.scenes.answer.note")}</p>
        </div>
      </div>
    </Frame>
  );
}

function Request() {
  const { t } = useTranslation();
  return (
    <Frame id="request" label={t("landing.scenes.request.poster")}>
      <Copy id="request" />
      <p className="lp-label lp-label-idle" data-anchor="outside">
        {t("landing.scenes.request.outside")}
      </p>
      <div className="lp-label lp-alert" data-anchor="alert">
        <p className="lp-alerttag">{t("landing.scenes.request.alertTag")}</p>
        <p className="lp-alerttitle">{t("landing.scenes.request.alertTitle")}</p>
        <p className="lp-alertbody">{t("landing.scenes.request.alertBody")}</p>
        <div className="lp-draft lp-t" aria-hidden="true" style={fadeIn(BEAT.alert[0], BEAT.alert[1])}>
          <span />
          <span />
          <span />
        </div>
      </div>
    </Frame>
  );
}

function Close() {
  const { t } = useTranslation();
  return (
    <Frame id="close" label={t("landing.scenes.close.poster")}>
      <Copy id="close" />
      <div className="lp-subject lp-ctazone">
        <Link id="lp-cta" className="lp-cta lp-t" to="/" style={fadeIn(BEAT.cta[0], BEAT.cta[1])}>
          <span>{t("landing.scenes.close.cta")}</span>
          <span aria-hidden="true">→</span>
        </Link>
      </div>
      <p className="lp-closing">
        <span>{t("app.prototype")}</span>
        <Link className="lp-quiet" to="/help">
          {t("landing.scenes.close.reviewers")}
        </Link>
      </p>
    </Frame>
  );
}

function Plain({ id }: { id: SceneId }) {
  const { t } = useTranslation();
  return (
    <Frame id={id} label={t(`landing.scenes.${id}.poster`)}>
      <Copy id={id} />
    </Frame>
  );
}

export function Scenes() {
  return (
    <>
      <Title />
      <Plain id="question" />
      <Guide />
      <Journey />
      <Answer />
      <Plain id="watch" />
      <Request />
      <Plain id="together" />
      <Close />
    </>
  );
}
