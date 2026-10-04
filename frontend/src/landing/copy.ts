// The landing page's words. They ship with the landing chunk, not with the app shell.
//
// Language lock: /welcome is written in English only. It renders in English whatever language the app
// is set to, through its own i18next instance, so the app's stored language (localStorage "cg.lang")
// and the app's own instance are never touched. `i18n/fil.json` is an empty stub on purpose: no
// Filipino copy exists for this page yet. To add it later, fill the stub, have it reviewed by a native
// speaker, add it back to scripts/gen-native-review.mjs and set LANDING_FIL_ENABLED to true.
import i18n from "../i18n";
import en from "./i18n/en.json";
import fil from "./i18n/fil.json";

/** The one switch for the header's EN/FIL toggle. False: the toggle is shown greyed out and does nothing. */
export const LANDING_FIL_ENABLED = false;

i18n.addResourceBundle("en", "translation", { landing: en }, true, true);
if (LANDING_FIL_ENABLED) i18n.addResourceBundle("fil", "translation", { landing: fil }, true, true);

/** A copy of the app's instance fixed to English. Changing it never changes the app's language. */
export const landingI18n = LANDING_FIL_ENABLED ? i18n : i18n.cloneInstance({ lng: "en", fallbackLng: "en" });
