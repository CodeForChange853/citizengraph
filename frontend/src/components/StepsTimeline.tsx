import { useTranslation } from "react-i18next";
import type { StepItem } from "../api/types";
import { localizeTime } from "../lib/time";
import { Icon } from "./Icon";

/** Numbered timeline. Each step shows its own time, or says it is not listed. */
export function StepsTimeline({ serviceId, steps }: { serviceId: string; steps: StepItem[] }) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language === "fil" ? "fil" : "en";
  const id = `steps-${serviceId}`;
  if (steps.length === 0) return null;
  return (
    <section aria-labelledby={id} className="flex flex-col gap-3">
      <h3 id={id} className="text-title font-bold">
        {t("answer.steps")}
      </h3>
      <ol className="flex flex-col">
        {steps.map((step, i) => (
          <li key={step.order} className="relative flex gap-3 pb-5 last:pb-0">
            {i < steps.length - 1 ? (
              <span aria-hidden="true" className="absolute left-[0.9rem] top-9 bottom-0 w-0.5 bg-border-strong" />
            ) : null}
            <span
              aria-hidden="true"
              className="z-10 flex size-8 shrink-0 items-center justify-center rounded-full bg-primary-bg text-body font-bold text-on-primary"
            >
              {step.order}
            </span>
            <div className="flex min-w-0 flex-col gap-1 pt-0.5">
              <p className="text-body">
                <span className="sr-only">{t("answer.stepNumber", { n: step.order })} </span>
                {step.text}
              </p>
              <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-body text-fg-muted">
                <span className="inline-flex items-center gap-1.5">
                  <Icon name="clock" className="size-4" />
                  {step.time_text ? t("answer.stepTime", { time: localizeTime(step.time_text, lang, t) }) : t("answer.stepNoTime")}
                </span>
                {step.external ? (
                  <span className="inline-flex items-center gap-1.5 font-bold">
                    <Icon name="building" className="size-4" />
                    {t("answer.otherOffice")}
                  </span>
                ) : null}
              </p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
