import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { ramp, useBeatProgress } from "./hooks";
import { Kinetic } from "./Kinetic";

const CHIPS = ["hudLocal", "hudOffline", "hudReadOnly"] as const;
/** The status read-out: how it is meant to run. These are design facts, not measurements. */
const READOUT = ["readModel", "readNetwork", "readGraph", "readTarget"] as const;

/** Beat 8: runs on the office's own machine, offline; then the way into the app. */
export function LocalBeat() {
  const { t } = useTranslation();
  const p = useBeatProgress("local", 50);
  return (
    <section className="lp-section" data-beat="local" aria-labelledby="lp-local-h">
      <div className="lp-copy">
        <p className="lp-kicker" aria-hidden="true">
          08 / 08
        </p>
        <h2 id="lp-local-h" className="lp-h2 lp-glitch">
          <Kinetic text={t("landing.localTitle")} shown={ramp(p, 0, 0.4)} />
        </h2>
        <p style={{ opacity: ramp(p, 0.15, 0.5) }}>{t("landing.localBody")}</p>
        <ul className="lp-hudrow" style={{ opacity: ramp(p, 0.3, 0.65) }}>
          {CHIPS.map((key) => (
            <li key={key} className="lp-hud">
              {t(`landing.${key}`)}
            </li>
          ))}
        </ul>
        <Link to="/" className="lp-cta" style={{ opacity: ramp(p, 0.45, 0.8) }}>
          {t("landing.cta")}
        </Link>
      </div>
      <div className="lp-visual" style={{ opacity: ramp(p, 0.25, 0.7) }}>
        <dl className="lp-readout">
          {READOUT.map((key) => (
            <div key={key}>
              <dt>{t(`landing.${key}.label`)}</dt>
              <dd>{t(`landing.${key}.value`)}</dd>
            </div>
          ))}
        </dl>
        <p className="lp-fine">{t("landing.readNote")}</p>
      </div>
    </section>
  );
}
