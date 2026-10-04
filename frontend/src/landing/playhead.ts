// The one playhead. The scroll position sets a target; the shown position eases toward it, which gives
// the weight of smooth scrolling without taking over the wheel. A big jump (a chapter link, Home/End)
// is a cut, not a whip through the scenes in between. The opening hook is the only thing that runs on
// the clock. The picture, the page and the sound all read this object; it knows nothing about the DOM.
import { clamp01 } from "./ease";
import { END, HOOK_MS } from "./scenes";

/** Time constant of the follow: the shown position settles on the target in about 120 ms. */
const FOLLOW_MS = 110;
/** A move of more than this many scenes at once is shown as a cut. */
export const CUT_DISTANCE = 0.75;

export type CueKind = "ignite" | "whoosh" | "tick" | "pulse";
export interface Cue {
  /** Playhead position, or a share of the hook when `hook` is true. */
  at: number;
  kind: CueKind;
  hook?: boolean;
}

export class Playhead {
  private targetPos = 0;
  private shown = 0;
  private hookShare = 0;
  private cutCount = 0;
  private readonly listeners = new Set<() => void>();
  private readonly cueListeners = new Set<(kind: CueKind) => void>();
  private readonly cues: Cue[];

  constructor(cues: Cue[] = []) {
    this.cues = cues;
  }

  /** The eased position the page shows: scene number plus progress. */
  get pos(): number {
    return this.shown;
  }
  get target(): number {
    return this.targetPos;
  }
  /** The opening hook, 0 to 1. */
  get hook(): number {
    return this.hookShare;
  }
  /** Counts the cuts, so the page can restart its dip to dark each time. */
  get cuts(): number {
    return this.cutCount;
  }
  /** True while something still has to move: the page keeps its frame loop running. */
  get moving(): boolean {
    return this.hookShare < 1 || Math.abs(this.targetPos - this.shown) > 1e-4;
  }

  subscribe = (fn: () => void): (() => void) => {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  };

  onCue(fn: (kind: CueKind) => void): () => void {
    this.cueListeners.add(fn);
    return () => this.cueListeners.delete(fn);
  }

  private emit(): void {
    for (const fn of this.listeners) fn();
  }

  /** Where the scroll position puts the story. */
  setTarget(u: number): void {
    const next = Math.min(END, Math.max(0, u));
    if (next === this.targetPos) return;
    this.targetPos = next;
    if (Math.abs(next - this.shown) > CUT_DISTANCE) {
      this.shown = next; // a cut: no cues, no travel through the scenes in between
      this.cutCount++;
      if (next > 0.5) this.hookShare = 1;
    }
    this.emit();
  }

  /** Show everything finished at once (reduced motion, tests). */
  finish(u = this.targetPos): void {
    this.targetPos = this.shown = Math.min(END, Math.max(0, u));
    this.hookShare = 1;
    this.emit();
  }

  /** Play the hook again from the start (the film does this). */
  restartHook(): void {
    this.hookShare = 0;
    this.emit();
  }

  /** Advance by `ms` of real time. */
  tick(ms: number): void {
    if (!this.moving || ms <= 0) return;
    const hookBefore = this.hookShare;
    const posBefore = this.shown;
    this.hookShare = clamp01(this.hookShare + ms / HOOK_MS);
    const gap = this.targetPos - this.shown;
    this.shown = Math.abs(gap) < 2e-4 ? this.targetPos : this.shown + gap * (1 - Math.exp(-ms / FOLLOW_MS));
    for (const cue of this.cues) {
      const [before, after] = cue.hook ? [hookBefore, this.hookShare] : [posBefore, this.shown];
      if (before < cue.at && cue.at <= after) for (const fn of this.cueListeners) fn(cue.kind);
    }
    this.emit();
  }
}
