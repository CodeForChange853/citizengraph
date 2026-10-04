import "@fontsource/archivo/latin-800.css";
import "@fontsource/atkinson-hyperlegible-mono/latin-400.css";
import "@fontsource/atkinson-hyperlegible-mono/latin-700.css";
import { lazy, Suspense, useCallback, useRef, useState, type MouseEvent } from "react";
import { I18nextProvider, useTranslation } from "react-i18next";
import { CUES } from "./beats";
import { LANDING_FIL_ENABLED, landingI18n } from "./copy";
import { PlayheadContext, StillContext, usePlayheadValue, usePrefersReducedMotion } from "./hooks";
import "./landing.css";
import { Playhead } from "./playhead";
import { anchorPos, END, posToFraction, SCENE_COUNT, SCENES, TOTAL_VH } from "./scenes";
import { Scenes } from "./SceneText";
import { useSound } from "./sound";
import { useStory } from "./story";
import { STAGE_VARS } from "./tokens";

// three.js and the shaders: a chunk of its own, fetched after the page has painted.
const Stage3D = lazy(() => import("./gl/Stage3D"));

/** True when this browser can give us a WebGL 2 context. Nothing is created in tests or on old devices. */
function canWebGL(): boolean {
  if (typeof WebGL2RenderingContext === "undefined") return false;
  try {
    return !!document.createElement("canvas").getContext("webgl2");
  } catch {
    return false;
  }
}

const LANGS = ["en", "fil"] as const;

function Dots() {
  const { t } = useTranslation();
  const current = usePlayheadValue((p) => Math.min(SCENE_COUNT - 1, Math.floor(p.target + 0.02)));
  return (
    <nav className="lp-dots" aria-label={t("landing.chapters")}>
      <ol>
        {SCENES.map((scene, i) => (
          <li key={scene.id}>
            <a href={`#lp-s-${scene.id}`} aria-current={current === i ? "step" : undefined} aria-label={`${i + 1}. ${t(`landing.scenes.${scene.id}.name`)}`}>
              <span aria-hidden="true" />
            </a>
          </li>
        ))}
      </ol>
    </nav>
  );
}

function Counter() {
  const { t } = useTranslation();
  const current = usePlayheadValue((p) => Math.min(SCENE_COUNT - 1, Math.floor(p.pos + 0.02)));
  const two = (n: number) => String(n).padStart(2, "0");
  return (
    <p className="lp-counter" aria-hidden="true">
      <span>
        {two(current + 1)} / {two(SCENE_COUNT)}
      </span>
      <span>{t(`landing.scenes.${SCENES[current]!.id}.name`)}</span>
    </p>
  );
}

function Page({ playhead, reduced }: { playhead: Playhead; reduced: boolean }) {
  const { t } = useTranslation();
  const rootRef = useRef<HTMLDivElement>(null);
  const trackRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const [gl, setGl] = useState<"off" | "loading" | "on">(() => (!reduced && canWebGL() ? "loading" : "off"));
  const story = useStory(playhead, reduced, rootRef, trackRef, stageRef);
  const sound = useSound(playhead, reduced);
  const cuts = usePlayheadValue((p) => p.cuts);
  const onLost = useCallback(() => setGl("off"), []);
  const onReady = useCallback(() => setGl("on"), []);
  const picture = reduced ? "off" : gl;

  function skip(event: MouseEvent) {
    event.preventDefault();
    story.goTo(END);
    document.getElementById("lp-cta")?.focus({ preventScroll: true });
  }

  return (
    <div ref={rootRef} className="lp" lang="en" style={STAGE_VARS} data-motion={reduced ? "static" : "full"} data-gl={picture} data-filming={story.filming}>
      <a className="lp-skip" href="#lp-cta" onClick={skip}>
        {t("landing.skip")}
      </a>
      <header className="lp-top">
        <div className="lp-id">
          <p className="lp-brand">{t("app.name")}</p>
          <p className="lp-proto">{t("app.prototype")}</p>
        </div>
        <div className="lp-controls">
          <div className="lp-seg" role="group" aria-label={t("lang.label")} data-disabled={!LANDING_FIL_ENABLED}>
            {LANGS.map((code) => (
              <button key={code} type="button" className="lp-btn" aria-pressed={code === "en"} aria-disabled={!LANDING_FIL_ENABLED} aria-label={t(`lang.${code}`)}>
                {code.toUpperCase()}
              </button>
            ))}
          </div>
          {sound.available ? (
            <button type="button" className="lp-btn" data-on={sound.enabled} aria-pressed={sound.enabled} onClick={sound.toggle}>
              {t(sound.enabled ? "landing.soundOn" : "landing.soundOff")}
            </button>
          ) : null}
          {reduced ? null : (
            <button type="button" className="lp-btn lp-film" data-film="" data-on={story.filming} onClick={story.filming ? story.stopFilm : story.startFilm}>
              <span aria-hidden="true">{story.filming ? "■" : "▶"}</span> {t(story.filming ? "landing.filmStop" : "landing.film")}
            </button>
          )}
        </div>
      </header>
      <main id="lp-main">
        <div ref={trackRef} className="lp-track" style={{ "--lp-total": TOTAL_VH } as React.CSSProperties}>
          {SCENES.map((scene, i) => (
            <span key={scene.id} id={`lp-s-${scene.id}`} className="lp-mark" style={{ "--at": posToFraction(anchorPos(i)) } as React.CSSProperties} />
          ))}
          <div ref={stageRef} className="lp-stage" data-cut={cuts === 0 ? undefined : cuts % 2 ? "a" : "b"}>
            {picture !== "off" ? (
              <Suspense fallback={null}>
                <Stage3D playhead={playhead} stageRef={stageRef} onLost={onLost} onReady={onReady} />
              </Suspense>
            ) : null}
            <div className="lp-scenes">
              <Scenes />
            </div>
            <div className="lp-crop" aria-hidden="true" />
            {reduced ? null : <Counter />}
          </div>
        </div>
      </main>
      {reduced ? null : <Dots />}
      <div className="lp-progress" aria-hidden="true" />
    </div>
  );
}

export function LandingPage() {
  const reduced = usePrefersReducedMotion();
  const [playhead] = useState(() => new Playhead(CUES));
  return (
    <I18nextProvider i18n={landingI18n}>
      <PlayheadContext.Provider value={playhead}>
        <StillContext.Provider value={reduced}>
          <Page playhead={playhead} reduced={reduced} />
        </StillContext.Provider>
      </PlayheadContext.Provider>
    </I18nextProvider>
  );
}
