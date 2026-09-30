import { useTranslation } from "react-i18next";
import { Icon } from "./Icon";

/** Calm notice for info_status "pending_lgu". Not red: nothing is wrong, it is being verified. */
export function PendingBanner() {
  const { t } = useTranslation();
  return (
    <div
      role="note"
      className="flex gap-3 rounded-md border-l-8 border-notice-accent bg-notice-bg p-4 text-on-notice"
    >
      <span className="mt-0.5 text-notice-icon">
        <Icon name="info" className="size-6" />
      </span>
      <div>
        <p className="text-lead font-bold">{t("pending.title")}</p>
        <p className="text-body">{t("pending.body")}</p>
      </div>
    </div>
  );
}
