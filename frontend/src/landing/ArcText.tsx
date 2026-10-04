import { useTranslation } from "react-i18next";
import { ramp, useBeatProgress } from "./hooks";

/** Beat 5: "retrieved, never generated" set on an arc that draws itself as the trail arrives. */
export function ArcText() {
  const { t } = useTranslation();
  const p = useBeatProgress("trail");
  return (
    <div className="lp-arc" style={{ opacity: ramp(p, 0.05, 0.3) }}>
      <svg viewBox="0 0 600 132" role="img" aria-label={t("landing.arc")}>
        <path
          id="lp-arc-path"
          d="M 40 124 A 520 520 0 0 1 560 124"
          pathLength={1}
          strokeDasharray={1}
          strokeDashoffset={1 - ramp(p, 0.05, 0.7)}
        />
        <text aria-hidden="true" dy="-14" style={{ opacity: ramp(p, 0.45, 0.95) }}>
          <textPath href="#lp-arc-path" startOffset="50%" textAnchor="middle">
            {t("landing.arc")}
          </textPath>
        </text>
      </svg>
    </div>
  );
}
