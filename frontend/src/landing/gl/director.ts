// The director: one pure function from the playhead to every number the picture needs.
// It imports nothing from three.js, so it runs in tests, and because it keeps no state the story can be
// scrubbed forwards and backwards. `u` is the playhead (scene number plus progress), `hook` the opening
// hook (0 to 1), `time` seconds on the clock (only for idle life: shimmer, sway, the heartbeat), `aspect`
// the stage's width over its height.
//
// The world: the title module stands at z = TITLE_Z. The queue corridor runs from there down to the
// station at the origin, where Core 1 works (scenes 2 to 4). Core 2 works at WATCH (scenes 5 to 8).
import { BEAT, HOOK } from "../beats";
import { clamp01, easeInOut, easeOutCubic, mix, ramp, seg, window4 } from "../ease";
import { isWide, subjectPoint } from "../layout";
import { tone } from "../tokens";
import { add, basisQuat, eulerQuat, fromCamera, hash, lerp3, lookBasis, mulQuat, scale, smoothPath, type Quat, type V3 } from "./vec";

export const TITLE_Z = 44;
export const WATCH: V3 = [7, 0, -2];
export const FLOOR_Y = -1.35;
export const FOV = 40;
/** Camera distance from its subject on a wide screen. */
const REST = 7;

const CYAN = tone("accent");
const ORANGE = tone("neon");
const WHITE: V3 = [1, 1, 1];
const GREY = tone("idle");

/** The four offices as clusters of points: 7 + 17 + 15 + 1 = 40 services (the received charters). */
export const CLUSTERS: { center: V3; count: number; radius: number }[] = [
  { center: [-2.3, -0.2, -2.6], count: 7, radius: 0.85 },
  { center: [0.5, 0.55, -6.5], count: 17, radius: 1.55 },
  { center: [2.7, -0.35, -4.0], count: 15, radius: 1.35 },
  { center: [-0.6, -1.1, -1.2], count: 1, radius: 0 },
];

export interface Star {
  p: V3;
  cluster: number;
}

/** The 40 service points. The first one is the service the sample question is about. */
export const STARS: Star[] = CLUSTERS.flatMap((c, cluster) =>
  Array.from({ length: c.count }, (_, i): Star => {
    const n = cluster * 31 + i;
    if (cluster === 0 && i === 0) return { p: add(c.center, [0.25, 0.12, 0.35]), cluster };
    // a point inside a ball, flattened a little so each office reads as a disc of points
    const r = c.radius * Math.cbrt(hash(n, 1));
    const a = hash(n, 2) * Math.PI * 2;
    const h = hash(n, 3) * 2 - 1;
    const s = Math.sqrt(1 - h * h);
    return { p: add(c.center, [r * s * Math.cos(a), r * h * 0.6, r * s * Math.sin(a)]), cluster };
  }),
);
export const TARGET_STAR = 0;

export const SHEET_COUNT = 40;
export const ROW_COUNT = 5;
/** The paper sheet before it is stretched into a checklist row: A4 proportions. */
export const SHEET_SIZE: [number, number] = [0.42, 0.594];

/** The steps of one request (scene 6), relative to WATCH: the corner where Core 2 sits, then five steps. */
const THREAD_KNOTS: V3[] = [
  [-1.9, 1.0, 0],
  [-1.45, 0.25, 0.2],
  [-0.7, -0.35, -0.1],
  [0.15, 0.2, 0.3],
  [0.95, -0.3, 0],
  [1.7, 0.15, -0.2],
];
export const THREAD_SPAN = 24;
/** Shares of the thread: the steps, the deadline of step 4 and where the thread stops (late, unfinished). */
export const THREAD_STOPS = { steps: [0.2, 0.4, 0.6, 0.8, 1.0], deadline: 0.71, end: 0.77 } as const;
const THREAD_DRAW = [0, 0.2, 0.4, 0.6, THREAD_STOPS.deadline, THREAD_STOPS.end];

/** Squeeze of sideways positions on a tall screen, so the picture fits the narrow stage. */
export const squeeze = (aspect: number): number => (isWide(aspect) ? 1 : 0.82);

