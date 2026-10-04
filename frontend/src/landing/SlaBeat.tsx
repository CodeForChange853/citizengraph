import { useTranslation } from "react-i18next";
import { ramp, useBeatProgress } from "./hooks";
import { Kinetic } from "./Kinetic";

/** Illustrative step states. The outside-agency step is waiting time the office is not charged with. */
const STEPS = ["onTime", "external", "late", "waiting"] as const;

/** Beat 7: Core 2 checks each step against its timeline and drafts an alert for staff to review. */
export function SlaBeat() {
  const { t } = useTranslation();
  const p = useBeatProgress("sla");
  const alert = ramp(p, 0.7, 0.95);
  return (
    <section className="lp-section lp-sla" data-beat="sla" aria-labelledby="lp-sla-h">
      <div className="lp-floor" aria-hidden="true" />
      <h2 id="lp-sla-h" className="lp-h2">
        <Kinetic text={t("landing.slaTitle")} shown={ramp(p, 0, 0.35)} />
      </h2>
      <p style={{ opacity: ramp(p, 0.1, 0.4) }}>{t("landing.slaBody")}</p>
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
    </section>
  );
}
