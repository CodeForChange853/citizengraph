import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import { Button } from "../components/Button";
import { ChecklistCard } from "../components/ChecklistCard";
import { Icon } from "../components/Icon";
import { removeChecklist, useSavedChecklists, type SavedChecklist } from "../lib/checklistStore";

function SavedItem({ entry, defaultOpen }: { entry: SavedChecklist; defaultOpen: boolean }) {
  const { t } = useTranslation();
  const [confirming, setConfirming] = useState(false);
  const meta = useMemo(
    () => ({ serviceId: entry.serviceId, name: entry.name, office: entry.office, items: entry.items }),
    [entry.serviceId, entry.name, entry.office, entry.items],
  );
  const done = entry.ticked.filter((item) => entry.items.includes(item)).length;
  return (
    <article
      aria-label={entry.name}
      className="rounded-lg border-2 border-border bg-surface p-4 shadow-card"
    >
      <details open={defaultOpen}>
        <summary className="flex min-h-11 cursor-pointer flex-col gap-0.5">
          <span className="text-lead font-bold">{entry.name}</span>
          <span className="flex items-center gap-1.5 text-body text-fg-muted">
            <Icon name="building" className="size-4" />
            {entry.office}
          </span>
          <span className="text-body font-bold">{t("answer.ready", { done, total: entry.items.length })}</span>
        </summary>
        <div className="mt-4 flex flex-col gap-4">
          <ChecklistCard meta={meta} />
          {confirming ? (
            <div className="flex flex-wrap items-center gap-2" role="group" aria-label={t("saved.removeAsk")}>
              <p className="text-body font-bold">{t("saved.removeAsk")}</p>
              <Button variant="secondary" icon="trash" onClick={() => removeChecklist(entry.serviceId)}>
                {t("saved.removeYes")}
              </Button>
              <Button variant="ghost" onClick={() => setConfirming(false)}>
                {t("saved.removeNo")}
              </Button>
            </div>
          ) : (
            <div>
              <Button variant="ghost" icon="trash" onClick={() => setConfirming(true)}>
                {t("saved.remove")}
              </Button>
            </div>
          )}
        </div>
      </details>
    </article>
  );
}

/** Checklists kept on this device. Works with no signal: nothing here calls the API. */
export default function Saved() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const saved = useSavedChecklists();
  return (
    <div className="flex flex-col gap-5">
      <h1 className="text-heading font-bold">{t("saved.title")}</h1>
      <p className="text-body text-fg-muted">{t("saved.note")}</p>
      {saved.length === 0 ? (
        <section className="flex flex-col gap-4 rounded-lg border-2 border-border bg-surface p-4 shadow-card">
          <p className="text-body">{t("saved.empty")}</p>
          <div>
            <Button icon="ask" onClick={() => void navigate("/")}>
              {t("saved.ask")}
            </Button>
          </div>
        </section>
      ) : (
        <ul className="flex flex-col gap-4">
          {saved.map((entry, i) => (
            <li key={entry.serviceId}>
              <SavedItem entry={entry} defaultOpen={i === 0} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
