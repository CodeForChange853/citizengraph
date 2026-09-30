import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import type { Lang } from "../api/types";
import en from "./en.json";
import fil from "./fil.json";

// Filipino strings: review status per string is in frontend/NEEDS-NATIVE-REVIEW.md.
export const LANG_KEY = "cg.lang";

export function detectLanguage(): Lang {
  try {
    const saved = localStorage.getItem(LANG_KEY);
    if (saved === "en" || saved === "fil") return saved;
  } catch {
    // storage blocked: fall through
  }
  const nav = typeof navigator === "undefined" ? "" : navigator.language.toLowerCase();
  return nav.startsWith("fil") || nav.startsWith("tl") ? "fil" : "en";
}

export function setLanguage(lang: Lang): Promise<unknown> {
  try {
    localStorage.setItem(LANG_KEY, lang);
  } catch {
    // storage blocked: the choice lasts for this visit only
  }
  document.documentElement.lang = lang;
  return i18n.changeLanguage(lang);
}

void i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, fil: { translation: fil } },
  lng: detectLanguage(),
  fallbackLng: "en",
  interpolation: { escapeValue: false },
  returnNull: false,
});
document.documentElement.lang = i18n.language;

export default i18n;
