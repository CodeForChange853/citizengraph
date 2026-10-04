// The story as a table: nine scenes, how much scrolling each takes and how long it runs in the film.
// The playhead `u` is a scene number plus the progress inside it: 3.5 is half way through scene 3.
// docs/landing_motion_spec.md, section 5, is the source for these numbers.
import { clamp01, ramp } from "./ease";

export type SceneId = "title" | "question" | "guide" | "journey" | "answer" | "watch" | "request" | "together" | "close";
/** Which core a scene belongs to: it picks the hot colour of the headline. */
export type SceneCore = "both" | "guide" | "watch";

export interface Scene {
  id: SceneId;
  /** Scroll length in hundredths of the viewport height. */
  vh: number;
  /** Seconds in the film. */
  film: number;
  core: SceneCore;
  /** Where in the scene its chapter link lands (0 to 1): a point where the headline has landed. */
  hold: number;
}

export const SCENES: readonly Scene[] = [
  { id: "title", vh: 100, film: 3, core: "both", hold: 0 },
  { id: "question", vh: 120, film: 6, core: "both", hold: 0.4 },
  { id: "guide", vh: 120, film: 6, core: "guide", hold: 0.5 },
  { id: "journey", vh: 400, film: 15, core: "guide", hold: 0.1 },
  { id: "answer", vh: 150, film: 7, core: "guide", hold: 0.4 },
  { id: "watch", vh: 120, film: 5, core: "watch", hold: 0.5 },
  { id: "request", vh: 250, film: 9, core: "watch", hold: 0.22 },
  { id: "together", vh: 120, film: 5, core: "both", hold: 0.55 },
  { id: "close", vh: 100, film: 3, core: "both", hold: 1 },
];

export const SCENE_COUNT = SCENES.length;
/** The end of the story on the playhead. */
export const END = SCENE_COUNT;
export const TOTAL_VH = SCENES.reduce((sum, s) => sum + s.vh, 0);
/** The opening hook plays by itself for this long, then scrolling drives. */
export const HOOK_MS = 3000;
/** The film: the hook, then every scene at its film length. */
export const FILM_SECONDS = HOOK_MS / 1000 + SCENES.reduce((sum, s) => sum + s.film, 0);

export function sceneIndex(id: SceneId): number {
  return SCENES.findIndex((s) => s.id === id);
}

/** Share of the whole scroll distance (0 to 1) for a playhead position. */
export function posToFraction(u: number): number {
  const pos = Math.min(END, Math.max(0, u));
  let vh = 0;
  for (let i = 0; i < SCENE_COUNT; i++) vh += SCENES[i]!.vh * clamp01(pos - i);
  return vh / TOTAL_VH;
}

/** Playhead position for a share of the whole scroll distance (0 to 1). */
export function fractionToPos(fraction: number): number {
  let vh = clamp01(fraction) * TOTAL_VH;
  for (let i = 0; i < SCENE_COUNT; i++) {
    const len = SCENES[i]!.vh;
    if (vh <= len) return i + vh / len;
    vh -= len;
  }
  return END;
}

/** The scene a playhead position is in, and the progress inside it. */
export function sceneAt(u: number): { index: number; p: number } {
  const pos = Math.min(END, Math.max(0, u));
  const index = Math.min(SCENE_COUNT - 1, Math.floor(pos));
  return { index, p: pos - index };
}

/** Where a scene's chapter link lands on the playhead. */
export function anchorPos(index: number): number {
  return index + SCENES[index]!.hold;
}

/**
 * How visible a scene's text is (0 to 1). The words of one scene are gone before the next ones arrive,
 * so two headlines never overlap; the picture carries the matching cut in between.
 */
export function visibility(index: number, u: number): number {
  const fadeIn = index === 0 ? 1 : ramp(u, index - 0.01, index + 0.05);
  const fadeOut = index === SCENE_COUNT - 1 ? 1 : 1 - ramp(u, index + 0.93, index + 0.995);
  return fadeIn * fadeOut;
}

/** Playhead position of the film after `seconds` (the hook holds the playhead at 0 first). */
export function filmPos(seconds: number): number {
  let left = seconds - HOOK_MS / 1000;
  if (left <= 0) return 0;
  for (let i = 0; i < SCENE_COUNT; i++) {
    const len = SCENES[i]!.film;
    if (left <= len) return i + left / len;
    left -= len;
  }
  return END;
}

/** Seconds of film at which a playhead position is reached (the inverse of filmPos, after the hook). */
export function filmTime(u: number): number {
  const pos = Math.min(END, Math.max(0, u));
  let seconds = HOOK_MS / 1000;
  for (let i = 0; i < SCENE_COUNT; i++) seconds += SCENES[i]!.film * clamp01(pos - i);
  return seconds;
}
