import { Component, type ReactNode } from "react";
import { Link } from "react-router";
import i18n from "../i18n";

/**
 * Stands round the lazy /welcome route. If the landing chunk or its stylesheet cannot be fetched (offline
 * on a first visit, a flaky connection), the visitor gets a plain page with the prototype label and a way
 * into the app, never a blank screen. This file is the only landing code in the app shell, so it uses
 * strings the app already has, in English like the rest of the landing page.
 */
export class LoadGuard extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (!this.state.failed) return this.props.children;
    const t = i18n.getFixedT("en");
    return (
      <main lang="en" data-landing-fallback="" style={{ maxWidth: "32rem", margin: "0 auto", padding: "3rem 1.25rem" }}>
        <h1>{t("app.name")}</h1>
        <p>{t("app.prototype")}</p>
        <p role="alert">{t("chat.error")}</p>
        <p style={{ display: "flex", flexWrap: "wrap", gap: "1.25rem", marginTop: "1.5rem" }}>
          <Link id="lp-cta" to="/">
            {t("saved.ask")}
          </Link>
          <button type="button" onClick={() => window.location.reload()}>
            {t("chat.retry")}
          </button>
        </p>
      </main>
    );
  }
}
