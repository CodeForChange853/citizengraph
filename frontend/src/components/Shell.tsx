import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, Outlet } from "react-router";
import { BottomNav } from "./BottomNav";
import { DisplayControls } from "./DisplayControls";
import { LanguageToggle } from "./LanguageToggle";
import { Monogram } from "./Monogram";
import { OfflineBanner } from "./OfflineBanner";

/** Header (EN/FIL always reachable), offline banner, prototype label, page, bottom nav. */
export function Shell() {
  const { t } = useTranslation();
  const [displayOpen, setDisplayOpen] = useState(false);
  return (
    <div className="min-h-dvh pb-28">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded-md focus:bg-accent-bg focus:px-4 focus:py-2 focus:font-bold focus:text-on-accent"
      >
        {t("app.skip")}
      </a>
      <header className="sticky top-0 z-20 border-b-2 border-border bg-surface">
        <div className="mx-auto flex max-w-2xl items-center gap-2 px-4 py-2">
          <Link
            to="/"
            aria-label={t("shell.home")}
            className="flex min-h-11 min-w-0 flex-1 items-center gap-2"
          >
            <Monogram />
            <span className="truncate text-lead font-bold">{t("app.name")}</span>
          </Link>
          <LanguageToggle />
          <button
            type="button"
            aria-expanded={displayOpen}
            aria-controls="display-panel"
            aria-label={t("shell.display")}
            onClick={() => setDisplayOpen((o) => !o)}
            className={`min-h-11 min-w-11 cursor-pointer rounded-md border-2 border-border-strong text-lead font-bold ${
              displayOpen ? "bg-primary-bg text-on-primary" : "bg-surface text-fg hover:bg-surface-2"
            }`}
          >
            Aa
          </button>
        </div>
        {displayOpen ? (
          <div id="display-panel" className="border-t-2 border-border bg-surface-2">
            <div className="mx-auto max-w-2xl px-4 py-4">
              <DisplayControls />
            </div>
          </div>
        ) : null}
        <p className="bg-surface-2 px-4 py-1 text-center text-body text-fg-muted">
          {t("app.prototype")}
        </p>
      </header>
      <OfflineBanner />
      <main id="main" tabIndex={-1} className="mx-auto max-w-2xl px-4 pt-6 outline-none">
        <Outlet />
      </main>
      <BottomNav />
    </div>
  );
}
