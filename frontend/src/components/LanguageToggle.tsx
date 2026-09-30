import { useTranslation } from "react-i18next";
import type { Lang } from "../api/types";
import { setLanguage } from "../i18n";
import { Segmented } from "./Segmented";

/** EN / FIL. Controls reply and screen language only; the citizen may type in either. */
export function LanguageToggle() {
  const { t, i18n } = useTranslation();
  const value: Lang = i18n.language === "fil" ? "fil" : "en";
  return (
    <Segmented<Lang>
      label={t("lang.label")}
      value={value}
      onChange={(lang) => void setLanguage(lang)}
      options={[
        { value: "en", label: "EN", title: t("lang.en") },
        { value: "fil", label: "FIL", title: t("lang.fil") },
      ]}
    />
  );
}
