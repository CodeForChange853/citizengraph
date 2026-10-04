import { useTranslation } from "react-i18next";
import { ramp, useBeatProgress } from "./hooks";
import { Kinetic } from "./Kinetic";

/** Illustrative step states. The outside-agency step is waiting time the office is not charged with. */
const STEPS = ["onTime", "external", "late", "waiting"] as const;

/**
 * Beat 7: Core 2 checks each step against its timeline and drafts an alert for staff to review.
 * The steps stand on a perspective floor grid; only the late step raises the alert.
 */
export function SlaBeat() {
  const { t } = useTranslation();
  const p = useBeatProgress("sla", 50);
  const alert = ramp(p, 0.7, 0.95);
  return (
    <section className="lp-section lp-sla" data-beat="sla" aria-labelledby="lp-sla-h">
      <div className="lp-floor" aria-hidden="true" />
      <div className="lp-copy">
        <p className="lp-kicker" aria-hidden="true">
          07 / 08
        </p>
        <h2 id="lp-sla-h" className="lp-h2 lp-glitch">
          <Kinetic text={t("landing.slaTitle")} shown={ramp(p, 0, 0.35)} />
        </h2>
        <p style={{ opacity: ramp(p, 0.1, 0.4) }}>{t("landing.slaBody")}</p>
      </div>
      <div className="lp-visual">
        <ol className="lp-steps">
          {STEPS.map((state, i) => (
            <li
              key={state}
              className="lp-step"
              data-state={state}
              style={{ opacity: ramp(p, 0.2 + i * 0.12, 0.35 + i * 0.12) }}
            >
              <span className="lp-step-n">{t("landing.slaStep", { n: i + 1 })}</span>
              <span className="lp-step-state">{t(`landing.sla.${state}`)}</span>
              {state === "late" ? (
                <p className={`lp-alert lp-hud${alert > 0.5 ? " lp-bloom" : ""}`} style={{ opacity: alert }}>
                  {t("landing.slaAlert")}
                </p>
              ) : null}
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
