import { useEffect, type RefObject } from "react";
import { beat, INTRO_END, TIMELINE_END, type BeatId, type Timeline } from "./timeline";

/** Longest step one frame may take, so a stalled tab does not jump the intro forward on return. */
const MAX_STEP_MS = 100;
/** Scrolling this far into the story while the intro still plays ends the intro. */
const SKIP_MARGIN = 0.25;

const SCROLL_BEATS: BeatId[] = ["answer", "sla", "local"];
const clamp01 = (v: number) => Math.min(1, Math.max(0, v));

export interface StoryLayout {
  /** Viewport height. */
  vh: number;
  /** The stage wrapper (beat 5): its top relative to the viewport, its height, and the stage's own height. */
  wrapTop: number;
  wrapHeight: number;
  stageHeight: number;
  /** The sections of beats 6, 7 and 8: top relative to the viewport, and height. */
  sections: { top: number; height: number }[];
  /** The page is scrolled to its end (short last sections still finish their beat). */
  atBottom?: boolean;
}

/**
 * Where the scroll position puts the timeline (beats 5 to 8). Pure, so it can be tested without a
 * browser. Beat 5 runs while the pinned stage is scrolled through; each later beat runs as its
 * section rises into view.
 */
export function storyTime(layout: StoryLayout): number {
  const { vh, wrapTop, wrapHeight, stageHeight, sections } = layout;
  if (layout.atBottom && sections.some((section) => section.height > 0)) return TIMELINE_END;
  const travel = wrapHeight - stageHeight; // extra scroll distance while the stage is pinned
  const trail = travel > 8 ? clamp01(-wrapTop / travel) : clamp01(-wrapTop / (vh * 0.22));
  let time = beat("trail").start + trail * beat("trail").dur;
  sections.forEach((section, i) => {
    if (section.height <= 0) return;
    const p = clamp01((vh * 0.92 - section.top) / (Math.min(section.height, vh) * 0.75));
    const b = beat(SCROLL_BEATS[i]!);
    if (p > 0) time = b.start + p * b.dur;
  });
  return time;
}

function readLayout(root: HTMLElement): StoryLayout | null {
  const wrap = root.querySelector<HTMLElement>('[data-beat="trail"]');
  const stage = wrap?.firstElementChild;
  if (!wrap || !stage) return null;
  const box = wrap.getBoundingClientRect();
  return {
    vh: window.innerHeight,
    atBottom: window.scrollY > 0 && window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 2,
    wrapTop: box.top,
    wrapHeight: box.height,
    stageHeight: stage.getBoundingClientRect().height,
    sections: SCROLL_BEATS.map((id) => {
      const r = root.querySelector(`[data-beat="${id}"]`)?.getBoundingClientRect();
      return { top: r?.top ?? 0, height: r?.height ?? 0 };
    }),
  };
}

/**
 * Connects the one timeline to the page: the intro (beats 1 to 4) plays on animation frames and waits
 * while the tab is hidden; after it, the scroll position seeks beats 5 to 8. With reduced motion
 * nothing plays and nothing follows the scroll: every beat is shown in its end state.
 */
export function usePlayback(timeline: Timeline, reduced: boolean, rootRef: RefObject<HTMLElement | null>): void {
  useEffect(() => {
    const root = rootRef.current;
    if (reduced || !root) {
      timeline.pause();
      timeline.seek(TIMELINE_END);
      return;
    }
    let frame = 0;
    let last = 0;
    let scrollFrame = 0;

    function loop(now: number) {
      frame = 0;
      if (last) timeline.advance(Math.min(now - last, MAX_STEP_MS));
      last = now;
      if (timeline.playing && !document.hidden) frame = requestAnimationFrame(loop);
      else last = 0;
    }

    function follow() {
      scrollFrame = 0;
      const layout = readLayout(root!);
      if (!layout) return;
      // The stage is pinned only when it fits the screen; a taller stage just scrolls.
      const wrap = root!.querySelector<HTMLElement>('[data-beat="trail"]')!;
      const pinned = String(layout.stageHeight <= layout.vh + 1);
      if (wrap.dataset.pinned !== pinned) wrap.dataset.pinned = pinned;
      const time = storyTime(layout);
      if (!timeline.introDone && time > INTRO_END + SKIP_MARGIN * beat("trail").dur) timeline.skipIntro();
      if (timeline.introDone && !timeline.playing) timeline.seek(time);
    }
    function onScroll() {
      if (!scrollFrame) scrollFrame = requestAnimationFrame(follow);
    }
    function kick() {
      if (timeline.playing && !frame && !document.hidden) frame = requestAnimationFrame(loop);
      if (timeline.introDone && timeline.time === INTRO_END) onScroll(); // the intro just ended: pick up the scroll
    }

    const unsubscribe = timeline.subscribe(kick);
    document.addEventListener("visibilitychange", kick);
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    timeline.replay();
    onScroll(); // a reload can restore a scroll position far down the page
    return () => {
      unsubscribe();
      document.removeEventListener("visibilitychange", kick);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      if (frame) cancelAnimationFrame(frame);
      if (scrollFrame) cancelAnimationFrame(scrollFrame);
      timeline.pause();
    };
  }, [timeline, reduced, rootRef]);
}
