import { useEffect } from "react";
import { TIMELINE_END, type Timeline } from "./timeline";

/**
 * Connects the timeline to the page. With reduced motion nothing plays: every beat is shown in its
 * end state.
 */
export function usePlayback(timeline: Timeline, reduced: boolean): void {
  useEffect(() => {
    timeline.pause();
    timeline.seek(TIMELINE_END);
  }, [timeline, reduced]);
}
