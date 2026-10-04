import { createContext, useContext, useSyncExternalStore } from "react";
import { HOOK, WORDS } from "./beats";
import { seg } from "./ease";
import type { Playhead } from "./playhead";

export const PlayheadContext = createContext<Playhead | null>(null);
/** True when the page is shown as still, stacked sections (reduced motion): everything is in its end state. */
export const StillContext = createContext(false);

export function usePlayhead(): Playhead {
  const playhead = useContext(PlayheadContext);
  if (!playhead) throw new Error("usePlayhead needs a PlayheadContext");
  return playhead;
}

export const useStill = (): boolean => useContext(StillContext);

/**
 * Read one value from the playhead. The component re-renders only when the selected value changes,
 * so select whole numbers or coarse steps, never the raw position.
 */
export function usePlayheadValue<T extends number | boolean | string>(select: (p: Playhead) => T): T {
  const playhead = usePlayhead();
  return useSyncExternalStore(playhead.subscribe, () => select(playhead));
}

/** Share of a headline that has landed (0 to 1, in coarse steps) for words landing over [from, to] on the playhead. */
export function useShown(from: number, to: number): number {
  const still = useStill();
  const shown = usePlayheadValue((p) => Math.round(seg(p.pos, from, to) * 24) / 24);
  return still ? 1 : shown;
}

/** The same for the title, whose words land during the opening hook. */
export function useHookShown(): number {
  const still = useStill();
  const shown = usePlayheadValue((p) => Math.round(seg(p.hook, HOOK.words[0], HOOK.words[1]) * 24) / 24);
  return still ? 1 : shown;
}

/** Where a scene's headline words land on the playhead. */
export const wordsWindow = (start: number, length = 1): [number, number] => [start + WORDS[0] * length, start + WORDS[1] * length];

const QUERY = "(prefers-reduced-motion: reduce)";

function subscribeReduced(fn: () => void): () => void {
  if (typeof window === "undefined" || !window.matchMedia) return () => {};
  const mq = window.matchMedia(QUERY);
  mq.addEventListener("change", fn);
  return () => mq.removeEventListener("change", fn);
}

/** True when the device asks for reduced motion: still sections, no autoplay, no sound. */
export function usePrefersReducedMotion(): boolean {
  return useSyncExternalStore(
    subscribeReduced,
    () => typeof window !== "undefined" && !!window.matchMedia && window.matchMedia(QUERY).matches,
  );
}
