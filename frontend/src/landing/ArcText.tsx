import { useTranslation } from "react-i18next";
import { clamp01, ramp } from "./ease";
import { useBeatProgress } from "./hooks";

/**
 * Beat 5: "retrieved, never generated" on an arc over the graph. The letters appear one after another
 * as the trail travels, as if its head wrote them, and the arc then sits round the orb. The square
 * viewBox is centred on the graph, where the canvas draws the orb.
 */
export function ArcText() {
  const { t } = useTranslation();
  const p = useBeatProgress("trail", 100);
  const text = t("landing.arc");
  const written = ramp(p, 0.14, 0.48) * (text.length + 1);
  return (
    <div className="lp-arc" style={{ opacity: ramp(p, 0.1, 0.18) }}>
      <svg viewBox="0 0 400 400" preserveAspectRatio="xMidYMid meet" role="img" aria-label={text}>
        <path id="lp-arc-path" d="M 46 200 A 154 154 0 0 1 354 200" fill="none" />
        <text aria-hidden="true">
          <textPath href="#lp-arc-path" startOffset="50%" textAnchor="middle">
            {Array.from(text, (ch, i) => (
              <tspan key={i} fillOpacity={clamp01(written - i)} strokeOpacity={clamp01(written - i)}>
                {ch}
              </tspan>
            ))}
          </textPath>
        </text>
      </svg>
    </div>
  );
}

/** The meaning of the orb, as real text under it. */
export function OrbNote() {
  const { t } = useTranslation();
  const p = useBeatProgress("trail", 50);
  return (
    <p className="lp-orbnote" style={{ opacity: ramp(p, 0.8, 0.95) }}>
      <span>{t("landing.orbNote")}</span>
    </p>
  );
}
