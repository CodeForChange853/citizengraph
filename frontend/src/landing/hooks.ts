import { createContext, useContext, useSyncExternalStore } from "react";
import type { BeatId, Timeline } from "./timeline";

export const TimelineContext = createContext<Timeline | null>(null);

export function useTimeline(): Timeline {
  const timeline = useContext(TimelineContext);
  if (!timeline) throw new Error("useTimeline needs a TimelineContext");
  return timeline;
}

/**
 * Read one value from the timeline. The component re-renders only when the selected value changes,
 * so select whole numbers or coarse steps, never the raw time.
 */
export function useTimelineValue<T extends number | boolean | string>(select: (t: Timeline) => T): T {
  const timeline = useTimeline();
  return useSyncExternalStore(timeline.subscribe, () => select(timeline));
}

/** A beat's progress in `steps` equal steps (0 to 1). */
export function useBeatProgress(id: BeatId, steps = 40): number {
  return useTimelineValue((t) => Math.round(t.progress(id) * steps) / steps);
}

const QUERY = "(prefers-reduced-motion: reduce)";

function subscribeReduced(fn: () => void): () => void {
  if (typeof window === "undefined" || !window.matchMedia) return () => {};
  const mq = window.matchMedia(QUERY);
  mq.addEventListener("change", fn);
  return () => mq.removeEventListener("change", fn);
}

/** True when the device asks for reduced motion: static end states, no autoplay, no sound. */
export function usePrefersReducedMotion(): boolean {
  return useSyncExternalStore(
    subscribeReduced,
    () => typeof window !== "undefined" && !!window.matchMedia && window.matchMedia(QUERY).matches,
  );
}

export { ramp } from "./ease";
