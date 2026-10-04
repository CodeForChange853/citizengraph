// One timeline for the whole landing page. Visuals and sound both read it:
//   - beats 1 to 4 (the intro) play by themselves and stop at the end of beat 4;
//   - beats 5 to 8 are seeked by the scroll position.
// The controller knows nothing about the DOM, the clock or audio, so it can be tested directly.

export type BeatId = "ask" | "contours" | "offices" | "query" | "trail" | "answer" | "sla" | "local";
export type CueKind = "key" | "enter" | "tick";

export interface Beat {
  id: BeatId;
  start: number;
  dur: number;
}
export interface Cue {
  at: number;
  kind: CueKind;
}

/** Milliseconds for the intro beats; the scroll beats use the same unit so one number line covers all. */
const DURATIONS: [BeatId, number][] = [
  ["ask", 3200],
  ["contours", 1600],
  ["offices", 2400],
  ["query", 3600],
  ["trail", 1000],
  ["answer", 1000],
  ["sla", 1000],
  ["local", 1000],
];

export const BEATS: Beat[] = DURATIONS.reduce<Beat[]>((list, [id, dur]) => {
  const prev = list[list.length - 1];
  list.push({ id, dur, start: prev ? prev.start + prev.dur : 0 });
  return list;
}, []);

export function beat(id: BeatId): Beat {
  const found = BEATS.find((b) => b.id === id);
  if (!found) throw new Error(`Unknown beat ${id}`);
  return found;
}

export const INTRO_END = beat("trail").start;
export const TIMELINE_END = beat("local").start + beat("local").dur;

const clamp01 = (v: number) => Math.min(1, Math.max(0, v));

export class Timeline {
  private t = 0;
  private running = false;
  private readonly listeners = new Set<() => void>();
  private readonly cueListeners = new Set<(kind: CueKind) => void>();
  private readonly cues: Cue[];

  constructor(cues: Cue[] = []) {
    this.cues = [...cues].sort((a, b) => a.at - b.at);
  }

  get time(): number {
    return this.t;
  }
  get playing(): boolean {
    return this.running;
  }
  get introDone(): boolean {
    return this.t >= INTRO_END;
  }

  /** 0 before the beat, 1 after it. */
  progress(id: BeatId): number {
    const b = beat(id);
    return clamp01((this.t - b.start) / b.dur);
  }

  /** Milliseconds into a beat (negative before it starts). */
  into(id: BeatId): number {
    return this.t - beat(id).start;
  }

  subscribe = (fn: () => void): (() => void) => {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  };

  onCue(fn: (kind: CueKind) => void): () => void {
    this.cueListeners.add(fn);
    return () => this.cueListeners.delete(fn);
  }

  /** Start (or resume) the intro. Does nothing once the intro is over. */
  play(): void {
    if (this.running || this.introDone) return;
    this.running = true;
    this.emit();
  }

  pause(): void {
    if (!this.running) return;
    this.running = false;
    this.emit();
  }

  /** Called by the frame loop with the elapsed milliseconds. Cues fire only here, never on a seek. */
  advance(dtMs: number): void {
    if (!this.running || dtMs <= 0) return;
    const from = this.t;
    this.t = Math.min(INTRO_END, from + dtMs);
    for (const cue of this.cues) {
      if (cue.at > from && cue.at <= this.t) this.cueListeners.forEach((fn) => fn(cue.kind));
    }
    if (this.t >= INTRO_END) this.running = false;
    this.emit();
  }

  /** Jump to a time without playing through it (scroll, skip, replay, reduced motion). */
  seek(time: number): void {
    const next = Math.min(TIMELINE_END, Math.max(0, time));
    if (next === this.t) return;
    this.t = next;
    this.emit();
  }

  /** End the intro now: its end state is shown and nothing more plays by itself. */
  skipIntro(): void {
    this.running = false;
    if (this.t < INTRO_END) this.t = INTRO_END;
    this.emit();
  }

  replay(): void {
    this.t = 0;
    this.running = true;
    this.emit();
  }

  private emit(): void {
    this.listeners.forEach((fn) => fn());
  }
}