/** The thread as points in the world, for an aspect. */
export function threadPath(aspect: number): V3[] {
  const fx = squeeze(aspect);
  return smoothPath(
    THREAD_KNOTS.map((k) => add(WATCH, [k[0] * fx, k[1], k[2]])),
    THREAD_SPAN,
  );
}

function pathPoint(path: V3[], share: number): V3 {
  const x = clamp01(share) * (path.length - 1);
  const i = Math.min(path.length - 2, Math.floor(x));
  return lerp3(path[i]!, path[i + 1]!, x - i);
}

/** Piecewise-linear lookup: `xs` rising, `ys` the value at each. */
function along(v: number, xs: readonly number[], ys: readonly number[]): number {
  if (v <= xs[0]!) return ys[0]!;
  for (let i = 1; i < xs.length; i++) {
    if (v <= xs[i]!) return mix(ys[i - 1]!, ys[i]!, seg(v, xs[i - 1]!, xs[i]!));
  }
  return ys[ys.length - 1]!;
}

export interface CoreState {
  p: V3;
  scale: number;
  /** 0 dark to 1 fully lit; the heartbeat pushes it a little over 1. */
  power: number;
}
export interface Glow {
  p: V3;
  size: number;
  color: V3;
  a: number;
}
export interface Ring {
  p: V3;
  radius: number;
  /** Line thickness as a share of the radius. */
  width: number;
  color: V3;
  a: number;
}
export interface Burst {
  p: V3;
  /** Life, 0 to 1. */
  t: number;
  color: V3;
  spread: number;
}
export interface Sheet {
  p: V3;
  q: Quat;
  sx: number;
  sy: number;
  a: number;
  /** 0 a sheet of paper, 1 a checklist row. */
  row: number;
}
export interface Beam {
  from: V3;
  to: V3;
  grow: number;
  width: number;
  a: number;
}
export type AnchorId = "office0" | "office1" | "office2" | "office3" | "service" | "outside" | "alert";

export interface Frame {
  cam: { p: V3; look: V3; fov: number };
  subject: { x: number; y: number };
  cyan: CoreState;
  orange: CoreState;
  glass: { p: V3; open: number; a: number };
  corridor: { a: number };
  sheets: Sheet[];
  stars: { a: number; collapse: number; lit: number; squeeze: number };
  beams: Beam[];
  orb: { p: V3; size: number; a: number };
  clock: { p: V3; size: number; a: number; ticks: number; hand: number };
  thread: { a: number; draw: number; grey: number; late: number };
  floor: { a: number; warp: number; center: V3 };
  dust: { a: number };
  glows: Glow[];
  rings: Ring[];
  bursts: Burst[];
  anchors: Record<AnchorId, { p: V3; a: number }>;
  /** Strength of the lens fringe in the last pass: a little more while the camera moves fast. */
  fringe: number;
}

/** The heartbeat: two quick beats, then a rest. One pair about every 1.25 s. */
export function heartbeat(time: number): number {
  const phase = (((time % 1.25) + 1.25) % 1.25) / 1.25;
  const second = phase > 0.2 ? 0.7 * Math.exp(-(phase - 0.2) * 11) : 0;
  return Math.exp(-phase * 9) + second;
}

