import { useTranslation } from "react-i18next";

// Stand-in for screens built in later stages (chat: stage 3; saved and help: stage 4).
export default function Placeholder({ title }: { title: string }) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-2">
      <h1 className="text-heading font-bold">{title}</h1>
      <p className="text-body">{t("placeholder.soon")}</p>
    </div>
  );
}
