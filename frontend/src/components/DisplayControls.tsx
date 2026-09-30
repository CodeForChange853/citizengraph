import { useTranslation } from "react-i18next";
import { updateSettings, useSettings, type TextSize, type Theme } from "../lib/settings";
import { Segmented } from "./Segmented";

/** Theme and text size. Both are saved on this device only. */
export function DisplayControls() {
  const { t } = useTranslation();
  const settings = useSettings();
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <span className="text-body font-bold">{t("display.theme")}</span>
        <div>
          <Segmented<Theme>
            label={t("display.theme")}
            value={settings.theme}
            onChange={(theme) => updateSettings({ theme })}
            options={[
              { value: "system", label: t("display.themeSystem") },
              { value: "light", label: t("display.themeLight") },
              { value: "dark", label: t("display.themeDark") },
            ]}
          />
        </div>
      </div>
      <div className="flex flex-col gap-2">
        <span className="text-body font-bold">{t("display.textSize")}</span>
        <div>
          <Segmented<TextSize>
            label={t("display.textSize")}
            value={settings.textSize}
            onChange={(textSize) => updateSettings({ textSize })}
            options={[
              { value: "normal", label: t("display.sizeNormal") },
              { value: "large", label: t("display.sizeLarge") },
              { value: "xlarge", label: t("display.sizeXlarge") },
            ]}
          />
        </div>
      </div>
    </div>
  );
}
