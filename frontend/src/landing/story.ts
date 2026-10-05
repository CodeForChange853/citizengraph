// Connects the playhead to the page: the scroll position sets the playhead, a frame loop eases it and
// paints the CSS variables the scenes read, and "Watch the film" scrolls the page by itself.
// Nothing here takes over the wheel: the page really scrolls, so the keyboard and the scrollbar work.
import { useCallback, useEffect, useRef, useState, type RefObject } from "react";
import { clamp01 } from "./ease";
import { subjectPoint } from "./layout";
import type { Playhead } from "./playhead";
import { anchorPos, END, FILM_SECONDS, filmPos, fractionToPos, posToFraction, SCENE_COUNT, visibility } from "./scenes";

/** Longest step one frame may take, so a stalled tab does not jump the story on return. */
const MAX_STEP_MS = 100;

/** Scroll geometry of the track: where it starts on the page and how far the pinned stage travels. */
function measure(track: HTMLElement, stage: HTMLElement): { top: number; range: number } {
  const box = track.getBoundingClientRect();
  return { top: box.top + window.scrollY, range: Math.max(1, box.height - stage.getBoundingClientRect().height) };
}

/** Write the playhead into the page: one pass over the scenes, touching only what changed. */
export function paint(root: HTMLElement, playhead: Playhead, aspect: number): void {
  const u = playhead.pos;
  const set = (el: HTMLElement, name: string, value: string) => {
    if (el.style.getPropertyValue(name) !== value) el.style.setProperty(name, value);
  };
  // The progress bar gets its own transform: a variable on the root would restyle the whole page every frame.
  const bar = root.querySelector<HTMLElement>(".lp-progress");
  const scaleX = `scaleX(${posToFraction(u).toFixed(4)})`;
  if (bar && bar.style.transform !== scaleX) bar.style.transform = scaleX;
  const subject = subjectPoint(u, aspect);
  set(root, "--sx", subject.x.toFixed(4));
  set(root, "--sy", subject.y.toFixed(4));
  root.querySelectorAll<HTMLElement>("[data-index]").forEach((section) => {
    const index = Number(section.dataset.index);
    const vis = visibility(index, u);
    const active = vis > 0.02;
    if (section.dataset.active !== String(active)) section.dataset.active = String(active);
    set(section, "--vis", vis.toFixed(3));
    if (active) set(section, "--u", u.toFixed(4));
  });
  const scene = Math.min(SCENE_COUNT - 1, Math.floor(u + 0.02));
  if (root.dataset.scene !== String(scene)) root.dataset.scene = String(scene);
}

export interface Story {
  filming: boolean;
  startFilm(): void;
  stopFilm(): void;
  /** Scroll to a place on the playhead (the skip link, a focused control inside a scene). */
  goTo(u: number): void;
}

export function useStory(playhead: Playhead, still: boolean, rootRef: RefObject<HTMLElement | null>, trackRef: RefObject<HTMLElement | null>, stageRef: RefObject<HTMLElement | null>): Story {
  const [filming, setFilming] = useState(false);
  const film = useRef({ on: false, seconds: 0 });
  const api = useRef<{ wake(): void; scrollToPos(u: number): void }>({ wake() {}, scrollToPos() {} });

  useEffect(() => {
    const root = rootRef.current;
    const track = trackRef.current;
    const stage = stageRef.current;
    if (!root || !track || !stage) return;
    if (still) {
      playhead.finish(END);
      return;
    }
    let raf = 0;
    let last = 0;
    const aspect = () => stage.clientWidth / Math.max(1, stage.clientHeight);

    // the track's place on the page changes only when the window does: measure once, not every scroll event
    let box = measure(track, stage);
    function remeasure() {
      box = measure(track!, stage!);
      onScroll();
    }
    function read() {
      const { top, range } = box;
      playhead.setTarget(fractionToPos(clamp01((window.scrollY - top) / range)));
    }
    function scrollToPos(u: number) {
      const { top, range } = box;
      window.scrollTo(0, top + posToFraction(u) * range);
    }
    function stopFilm() {
      if (!film.current.on) return;
      film.current.on = false;
      setFilming(false);
    }
    function loop(now: number) {
      raf = -1; // running: a wake() from inside this frame must not schedule a second loop
      const step = last ? Math.min(now - last, MAX_STEP_MS) : 0;
      last = now;
      if (film.current.on) {
        film.current.seconds += step / 1000;
        scrollToPos(filmPos(film.current.seconds));
        read();
        if (film.current.seconds >= FILM_SECONDS) stopFilm();
      }
      playhead.tick(step);
      paint(root!, playhead, aspect());
      if ((playhead.moving || film.current.on) && !document.hidden) raf = requestAnimationFrame(loop);
      else raf = last = 0;
    }
    function wake() {
      if (!raf && !document.hidden) raf = requestAnimationFrame(loop);
    }
    function onScroll() {
      read();
      wake();
    }
    // any real input ends the film where it is
    function interrupt(event: Event) {
      if (!film.current.on) return;
      // the film button handles its own click (and Enter or Space on it)
      const onButton = !!(event.target as HTMLElement | null)?.closest?.("[data-film]");
      const key = (event as KeyboardEvent).key;
      if (onButton && (event.type === "pointerdown" || key === "Enter" || key === " ")) return;
      stopFilm();
    }
    // a control inside a scene that is not on stage (the call to action, a chapter away): go to its scene
    function onFocus(event: FocusEvent) {
      const section = (event.target as HTMLElement).closest<HTMLElement>("[data-index]");
      if (!section) return;
      const index = Number(section.dataset.index);
      if (visibility(index, playhead.target) < 0.5) scrollToPos(anchorPos(index));
    }

    api.current = { wake, scrollToPos };
    const unsubscribe = playhead.subscribe(wake);
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", remeasure);
    const resizer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(remeasure);
    resizer?.observe(stage);
    document.addEventListener("visibilitychange", wake);
    for (const type of ["wheel", "touchstart", "keydown", "pointerdown"]) window.addEventListener(type, interrupt, { passive: true });
    root.addEventListener("focusin", onFocus);
    read();
    if (playhead.target > 0.5) playhead.finish(playhead.target); // a reload far down the page: no hook
    paint(root, playhead, aspect());
    wake();
    return () => {
      unsubscribe();
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", remeasure);
      resizer?.disconnect();
      document.removeEventListener("visibilitychange", wake);
      for (const type of ["wheel", "touchstart", "keydown", "pointerdown"]) window.removeEventListener(type, interrupt);
      root.removeEventListener("focusin", onFocus);
      if (raf > 0) cancelAnimationFrame(raf);
      film.current.on = false;
    };
  }, [playhead, still, rootRef, trackRef, stageRef]);

  const startFilm = useCallback(() => {
    if (still) return;
    api.current.scrollToPos(0);
    playhead.finish(0);
    playhead.restartHook();
    film.current = { on: true, seconds: 0 };
    setFilming(true);
    api.current.wake();
  }, [playhead, still]);

  const stopFilm = useCallback(() => {
    film.current.on = false;
    setFilming(false);
  }, []);

  const goTo = useCallback((u: number) => api.current.scrollToPos(u), []);

  return { filming, startFilm, stopFilm, goTo };
}
