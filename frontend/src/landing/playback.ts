import { useEffect } from "react";
import { TIMELINE_END, type Timeline } from "./timeline";

/** Longest step one frame may take, so a stalled tab does not jump the intro forward on return. */
const MAX_STEP_MS = 100;

/**
 * Connects the timeline to the page clock. The intro (beats 1 to 4) plays by itself, driven by
 * animation frames, and waits while the tab is hidden. With reduced motion nothing plays: every
 * beat is shown in its end state.
 */
export function usePlayback(timeline: Timeline, reduced: boolean): void {
  useEffect(() => {
    if (reduced) {
      timeline.pause();
      timeline.seek(TIMELINE_END);
      return;
    }
    let frame = 0;
    let last = 0;

    function loop(now: number) {
      frame = 0;
      if (last) timeline.advance(Math.min(now - last, MAX_STEP_MS));
      last = now;
      if (timeline.playing && !document.hidden) frame = requestAnimationFrame(loop);
      else last = 0;
    }
    function kick() {
      if (timeline.playing && !frame && !document.hidden) frame = requestAnimationFrame(loop);
      // Until the scroll story exists, the later beats show their end state once the intro is over.
      if (timeline.introDone && timeline.time < TIMELINE_END) timeline.seek(TIMELINE_END);
    }

    const unsubscribe = timeline.subscribe(kick);
    document.addEventListener("visibilitychange", kick);
    timeline.replay();
    return () => {
      unsubscribe();
      document.removeEventListener("visibilitychange", kick);
      if (frame) cancelAnimationFrame(frame);
      timeline.pause();
    };
  }, [timeline, reduced]);
}
