import type { CSSProperties } from "react";
import { useTranslation } from "react-i18next";
import { SampleDataTag } from "../components/SampleDataTag";
import { DEMO_SERVICE } from "./demo";
import { ramp, useBeatProgress } from "./hooks";
import { Kinetic } from "./Kinetic";

/** The kinds of fact an answer holds. The landing page shows where they go, never their values. */
const ROWS = ["rowBring", "rowFee", "rowTime"] as const;

/**
 * Beat 6: the orb's ring opens into a SAMPLE answer card. The card names the service and its office and
 * shows neutral placeholders only: no amount, no time, no count and no checklist is shown or invented.
 */
export function SampleCard() {
  const { t } = useTranslation();
  const p = useBeatProgress("answer", 50);
  const open = ramp(p, 0.2, 0.8);
  return (
    <section className="lp-section" data-beat="answer" aria-labelledby="lp-answer-h">
      <div className="lp-copy">
        <p className="lp-kicker" aria-hidden="true">
          06 / 08
        </p>
        <h2 id="lp-answer-h" className="lp-h2 lp-glitch">
          <Kinetic text={t("landing.sampleTitle")} shown={ramp(p, 0, 0.45)} />
        </h2>
        <p style={{ opacity: ramp(p, 0.2, 0.55) }}>{t("landing.sampleBody")}</p>
      </div>
      <div className="lp-visual">
        <div className="lp-cardwrap" style={{ "--k": 1 - open } as CSSProperties}>
          <div className="lp-ring" aria-hidden="true" style={{ opacity: ramp(p, 0.02, 0.15) }} />
          <div className="lp-card" style={{ opacity: ramp(p, 0.45, 0.8) }}>
            <div className="lp-card-head">
              <span className="lp-hud">{DEMO_SERVICE.office}</span>
              <SampleDataTag meta={{ mock: true }} />
            </div>
            <h3>{DEMO_SERVICE.name}</h3>
            <dl className="lp-rows">
              {ROWS.map((key) => (
                <div key={key} className="lp-row">
                  <dt>{t(`landing.${key}`)}</dt>
                  <dd>
                    {t("landing.rowValue")}
                    <span className="lp-bar" aria-hidden="true" />
                  </dd>
                </div>
              ))}
            </dl>
            <p className="lp-fine">{t("landing.sampleNote")}</p>
          </div>
        </div>
      </div>
    </section>
  );
}
