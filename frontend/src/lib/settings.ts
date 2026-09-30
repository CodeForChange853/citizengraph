import { useSyncExternalStore } from "react";
import { readJson, writeJson } from "./storage";

export type Theme = "system" | "light" | "dark";
export type TextSize = "normal" | "large" | "xlarge";
export interface Settings {
  theme: Theme;
  textSize: TextSize;
}

export const SETTINGS_KEY = "cg.settings.v1";
const DEFAULTS: Settings = { theme: "system", textSize: "normal" };

function load(): Settings {
  const saved = readJson<Partial<Settings>>(SETTINGS_KEY, {});
  const theme = ["system", "light", "dark"].includes(saved.theme ?? "") ? saved.theme! : "system";
  const size = ["normal", "large", "xlarge"].includes(saved.textSize ?? "")
    ? saved.textSize!
    : "normal";
  return { theme, textSize: size };
}

let state: Settings = load();
const listeners = new Set<() => void>();

/** Reflect the settings on <html>; tokens.css and index.css react to these attributes. */
export function applySettings(s: Settings = state): void {
  const root = document.documentElement;
  if (s.theme === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", s.theme);
  if (s.textSize === "normal") root.removeAttribute("data-text-size");
  else root.setAttribute("data-text-size", s.textSize);
}

export function updateSettings(patch: Partial<Settings>): void {
  state = { ...state, ...patch };
  writeJson(SETTINGS_KEY, state);
  applySettings(state);
  listeners.forEach((l) => l());
}

/** Re-read storage (tests). */
export function reloadSettings(): void {
  state = load();
  applySettings(state);
  listeners.forEach((l) => l());
}

export function useSettings(): Settings {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => state,
  );
}

export { DEFAULTS as DEFAULT_SETTINGS };