export function direct(u: number, hook: number, time: number, aspect: number): Frame {
  const wide = isWide(aspect);
  const fx = squeeze(aspect);
  const k = Math.max(1, 0.9 / aspect); // stand further back on a tall screen
  const D = REST * k;
  const h = clamp01(hook);

  // ---- camera -------------------------------------------------------------------------------------
  const travel = easeInOut(seg(u, 0.55, 1.95)); // through the module and down the corridor
  const fly = easeInOut(seg(u, BEAT.fly[0], BEAT.fly[1])) * (1 - easeInOut(seg(u, 4.0, 4.28)));
  const swingPos = easeInOut(seg(u, BEAT.swing[0], BEAT.swing[1]));
  const swingLook = easeInOut(seg(u, BEAT.swing[0], BEAT.swing[1] - 0.12)); // the look leads: a swing
  const target: V3 = [STARS[TARGET_STAR]!.p[0] * fx, STARS[TARGET_STAR]!.p[1], STARS[TARGET_STAR]!.p[2]];

  let camP: V3 = [0, mix(0, 0.12, ramp(u, 0.8, 1.2)) * (1 - ramp(u, 1.8, 2.0)), mix(TITLE_Z + D + (1 - easeOutCubic(h)) * 1.4, D, travel)];
  let camLook: V3 = [0, camP[1] * 0.6, camP[2] - 10];
  if (u >= 1.95) camLook = [0, 0, 0];
  // scene 2: lean in a little; scene 3c: fly to the service; scene 5: swing to Core 2
  camP = add(camP, [0, 0, -0.6 * k * window4(u, 2.1, 2.5, 2.95, 3.1)]);
  const flyP: V3 = add(target, [0.45, 0.2, 3.3 * k]);
  camP = lerp3(camP, flyP, fly);
  camLook = lerp3(camLook, target, fly);
  camP = lerp3(camP, add(WATCH, [0, 0, D]), swingPos);
  camLook = lerp3(camLook, WATCH, swingLook);
  // idle sway, so a still frame is never dead
  const sway = 1 - 0.7 * window4(u, 0.6, 0.8, 1.9, 2.0);
  camP = add(camP, [Math.sin(time * 0.23) * 0.16 * sway, Math.sin(time * 0.17 + 1) * 0.09 * sway, 0]);
  const basis = lookBasis(camP, camLook);

  // ---- the two cores and the glass module ------------------------------------------------------------
  const inTitle = u < 1.06;
  const doors = ramp(u, BEAT.doors[0], BEAT.doors[1]);
  const open2 = ramp(u, BEAT.open[0], BEAT.open[1]);
  const lamp = ramp(u, BEAT.lamp[0], BEAT.lamp[1]);
  const shut7 = ramp(u, BEAT.close[0], BEAT.close[1]);
  const merge = ramp(u, BEAT.merge[0], BEAT.merge[1]);
  const heart = window4(u, BEAT.heart[0], BEAT.heart[1], BEAT.heart[2], BEAT.heart[3]);
  const beat = heartbeat(time) * heart;
  const slot = 0.62;

  const cyan: CoreState = { p: [0, 0, 0], scale: 1, power: 1 };
  const orange: CoreState = { p: [0, 0, 0], scale: 1, power: 1 };
  if (inTitle) {
    const out = ramp(h, HOOK.split, HOOK.split + 0.25);
    const lit1 = easeOutCubic(seg(h, HOOK.cyan, HOOK.cyan + 0.3));
    const lit2 = easeOutCubic(seg(h, HOOK.orange, HOOK.orange + 0.3));
    const gone = 1 - ramp(u, 0.82, 0.98);
    cyan.p = [-(slot * out + 1.9 * doors), 0, TITLE_Z];
    orange.p = [slot * out + 1.9 * doors, 0, TITLE_Z];
    cyan.scale = (h < HOOK.split ? 0 : mix(0.1, 1, lit1)) * gone;
    orange.scale = (h < HOOK.split ? 0 : mix(0.1, 1, lit2)) * gone;
    cyan.power = mix(0.7, 1, lit1) * gone;
    orange.power = mix(0.7, 1, lit2) * gone;
  } else {
    const arrive = ramp(u, 1.12, 1.3);
    const lampP: V3 = [0, wide ? 1.3 : 1.2, 0];
    // Core 1: slot, then centre stage, then a lamp above its work, then home beside Core 2
    let p: V3 = lerp3([-slot, 0, 0], [0, 0, 0.8], open2);
    p = lerp3(p, lampP, lamp);
    const home7 = easeInOut(seg(u, 7.02, 7.32));
    p = lerp3(p, add(WATCH, [-slot, 0, 0]), home7);
    p = add(p, [0, Math.sin(home7 * Math.PI) * 0.8, 0]);
    p = lerp3(p, WATCH, merge);
    cyan.p = p;
    cyan.scale = mix(mix(mix(1, 1.55, open2), 0.55, lamp), 1, home7) * (1 + 0.07 * beat) * (1 - 0.75 * merge);
    cyan.power = arrive * mix(1, 0.3, ramp(u, 5.0, 5.3) * (1 - home7)) * (1 + 0.22 * beat) * (1 - ramp(u, BEAT.cta[0], BEAT.cta[1]));
    // Core 2: slot, steps back while Core 1 works, waits at WATCH, takes the stage, then a corner, then home
    let o: V3 = lerp3([slot, 0, 0], [2.3 * fx, 0.7, -2.2], open2);
    o = lerp3(o, WATCH, ramp(u, 3.0, 3.3));
    const corner = ramp(u, 6.0, 6.14) * (1 - ramp(u, 7.02, 7.3));
    o = add(o, [-1.9 * fx * corner + slot * ramp(u, 7.02, 7.3) * (1 - merge), 1.0 * corner, 0]);
    orange.p = o;
    const stage5 = ramp(u, 5.1, 5.4);
    orange.scale = mix(mix(mix(1, 0.5, open2), 1.45, stage5), 1, ramp(u, 7.02, 7.3)) * mix(1, 0.4, corner) * (1 + 0.07 * beat) * (1 - 0.75 * merge);
    orange.power = arrive * mix(mix(1, 0.3, open2), 0.1, ramp(u, 3.0, 3.1)) * (1 - stage5) + stage5 * (1 + 0.22 * beat) * (1 - ramp(u, BEAT.cta[0], BEAT.cta[1]));
  }

  const glassA = inTitle
    ? ramp(h, HOOK.glass, 1) * (1 - ramp(u, 0.78, 0.96))
    : ramp(u, 1.12, 1.3) * (1 - 0.6 * open2) * (1 - ramp(u, 2.95, 3.08)) + shut7 * (1 - ramp(u, 8.0, 8.2));
  const glass = {
    p: (inTitle ? [0, 0, TITLE_Z] : u < 5 ? [0, 0, 0] : WATCH) as V3,
    open: inTitle ? doors * 1.9 : u < 5 ? open2 * 1.25 : (1 - shut7) * 1.25,
    a: glassA,
  };

  // ---- scene 1: corridor and paper ------------------------------------------------------------------------
  const corridorA = window4(u, BEAT.corridor[0], BEAT.corridor[1], BEAT.corridor[2], BEAT.corridor[3]);
  const sheets: Sheet[] = [];
  const camQ = basisQuat(basis);
  const rowsIn = seg(u, BEAT.rows[0] - 0.01, BEAT.rows[0] + 0.03) * (1 - ramp(u, 4.16, 4.27));
  const fall = seg(u, BEAT.collapse[0], BEAT.collapse[1] - 0.04);
  for (let i = 0; i < SHEET_COUNT; i++) {
    if (corridorA > 0) {
      const side = i % 2 ? -1 : 1;
      const z = 39 - i * 0.9;
      const t = clamp01((7 - (camP[2] - z)) / 9);
      const lift = easeOutCubic(t);
      const rest = eulerQuat(-0.35 + hash(i, 5) * 0.5, (hash(i, 6) - 0.5) * 1.2, (hash(i, 7) - 0.5) * 0.5);
      const spin = eulerQuat(t * (2 + hash(i, 8) * 4), t * (hash(i, 9) * 6 - 3), t * (hash(i, 10) * 4 - 2));
      sheets.push({
        p: [
          side * (0.6 + hash(i, 1) * 0.75) + (hash(i, 3) - 0.5) * 2.2 * t,
          -0.8 + hash(i, 2) * 0.6 + (0.5 + hash(i, 4) * 1.2) * lift + Math.sin(t * 6 + i) * 0.06,
          z + 2.2 * t,
        ],
        q: mulQuat(rest, spin),
        sx: 1,
        sy: 1,
        a: corridorA * (0.35 + 0.65 * Math.min(1, t * 3)),
        row: 0,
      });
    } else if (i < ROW_COUNT && rowsIn > 0) {
      const t = easeOutCubic(seg(u, BEAT.rows[0] + 0.03 * i, BEAT.rows[0] + 0.1 + 0.03 * i));
      const slotP = fromCamera(camP, basis, [0, (wide ? 0.64 : 0.36) - (wide ? 0.32 : 0.27) * i, -4.4]);
      let p = lerp3(target, slotP, t);
      p = add(p, scale(basis.up, Math.sin(t * Math.PI) * 0.35));
      p = lerp3(p, [0, 0, 0], fall * fall);
      const turn = (1 - t) * (3 + i);
      sheets.push({
        p,
        q: mulQuat(camQ, eulerQuat(turn * 0.7, turn, turn * 0.4)),
        sx: mix(0.3, 3.6, t) * (1 - fall),
        sy: mix(0.3, wide ? 0.36 : 0.31, t) * (1 - fall),
        a: rowsIn * Math.min(1, t * 4),
        row: ramp(t, 0.5, 1),
      });
    } else {
      sheets.push({ p: [0, 0, 0], q: [0, 0, 0, 1], sx: 0, sy: 0, a: 0, row: 0 });
    }
  }

  // ---- scene 3: the question, the sweep, the constellations, the beam -----------------------------------
  const starsA = ramp(u, BEAT.stars[0], BEAT.stars[1]) * (1 - ramp(u, BEAT.collapse[1] - 0.04, BEAT.collapse[1] + 0.04));
  const lit = ramp(u, BEAT.lit[0], BEAT.lit[1]);
  const narrow = ramp(u, BEAT.narrow[0], BEAT.narrow[1]);
  const beamsOff = 1 - ramp(u, 3.95, 4.05);
  const beams: Beam[] = CLUSTERS.map((c, i) => {
    const center: V3 = [c.center[0] * fx, c.center[1], c.center[2]];
    const start = BEAT.fan[0] + i * 0.02;
    return {
      from: cyan.p,
      to: i === 0 ? lerp3(center, target, narrow) : center,
      grow: ramp(u, start, start + 0.07),
      width: i === 0 ? mix(0.5, 0.07, narrow) : 0.5 * (0.5 + c.radius / 2),
      a: (i === 0 ? 1 : 1 - ramp(u, 3.52, 3.6)) * beamsOff * 0.5,
    };
  });

  // ---- scene 4 and 8: the orb ------------------------------------------------------------------------------
  const orbGrow = ramp(u, BEAT.orb[0], BEAT.orb[1]) * (1 - ramp(u, BEAT.card[0], BEAT.card[1] - 0.02));
  const orbCta = ramp(u, BEAT.merge[1] - 0.1, BEAT.cta[1]);
  const orb = { p: (u < 6 ? [0, 0, 0] : WATCH) as V3, size: u < 6 ? orbGrow : 1.25 * orbCta, a: u < 6 ? Math.min(1, orbGrow * 2) : orbCta };

  // ---- scene 5 to 6: the clock ring ------------------------------------------------------------------------------
  const ringFly = easeInOut(seg(u, 5.02, 5.32));
  const clockA = ramp(u, 5.0, 5.06) * (1 - ramp(u, 7.0, 7.12));
  const clock = {
    p: u < 5.32 ? lerp3([0, 0, 0], WATCH, ringFly) : orange.p,
    size: mix(0.35, 1.3, ramp(u, 5.05, 5.35)) * mix(1, 0.42, ramp(u, 6.0, 6.14)),
    a: clockA,
    ticks: ramp(u, BEAT.clock[0], BEAT.clock[1]),
    hand: time * 0.9 + u * 5,
  };

  // ---- scene 6: the thread ----------------------------------------------------------------------------------------
  const path = threadPath(aspect);
  const threadA = ramp(u, 6.05, 6.1) * (1 - ramp(u, BEAT.reel[0] + 0.05, BEAT.reel[1] + 0.02));
  const draw = along(u, BEAT.thread, THREAD_DRAW) * (1 - ramp(u, BEAT.reel[0], BEAT.reel[1]));
  const greyOn = ramp(u, BEAT.grey[0], BEAT.grey[1]);
  const lateOn = ramp(u, BEAT.late[0], BEAT.late[1]);
  const head = pathPoint(path, draw);

  // ---- glows, rings, bursts --------------------------------------------------------------------------------------
  const glows: Glow[] = [];
  const rings: Ring[] = [];
  const bursts: Burst[] = [];
  const title: V3 = [0, 0, TITLE_Z];
  if (inTitle) {
    // the first spark: one orange point, alive, before anything else exists
    const sparkA = (1 - ramp(h, HOOK.split, HOOK.split + 0.2)) * (0.75 + 0.25 * Math.sin(time * 9));
    glows.push({ p: title, size: 0.5 + 0.9 * seg(h, 0, HOOK.split), color: ORANGE, a: sparkA });
    glows.push({ p: title, size: 0.12, color: WHITE, a: sparkA });
    bursts.push({ p: title, t: seg(h, HOOK.split - 0.01, HOOK.split + 0.4), color: ORANGE, spread: 1.6 });
    bursts.push({ p: [-slot, 0, TITLE_Z], t: seg(h, HOOK.cyan, HOOK.cyan + 0.4), color: CYAN, spread: 1.1 });
    bursts.push({ p: [slot, 0, TITLE_Z], t: seg(h, HOOK.orange, HOOK.orange + 0.4), color: ORANGE, spread: 1.1 });
  }
  glows.push({ p: cyan.p, size: 2.7 * cyan.scale, color: CYAN, a: 0.5 * Math.min(1.3, cyan.power) });
  glows.push({ p: orange.p, size: 2.7 * orange.scale, color: ORANGE, a: 0.5 * Math.min(1.3, orange.power) });

  // scene 2: listening rings round Core 1
  const listen = ramp(u, 2.35, 2.6) * (1 - ramp(u, 3.0, 3.1));
  if (listen > 0) {
    for (let i = 0; i < 4; i++) {
      const f = (((time * 0.3 + i / 4) % 1) + 1) % 1;
      rings.push({ p: cyan.p, radius: (0.75 + f * 1.7) * cyan.scale * 0.65, width: 0.012, color: CYAN, a: listen * 0.5 * (1 - f) ** 1.5 });
    }
  }
  // scene 3a: the safety sweep passes over the question
  const sweep = seg(u, BEAT.sweep[0], BEAT.sweep[1]);
  if (sweep > 0 && sweep < 1) {
    rings.push({ p: [0, 0, 0.6], radius: 0.2 + 3.6 * sweep, width: 0.007, color: CYAN, a: 0.9 * Math.min(1, sweep * 8) * (1 - sweep) ** 0.7 });
    rings.push({ p: [0, 0, 0.6], radius: 0.2 + 3.35 * sweep, width: 0.004, color: CYAN, a: 0.35 * Math.min(1, sweep * 8) * (1 - sweep) });
  }
  // scene 3c: the one service lights
  if (lit > 0 && starsA > 0) {
    glows.push({ p: target, size: 1.5, color: CYAN, a: 0.7 * lit * starsA * (1 - 0.6 * ramp(u, BEAT.rows[0], BEAT.rows[0] + 0.05)) });
    glows.push({ p: target, size: 0.3, color: WHITE, a: lit * starsA });
    rings.push({ p: target, radius: 0.32, width: 0.04, color: WHITE, a: 0.8 * lit * starsA * (1 - ramp(u, BEAT.rows[0] - 0.02, BEAT.rows[0] + 0.03)) });
    bursts.push({ p: target, t: seg(u, BEAT.lit[0], BEAT.lit[0] + 0.14), color: CYAN, spread: 1.2 });
  }
  // scene 6: step markers, the deadline pulse, the head of the thread
  if (threadA > 0) {
    THREAD_STOPS.steps.forEach((s, i) => {
      const reached = draw >= s - 0.005;
      const outside = i === 2; // the step done by another agency
      rings.push({ p: pathPoint(path, s), radius: 0.11, width: 0.14, color: outside ? GREY : reached ? ORANGE : WHITE, a: threadA * (reached ? 0.95 : 0.4) });
      if (reached && !outside) glows.push({ p: pathPoint(path, s), size: 0.5, color: ORANGE, a: 0.6 * threadA });
    });
    glows.push({ p: head, size: 0.55 + 0.5 * lateOn, color: ORANGE, a: threadA * (draw > 0.001 ? 0.9 : 0) });
    glows.push({ p: head, size: 0.14, color: WHITE, a: threadA * (draw > 0.001 ? 1 : 0) });
    if (lateOn > 0) {
      const mark = pathPoint(path, THREAD_STOPS.deadline);
      bursts.push({ p: mark, t: seg(u, BEAT.late[0], BEAT.late[0] + 0.13), color: ORANGE, spread: 1.3 });
      for (let i = 0; i < 2; i++) {
        const f = (((time * 0.55 + i / 2) % 1) + 1) % 1;
        rings.push({ p: head, radius: 0.15 + f * 0.75, width: 0.03, color: ORANGE, a: threadA * lateOn * 0.7 * (1 - f) ** 2 });
      }
    }
  }
  // scene 7: both cores beat in step
  if (heart > 0) {
    const phase = (((time % 1.25) + 1.25) % 1.25) / 1.25;
    for (const [core, color] of [
      [cyan, CYAN],
      [orange, ORANGE],
    ] as const) {
      rings.push({ p: core.p, radius: 0.5 + phase * 1.3, width: 0.02, color, a: heart * 0.55 * (1 - phase) ** 2 });
    }
  }
  if (u > BEAT.merge[0]) bursts.push({ p: WATCH, t: seg(u, BEAT.merge[1] - 0.06, BEAT.merge[1] + 0.12), color: ORANGE, spread: 1.4 });

  // ---- labels the page pins to points of the picture ---------------------------------------------------------
  const officeA = ramp(u, BEAT.offices[0], BEAT.offices[1]) * (1 - ramp(u, 3.74, 3.8));
  const anchors = {} as Frame["anchors"];
  CLUSTERS.forEach((c, i) => {
    anchors[`office${i}` as AnchorId] = {
      p: [c.center[0] * fx, c.center[1] + c.radius * 0.6 + 0.35, c.center[2]],
      a: officeA * (i === 0 ? 1 : 1 - ramp(u, 3.52, 3.6)),
    };
  });
  anchors.service = { p: add(target, [0, -0.45, 0]), a: ramp(u, 3.66, 3.72) * (1 - ramp(u, 3.95, 4.0)) };
  const out = 1 - ramp(u, 6.93, 6.99);
  anchors.outside = { p: add(pathPoint(path, 0.5), [0, -0.3, 0]), a: ramp(u, 6.32, 6.4) * out * (wide ? 1 : 1 - ramp(u, BEAT.alert[0] - 0.06, BEAT.alert[0])) };
  anchors.alert = { p: add(head, [0, -0.35, 0]), a: ramp(u, BEAT.alert[0], BEAT.alert[0] + 0.06) * out };

  const moving = Math.max(window4(u, 0.6, 0.9, 1.7, 1.95), window4(u, 3.5, 3.56, 3.66, 3.72), window4(u, 5.0, 5.1, 5.25, 5.4));

  return {
    cam: { p: camP, look: camLook, fov: FOV },
    subject: subjectPoint(u, aspect),
    cyan,
    orange,
    glass,
    corridor: { a: corridorA },
    sheets,
    stars: { a: starsA, collapse: easeInOut(seg(u, BEAT.collapse[0], BEAT.collapse[1])), lit, squeeze: fx },
    beams,
    orb,
    clock,
    thread: { a: threadA, draw, grey: greyOn, late: lateOn },
    floor: {
      a: 0.55 * ramp(u, 1.9, 2.2),
      warp: u < 6 ? ramp(u, 4.1, 4.32) * (1 - ramp(u, BEAT.card[0], BEAT.card[1])) : 0.7 * orbCta,
      center: orb.p,
    },
    dust: { a: 0.6 * ramp(h, 0.3, 0.9) },
    glows,
    rings,
    bursts,
    anchors,
    fringe: 0.001 + 0.0016 * moving,
  };
}
