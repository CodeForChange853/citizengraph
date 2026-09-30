import { useTranslation } from "react-i18next";

/** Small tag shown when the response says meta.mock = true. */
export function SampleDataTag({ meta }: { meta?: { mock?: boolean } }) {
  const { t } = useTranslation();
  if (!meta?.mock) return null;
  return (
    <span className="inline-flex items-center rounded-full border border-border-strong bg-surface-2 px-2.5 py-0.5 text-caption font-bold text-fg-muted">
      {t("app.sampleData")}
    </span>
  );
}
