import { useTranslation } from "react-i18next";
import { InfoScent } from "../components/InfoScent";
import { SampleDataTag } from "../components/SampleDataTag";
import { DEMO_SERVICE } from "./demo";
import { ramp, useBeatProgress } from "./hooks";
import { Kinetic } from "./Kinetic";

/** Beat 6: a SAMPLE answer card. Every fact on it is read from the mock API's sample data. */
export function SampleCard() {
  const { t } = useTranslation();
  const p = useBeatProgress("answer");
  const card = ramp(p, 0.3, 0.9);
  return (
    <section className="lp-section" aria-labelledby="lp-answer-h">
      <h2 id="lp-answer-h" className="lp-h2">
        <Kinetic text={t("landing.sampleTitle")} shown={ramp(p, 0, 0.45)} />
      </h2>
      <div className="lp-card" style={{ opacity: card, transform: `translateY(${(1 - card) * 1.5}rem)` }}>
        <div className="lp-card-head">
          <span className="lp-hud">{DEMO_SERVICE.office}</span>
          <SampleDataTag meta={{ mock: true }} />
        </div>
        <h3>{DEMO_SERVICE.name}</h3>
        <InfoScent summary={DEMO_SERVICE.summary} status={DEMO_SERVICE.info_status} size="fact" />
        <p>{t("landing.sampleNote")}</p>
      </div>
    </section>
  );
}
