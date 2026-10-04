import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { ramp, useBeatProgress } from "./hooks";
import { Kinetic } from "./Kinetic";

const CHIPS = ["hudLocal", "hudOffline", "hudReadOnly"] as const;

/** Beat 8: runs on the office's own machine, offline; then the way into the app. */
export function LocalBeat() {
  const { t } = useTranslation();
  const p = useBeatProgress("local");
  return (
    <section className="lp-section" aria-labelledby="lp-local-h">
      <h2 id="lp-local-h" className="lp-h2">
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
    </section>
  );
}
