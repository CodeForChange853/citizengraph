import { useTranslation } from "react-i18next";
import { useChecklist, type ChecklistMeta } from "../lib/checklistStore";
import { Button } from "./Button";
import { Icon } from "./Icon";

/**
 * "What to bring" as a tickable checklist. Ticks are saved on this device (no account),
 * so the citizen can come back with no signal and see what is still missing.
 */
export function ChecklistCard({ meta }: { meta: ChecklistMeta }) {
  const { t } = useTranslation();
  const { ticked, done, total, kept, toggle, keep } = useChecklist(meta);
  const pct = total === 0 ? 0 : Math.round((done / total) * 100);
  const headingId = `bring-${meta.serviceId}`;

  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-3">
      <div className="flex items-baseline justify-between gap-3">
        <h3 id={headingId} className="text-title font-bold">
          {t("answer.bring")}
        </h3>
        {total > 0 ? (
          <p className="text-lead font-bold" aria-live="polite">
            {t("answer.ready", { done, total })}
          </p>
        ) : null}
      </div>

      {total > 0 ? (
        <div
          role="progressbar"
          aria-label={t("answer.progressLabel")}
          aria-valuemin={0}
          aria-valuemax={total}
          aria-valuenow={done}
          aria-valuetext={t("answer.ready", { done, total })}
          className="h-3 overflow-hidden rounded-full bg-track"
        >
          <div className="h-full rounded-full bg-primary" style={{ width: `${pct}%` }} />
        </div>
      ) : null}

      {total === 0 ? (
        <p className="text-body">{t("answer.nothingToBring")}</p>
      ) : (
        <ul className="flex flex-col gap-1">
          {meta.items.map((item, i) => {
            const id = `${meta.serviceId}-item-${i}`;
            return (
              <li key={id}>
                <label
                  htmlFor={id}
                  className="flex min-h-11 cursor-pointer items-start gap-3 rounded-md px-1 py-2 hover:bg-surface-2"
                >
                  <input
                    id={id}
                    type="checkbox"
                    className="peer sr-only"
                    checked={ticked.has(item)}
                    onChange={() => toggle(item)}
                  />
                  <span
                    aria-hidden="true"
                    className={`mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-sm border-2 peer-focus-visible:outline-3 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-focus ${
                      ticked.has(item)
                        ? "border-primary-bg bg-primary-bg text-on-primary"
                        : "border-border-strong bg-surface"
                    }`}
                  >
                    {ticked.has(item) ? <Icon name="check" className="size-5" /> : null}
                  </span>
                  <span className="text-body">{item}</span>
                </label>
              </li>
            );
          })}
        </ul>
      )}

      {total > 0 ? (
        kept ? (
          <p className="flex items-center gap-2 text-body text-fg-muted">
            <Icon name="check" />
            {t("answer.kept")}
          </p>
        ) : (
          <div>
            <Button variant="secondary" icon="bookmark" onClick={keep}>
              {t("answer.keep")}
            </Button>
          </div>
        )
      ) : null}
    </section>
  );
}
