import type { TFunction } from "i18next";
import type { Lang } from "../api/types";

// One number or a range ("5", "5-10"), then a unit word. Nothing else counts as a time we understand.
const NUMBER = String.raw`\d+(?:\.\d+)?`;
const TERM = new RegExp(String.raw`^${NUMBER}(?:\s*[-–]\s*${NUMBER})?\s*(minutes?|hours?|days?|weeks?)$`, "i");
const UNIT_WORD = new RegExp(String.raw`(?<=\d\s*)(minutes?|hours?|days?|weeks?)\b`, "gi");

const UNIT_KEY: Record<string, string> = { minute: "minute", hour: "hour", day: "day", week: "week" };

function unitKey(word: string): string {
  return UNIT_KEY[word.toLowerCase().replace(/s$/, "")] ?? "";
}

/**
 * Filipino display of a charter time such as "5-10 minutes" or "3 days, 10 minutes".
 * Only the unit word changes; the numbers stay exactly as given. A time is localized only when every
 * comma-separated part is a number or range followed by minutes, hours, days or weeks. Anything else
 * ("1 hour (Once a month)", "working days", text we do not know) comes back unchanged, never half translated.
 * English is always returned as given. The Filipino unit words live in fil.json (`time.*`).
 */
export function localizeTime(text: string, lang: Lang, t: TFunction): string {
  if (lang !== "fil") return text;
  const parts = text.split(",").map((p) => p.trim());
  if (parts.some((p) => !TERM.test(p))) return text;
  return text.replace(UNIT_WORD, (word) => t(`time.${unitKey(word)}`));
}
