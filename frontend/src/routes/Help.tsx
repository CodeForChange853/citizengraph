import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { DisplayControls } from "../components/DisplayControls";
import { Icon } from "../components/Icon";
import { LanguageToggle } from "../components/LanguageToggle";

function Block({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section aria-labelledby={id} className="flex flex-col gap-2 rounded-lg border-2 border-border bg-surface p-4 shadow-card">
      <h2 id={id} className="text-title font-bold">
        {title}
      </h2>
      {children}
    </section>
  );
}

/** About, how to use, privacy, offline use, display settings. Plain short sentences. */
export default function Help() {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-heading font-bold">{t("help.title")}</h1>

      <div role="note" className="flex gap-3 rounded-md border-l-8 border-notice-accent bg-notice-bg p-4 text-on-notice">
        <span className="mt-0.5 text-notice-icon">
          <Icon name="info" className="size-6" />
        </span>
        <p className="text-lead font-bold">{t("app.prototype")}</p>
      </div>

      <Block id="help-about" title={t("help.aboutTitle")}>
        <p className="text-body">{t("help.about1")}</p>
        <p className="text-body">{t("help.about2")}</p>
      </Block>

      <Block id="help-how" title={t("help.howTitle")}>
        <ol className="list-decimal space-y-1 pl-6 text-body">
          <li>{t("help.how1")}</li>
          <li>{t("help.how2")}</li>
          <li>{t("help.how3")}</li>
        </ol>
      </Block>

      <Block id="help-pending" title={t("help.pendingTitle")}>
        <p className="text-body">{t("help.pending")}</p>
      </Block>

      <Block id="help-privacy" title={t("help.privacyTitle")}>
        <p className="text-body">{t("help.privacy1")}</p>
        <p className="text-body">{t("help.privacy2")}</p>
        <p className="text-body">{t("help.privacy3")}</p>
      </Block>

      <Block id="help-offline" title={t("help.offlineTitle")}>
        <p className="text-body">{t("help.offline")}</p>
      </Block>

      <Block id="help-sample" title={t("help.sampleTitle")}>
        <p className="text-body">{t("help.sample")}</p>
      </Block>

      <Block id="help-display" title={t("help.displayTitle")}>
        <div className="flex flex-col gap-2">
          <span className="text-body font-bold">{t("lang.label")}</span>
          <div>
            <LanguageToggle />
          </div>
        </div>
        <DisplayControls />
      </Block>
    </div>
  );
}
