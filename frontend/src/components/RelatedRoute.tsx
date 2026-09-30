import { useTranslation } from "react-i18next";
import type { Related } from "../api/types";
import { Icon } from "./Icon";

/** "You will also need": get something at another office first, then come back. */
export function RelatedRoute({ serviceId, related }: { serviceId: string; related: Related[] }) {
  const { t } = useTranslation();
  const id = `also-${serviceId}`;
  if (related.length === 0) return null;
  return (
    <section aria-labelledby={id} className="flex flex-col gap-3">
      <h3 id={id} className="text-title font-bold">
        {t("answer.also")}
      </h3>
      <ul className="flex flex-col gap-3">
        {related.map((r) => (
          <li key={`${r.office}-${r.label}`} className="flex gap-3 rounded-md border-2 border-border-strong bg-surface-2 p-3">
            <span className="mt-0.5 text-primary">
              <Icon name="arrowRight" className="size-6" />
            </span>
            <div className="flex flex-col gap-0.5">
              <p className="text-lead font-bold">{t("answer.alsoGoTo", { office: r.office })}</p>
              <p className="text-body">{r.label}</p>
              <p className="text-body text-fg-muted">{r.note}</p>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
