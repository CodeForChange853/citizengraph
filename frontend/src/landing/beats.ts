// When things happen inside the scenes, on the playhead (scene number plus progress). The picture
// (gl/director.ts), the page (the scene components) and the sound cues all read these numbers, so a
// word, a ring and a tick that belong together stay together.
import type { Cue } from "./playhead";

/** The opening hook, as shares of its 3 seconds. */
export const HOOK = {
  /** The single spark splits in two. */
  split: 0.25,
  /** The cyan core ignites, then the orange one. */
  cyan: 0.45,
  orange: 0.55,
  /** The glass module appears round them. */
  glass: 0.6,
  /** The headline lands word by word. */
  words: [0.5, 0.95],
} as const;

/** Headline words of an ordinary scene land over this share of the scene; the support text follows. */
export const WORDS = [0.06, 0.3] as const;
export const SUPPORT = [0.3, 0.38] as const;

export const BEAT = {
  // scene 0 to 1: through the module into the corridor
  doors: [0.72, 1.0],
  corridor: [0.8, 1.0, 1.98, 2.18],
  // scene 2: the module opens, the cyan core steps forward
  open: [2.15, 2.5],
  langs: [2.45, 2.55, 2.65],
  // scene 3a: the question, then the safety sweep
  lamp: [3.0, 3.1],
  question: [3.03, 3.12],
  sweep: [3.12, 3.23],
  checked: [3.2, 3.24],
  // scene 3b: words to chips to one icon, then the beam fans out to the four offices
  chips: [3.27, 3.33],
  icon: [3.33, 3.36],
  iconFly: [3.4, 3.44],
  stars: [3.38, 3.47],
  fan: [3.4, 3.53],
  offices: [3.44, 3.5],
  // scene 3c: fly in, the beam narrows, one service lights
  fly: [3.5, 3.72],
  narrow: [3.55, 3.66],
  lit: [3.62, 3.72],
  // scene 3d: papers line up as a checklist
  rows: [3.77, 3.99],
  // scene 4: everything falls into the orb; the orb resolves into the card; the items tick
  collapse: [4.0, 4.3],
  orb: [4.14, 4.32],
  arc: [4.3, 4.38, 4.5, 4.56],
  card: [4.5, 4.68],
  ticks: [4.72, 4.78, 4.84, 4.9],
  // scene 5: the ring flies to the orange core and becomes the clock
  swing: [5.0, 5.4],
  clock: [5.28, 5.45],
  // scene 6: the thread through the steps
  thread: [6.08, 6.16, 6.25, 6.42, 6.55, 6.64],
  grey: [6.3, 6.4],
  late: [6.55, 6.6],
  alert: [6.66, 6.8],
  reel: [6.97, 7.1],
  // scene 7: both cores in the module, beating in step
  close: [7.15, 7.42],
  heart: [7.35, 7.5, 8.05, 8.2],
  // scene 8: the cores merge into the orb that holds the call to action
  merge: [8.08, 8.4],
  cta: [8.4, 8.62],
} as const;

/** Sound cues. They fire only when the playhead crosses them going forward; a cut fires nothing. */
export const CUES: Cue[] = [
  { at: HOOK.cyan, kind: "ignite", hook: true },
  { at: HOOK.orange, kind: "ignite", hook: true },
  { at: 0.8, kind: "whoosh" },
  { at: 1.86, kind: "whoosh" },
  { at: 2.2, kind: "ignite" },
  { at: BEAT.sweep[0], kind: "whoosh" },
  { at: BEAT.fly[0] + 0.02, kind: "whoosh" },
  { at: BEAT.lit[0], kind: "tick" },
  ...BEAT.ticks.map((at) => ({ at, kind: "tick" as const })),
  { at: 5.04, kind: "whoosh" },
  { at: 5.2, kind: "ignite" },
  { at: BEAT.late[0], kind: "pulse" },
  { at: BEAT.heart[0] + 0.05, kind: "pulse" },
  { at: BEAT.merge[1], kind: "ignite" },
];
