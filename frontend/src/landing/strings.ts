// The landing page's strings ship with the landing chunk, not with the app shell.
// Filipino strings here are unverified until a native speaker reviews them: they are listed in
// frontend/NEEDS-NATIVE-REVIEW.md under `landing.*`.
import i18n from "../i18n";
import en from "./i18n/en.json";
import fil from "./i18n/fil.json";

i18n.addResourceBundle("en", "translation", { landing: en }, true, true);
i18n.addResourceBundle("fil", "translation", { landing: fil }, true, true);
