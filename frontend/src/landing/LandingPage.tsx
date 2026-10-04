import "@fontsource/atkinson-hyperlegible-mono/latin-400.css";
import "@fontsource/atkinson-hyperlegible-mono/latin-700.css";
import { useRef, useState, type MouseEvent } from "react";
import { useTranslation } from "react-i18next";
import type { Lang } from "../api/types";
import { setLanguage } from "../i18n";
import { ArcText } from "./ArcText";
import { CUES, OFFICES, SERVICE_TOTAL } from "./demo";
import { Grain } from "./Grain";
import { TimelineContext, usePrefersReducedMotion, useTimelineValue } from "./hooks";
import { Kinetic } from "./Kinetic";
import "./landing.css";
import { LocalBeat } from "./LocalBeat";
import { STAGE_VARS } from "./palette";
import { usePlayback } from "./playback";
import { SampleCard } from "./SampleCard";
import { SlaBeat } from "./SlaBeat";
import { useSound } from "./sound";
import { StageCanvas } from "./StageCanvas";
import "./strings";
import { Terminal } from "./Terminal";
import { Timeline } from "./timeline";

const LANGS: Lang[] = ["en", "fil"];

function Stage({ timeline, reduced }: { timeline: Timeline; reduced: boolean }) {
  const { t, i18n } = useTranslation();
  const mainRef = useRef<HTMLElement>(null);
  const zoneRef = useRef<HTMLDivElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  usePlayback(timeline, reduced, rootRef);
  const sound = useSound(timeline, reduced);

  const playing = useTimelineValue((tl) => tl.playing);
  const introDone = useTimelineValue((tl) => tl.introDone);
  const headline = useTimelineValue((tl) => Math.round(tl.progress("contours") * 8) / 8);
  const hud = useTimelineValue((tl) => tl.progress("offices") > 0.6);
  const hint = useTimelineValue((tl) => tl.introDone && tl.progress("trail") === 0);
  const lang: Lang = i18n.language === "fil" ? "fil" : "en";

  function skip(event: MouseEvent) {
    event.preventDefault();
    timeline.skipIntro();
    mainRef.current?.focus({ preventScroll: true });
  }

  function replay() {
    window.scrollTo(0, 0);
    timeline.replay();
  }

  return (
    <div ref={rootRef} className="lp" style={STAGE_VARS} data-motion={reduced ? "static" : "full"} data-playing={playing}>
      <a className="lp-skip" href="#lp-main" data-idle={introDone} onClick={skip}>
        {t("landing.skipIntro")}
      </a>
      <Grain />
      <main id="lp-main" ref={mainRef} tabIndex={-1}>
        <div className="lp-stagewrap" data-beat="trail">
          <div className="lp-stage">
            <StageCanvas zoneRef={zoneRef} />
            <div className="lp-top">
              <div>
                <p className="lp-brand">{t("app.name")}</p>
                <p className="lp-proto">{t("app.prototype")}</p>
              </div>
              <div className="lp-controls">
                <div className="lp-seg" role="group" aria-label={t("lang.label")}>
                  {LANGS.map((code) => (
                    <button
                      key={code}
                      type="button"
                      className="lp-btn"
                      aria-pressed={lang === code}
                      aria-label={t(`lang.${code}`)}
                      onClick={() => void setLanguage(code)}
                    >
                      {code.toUpperCase()}
                    </button>
                  ))}
                </div>
                {sound.available ? (
                  <button type="button" className="lp-btn" data-on={sound.enabled} aria-pressed={sound.enabled} onClick={sound.toggle}>
                    {t(sound.enabled ? "landing.soundOn" : "landing.soundOff")}
                  </button>
                ) : null}
                {introDone && !reduced ? (
                  <button
                    type="button"
                    className="lp-btn"
                    aria-label={t("landing.replay")}
                    title={t("landing.replay")}
                    onClick={replay}
                  >
                    <span aria-hidden="true">↻</span>
                  </button>
                ) : null}
              </div>
            </div>
            <div className="lp-body">
              <div className="lp-hero">
                <h1 className="lp-h1">
                  <Kinetic text={t("landing.title")} shown={headline} />
                </h1>
                <Terminal />
              </div>
              <div className="lp-graphzone" ref={zoneRef}>
                <ul className="lp-hudrow lp-stagehud" style={{ opacity: hud ? 1 : 0 }}>
                  <li className="lp-hud">{t("landing.hudOffices", { count: OFFICES.length })}</li>
                  <li className="lp-hud">{t("landing.hudServices", { count: SERVICE_TOTAL })}</li>
                </ul>
                <ArcText />
              </div>
            </div>
            {reduced ? null : (
              <p className="lp-hint lp-mono" style={{ opacity: hint ? 1 : 0 }}>
                {t("landing.scrollHint")} <span aria-hidden="true">↓</span>
              </p>
            )}
          </div>
        </div>
        <SampleCard />
        <SlaBeat />
        <LocalBeat />
      </main>
      <footer className="lp-foot">{t("app.prototype")}</footer>
    </div>
  );
}

export function LandingPage() {
  const reduced = usePrefersReducedMotion();
  const [timeline] = useState(() => new Timeline(CUES));
  return (
    <TimelineContext.Provider value={timeline}>
      <Stage timeline={timeline} reduced={reduced} />
    </TimelineContext.Provider>
  );
}
