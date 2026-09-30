import { useTranslation } from "react-i18next";
import { useOnline } from "../lib/useOnline";
import { Icon } from "./Icon";

/** Shown while the device has no connection. `forceShow` is for the design page. */
export function OfflineBanner({ forceShow = false }: { forceShow?: boolean }) {
  const { t } = useTranslation();
  const online = useOnline();
  if (online && !forceShow) return null;
  return (
    <div
      role="status"
      className="flex items-center gap-3 bg-banner-bg px-4 py-3 text-body text-on-banner"
    >
      <span className="text-banner-accent">
        <Icon name="wifiOff" className="size-6" />
      </span>
      <p>{t("offline.banner")}</p>
    </div>
  );
}
