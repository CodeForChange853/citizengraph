import { useTranslation } from "react-i18next";
import { Icon } from "./Icon";

/** Office chips: the office that serves this, plus offices in the related route. Not tappable. */
export function WhereToGo({ serviceId, offices }: { serviceId: string; offices: string[] }) {
  const { t } = useTranslation();
  const id = `where-${serviceId}`;
  const unique = [...new Set(offices)];
  return (
    <section aria-labelledby={id} className="flex flex-col gap-3">
      <h3 id={id} className="text-title font-bold">
        {t("answer.where")}
      </h3>
      <ul className="flex flex-wrap gap-2">
        {unique.map((office) => (
          <li
            key={office}
            className="inline-flex min-h-11 items-center gap-2 rounded-full border-2 border-border-strong bg-surface-2 px-4 py-1.5 text-body font-bold"
          >
            <Icon name="pin" />
            {office}
          </li>
        ))}
      </ul>
    </section>
  );
}
