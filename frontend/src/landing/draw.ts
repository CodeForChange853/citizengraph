// The stage picture. `drawStage` is a pure function of the layout, the timeline time and the quality
// level: it keeps no state between frames, so the picture can be scrubbed forwards and backwards and the
// same time always gives the same frame. All colours come from the palette roles.
import { calloutAt, ENTER_AT, guardTicks, LINE_MS, SERVICE_TOTAL } from "./demo";
import { clamp01, easeOutCubic, ramp } from "./ease";
import { OFFICE_CELLS, RING_SEGMENTS, RINGS, SEEDS, TARGET, type Pt, type Seed } from "./geometry";
import { withAlpha, type Role } from "./palette";
import { beat, BEATS, beatNumberAt, intoAt, progressAt } from "./timeline";

/** 2 = full quality, 1 = lower resolution, thinner glow and half the sparks, 0 = plain lines at 1x. */
export type Quality = 0 | 1 | 2;

export interface Zone {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** Everything the picture needs to know about the page, in CSS pixels relative to the canvas. */
export interface StageLayout {
  width: number;
  height: number;
  /** Where the graph sits. */
  zone: Zone;
  /** The end of the typed question: rings ripple from here and the trail starts here. */
  origin: Pt;
  /** The height of the line under the question. */
  lineY: number;
  /** Size of the mono HUD text. */
  fontPx: number;
  /** The glow trail in graph units (see geometry.buildTrail). */
  trail: Pt[];
}

type Ctx = CanvasRenderingContext2D;
type XY = [number, number];

/** Stroke widths and alphas of the glow passes, widest first. */
const GLOW: Record<Quality, [number, number][]> = {
  2: [
    [11, 0.1],
    [6, 0.22],
    [2.25, 1],
  ],
  1: [
    [7, 0.18],
    [2.25, 1],
  ],
  0: [[2.25, 1]],
};
/** Share of the sparks drawn at each quality level. */
const SPARK_SHARE: Record<Quality, number> = { 2: 1, 1: 0.5, 0: 0 };

const GRID = 48;
const MONO = '"Atkinson Hyperlegible Mono", ui-monospace, Consolas, monospace';
const TAU = Math.PI * 2;

function polyline(ctx: Ctx, points: Pt[], count: number, at: (p: Pt) => XY, step = 1) {
  ctx.beginPath();
  for (let i = 0; i < count; i += step) {
    const [x, y] = at(points[i]!);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  if (count > 0 && (count - 1) % step !== 0) ctx.lineTo(...at(points[count - 1]!));
}

/** Stroke the current path once per glow pass. */
function glowStroke(ctx: Ctx, role: Role, alpha: number, quality: Quality, build: () => void) {
  for (const [lineWidth, a] of GLOW[quality]) {
    ctx.strokeStyle = withAlpha(role, a * alpha);
    ctx.lineWidth = lineWidth;
    build();
    ctx.stroke();
  }
}

/** A bright dot with a soft bloom: the head of a line or trail. */
function head(ctx: Ctx, x: number, y: number, alpha: number, quality: Quality) {
  if (alpha <= 0) return;
  if (quality > 0) {
    ctx.fillStyle = withAlpha("glow", 0.16 * alpha);
    ctx.beginPath();
    ctx.arc(x, y, 13, 0, TAU);
    ctx.fill();
    ctx.fillStyle = withAlpha("glow", 0.3 * alpha);
    ctx.beginPath();
    ctx.arc(x, y, 7, 0, TAU);
    ctx.fill();
  }
  ctx.fillStyle = withAlpha("glow", alpha);
  ctx.beginPath();
  ctx.arc(x, y, 3.5, 0, TAU);
  ctx.fill();
}

function cropMarks(ctx: Ctx, x: number, y: number, w: number, h: number, size: number, colour: (corner: number) => string) {
  const corners = [
    [x, y, 1, 1],
    [x + w, y, -1, 1],
    [x + w, y + h, -1, -1],
    [x, y + h, 1, -1],
  ] as const;
  corners.forEach(([cx, cy, dx, dy], i) => {
    ctx.strokeStyle = colour(i);
    ctx.beginPath();
    ctx.moveTo(cx + dx * size, cy);
    ctx.lineTo(cx, cy);
    ctx.lineTo(cx, cy + dy * size);
    ctx.stroke();
  });
}

/**
 * One burst of sparks. Each spark is born at `born(seed)` seconds, lives `life(seed)` seconds and flies
 * from `from(seed)` with velocity `velocity(seed)` under a little gravity; `now` is the clock in seconds.
 */
function sparks(
  ctx: Ctx,
  seeds: Seed[],
  now: number,
  born: (s: Seed) => number,
  life: (s: Seed) => number,
  from: (s: Seed) => XY,
  velocity: (s: Seed) => XY,
) {
  ctx.lineWidth = 1.5;
  for (const s of seeds) {
    const age = now - born(s);
    const span = life(s);
    if (age <= 0 || age >= span) continue;
    const [x0, y0] = from(s);
    const [vx, vy] = velocity(s);
    const gravity = 380;
    const x = x0 + vx * age;
    const y = y0 + vy * age + 0.5 * gravity * age * age;
    const fade = 1 - age / span;
    ctx.strokeStyle = withAlpha("glow", fade * fade);
    ctx.beginPath();
    ctx.moveTo(x - vx * 0.035, y - (vy + gravity * age) * 0.035);
    ctx.lineTo(x, y);
    ctx.stroke();
  }
}

export function drawStage(ctx: Ctx, layout: StageLayout, time: number, quality: Quality): void {
  const { width, height, zone, origin, lineY, fontPx } = layout;
  ctx.clearRect(0, 0, width, height);
  ctx.lineJoin = "round";
  ctx.lineCap = "round";

  const askMs = Math.max(0, intoAt("ask", time));
  const contours = progressAt("contours", time);
  const offices = progressAt("offices", time);
  const trail = progressAt("trail", time);
  const at = (p: Pt): XY => [zone.x + p.x * zone.w, zone.y + p.y * zone.h];
  const sparkCount = Math.round(SEEDS.length * SPARK_SHARE[quality]);

  // ---- Always there, from the very first frame: a faint ruled grid and the frame's crop marks.
  ctx.strokeStyle = withAlpha("line", 0.3 + 0.25 * ramp(askMs, 0, 400));
  ctx.lineWidth = 1;
  ctx.beginPath();
  for (let x = (width % GRID) / 2; x <= width; x += GRID) {
    ctx.moveTo(x, 0);
    ctx.lineTo(x, height);
  }
  for (let y = lineY % GRID; y <= height; y += GRID) {
    ctx.moveTo(0, y);
    ctx.lineTo(width, y);
  }
  ctx.stroke();
  ctx.lineWidth = 1.5;
  cropMarks(ctx, 8, 8, width - 16, height - 16, 12, () => withAlpha("muted", 0.9));

  // ---- Beat 2: contour rings ripple out from the end of the question, across the whole stage.
  if (contours > 0) {
    const scale = Math.max(width, height) * 1.05;
    const ringAt = (p: Pt): XY => [origin.x + p.x * scale, origin.y + p.y * scale];
    ctx.lineWidth = 1.25;
    RINGS.forEach((ring, k) => {
      const shown = ramp(contours, k * 0.065, k * 0.065 + 0.4);
      if (shown <= 0) return;
      const count = Math.ceil(shown * RING_SEGMENTS) + 1;
      ctx.strokeStyle = withAlpha("line", 0.95 - 0.35 * offices);
      polyline(ctx, ring, count, ringAt, quality === 0 ? 2 : 1);
      ctx.stroke();
      if (shown < 1) {
        // the ripple: a ring is brighter while it is still drawing itself
        ctx.strokeStyle = withAlpha("muted", 0.55 * (1 - shown));
        ctx.stroke();
      }
    });
  }

  // ---- Beat 1: the line draws across the stage. At t=0 only its glowing start point is there.
  const lineP = easeOutCubic(askMs / LINE_MS);
  const lineX = Math.max(6, width * lineP);
  const settled = ramp(askMs, LINE_MS, LINE_MS + 700);
  glowStroke(ctx, "glow", 1 - 0.5 * settled, quality, () => {
    ctx.beginPath();
    ctx.moveTo(0, lineY);
    ctx.lineTo(lineX, lineY);
  });
  head(ctx, lineX, lineY, 1 - settled, quality);

  if (sparkCount > 0) {
    const now = askMs / 1000;
    // off the head of the line while it draws
    sparks(
      ctx,
      SEEDS.slice(0, Math.ceil(sparkCount * 0.36)),
      now,
      (s) => (s.a * LINE_MS) / 1000,
      (s) => 0.3 + s.b * 0.35,
      (s) => [width * easeOutCubic(s.a), lineY],
      (s) => [-(60 + s.c * 180), (s.d - 0.5) * 300],
    );
    // a burst from the end of the question when it is sent
    sparks(
      ctx,
      SEEDS.slice(26, 26 + Math.ceil(sparkCount * 0.25)),
      now,
      () => ENTER_AT / 1000,
      (s) => 0.35 + s.b * 0.4,
      () => [origin.x, origin.y],
      (s) => [Math.cos(s.a * TAU) * (70 + s.c * 190), Math.sin(s.a * TAU) * (70 + s.c * 190) - 60],
    );
    // beat 2: small hops along the line
    const from = beat("contours").start / 1000;
    const span = beat("contours").dur / 1000;
    sparks(
      ctx,
      SEEDS.slice(44, 44 + Math.ceil(sparkCount * 0.3)),
      time / 1000,
      (s) => from + s.a * span * 0.9,
      (s) => 0.35 + s.c * 0.3,
      (s) => [s.b * width, lineY],
      (s) => [(s.d - 0.5) * 80, -(50 + s.c * 130)],
    );
  }

  // ---- Crop marks round the graph. Each guardrail check of beat 4 turns one of them to the accent.
  const marks = ramp(contours, 0.5, 1);
  if (marks > 0) {
    const ticks = guardTicks(intoAt("query", time));
    ctx.lineWidth = 1.5;
    cropMarks(ctx, zone.x, zone.y, zone.w, zone.h, 12, (i) => (i < ticks ? withAlpha("accent", marks) : withAlpha("text", 0.85 * marks)));
    // HUD: a step counter. It counts the beats of this page and claims nothing about the system.
    ctx.font = `700 ${fontPx}px ${MONO}`;
    ctx.textBaseline = "top";
    ctx.textAlign = "right";
    ctx.fillStyle = withAlpha("muted", marks);
    ctx.fillText(`STEP ${String(beatNumberAt(time)).padStart(2, "0")}/${String(BEATS.length).padStart(2, "0")}`, zone.x + zone.w - 18, zone.y + 4);
    ctx.textAlign = "left";
  }
  if (offices <= 0) return;

  // ---- Beat 3: the office cells grow from their corners, then each office's services pop in.
  const edges = ramp(offices, 0, 0.45);
  ctx.strokeStyle = withAlpha("edge", 1);
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  const tips: XY[] = [];
  for (const office of OFFICE_CELLS) {
    const corners = office.cell.map(at);
    corners.forEach((a, i) => {
      const b = corners[(i + 1) % corners.length]!;
      const mid: XY = [a[0] + ((b[0] - a[0]) * edges) / 2, a[1] + ((b[1] - a[1]) * edges) / 2];
      const back: XY = [b[0] + ((a[0] - b[0]) * edges) / 2, b[1] + ((a[1] - b[1]) * edges) / 2];
      ctx.moveTo(a[0], a[1]);
      ctx.lineTo(mid[0], mid[1]);
      ctx.moveTo(b[0], b[1]);
      ctx.lineTo(back[0], back[1]);
      if (edges < 1) tips.push(mid, back);
    });
  }
  ctx.stroke();
  if (tips.length) {
    ctx.fillStyle = withAlpha("text", 1 - edges * 0.5);
    ctx.beginPath();
    for (const [x, y] of tips) {
      ctx.moveTo(x + 1.75, y);
      ctx.arc(x, y, 1.75, 0, TAU);
    }
    ctx.fill();
  }

  let index = 0;
  const nodeShown = (i: number) => ramp(offices, 0.3 + (0.55 * i) / SERVICE_TOTAL, 0.36 + (0.55 * i) / SERVICE_TOTAL);
  // spokes first, so the nodes sit on top of them
  ctx.lineWidth = 1;
  ctx.strokeStyle = withAlpha("edge", 0.75);
  ctx.beginPath();
  for (const office of OFFICE_CELLS) {
    const [hx, hy] = at(office.hub);
    for (const node of office.nodes) {
      const shown = nodeShown(index++);
      if (shown <= 0) continue;
      const [x, y] = at(node);
      ctx.moveTo(hx, hy);
      ctx.lineTo(hx + (x - hx) * shown, hy + (y - hy) * shown);
    }
  }
  ctx.stroke();

  index = 0;
  ctx.fillStyle = withAlpha("text", 1);
  ctx.beginPath();
  for (const office of OFFICE_CELLS) {
    for (const node of office.nodes) {
      const shown = nodeShown(index++);
      if (shown <= 0) continue;
      const [x, y] = at(node);
      ctx.moveTo(x + 3 * shown, y);
      ctx.arc(x, y, 3 * shown, 0, TAU);
    }
  }
  ctx.fill();

  // Office hubs with HUD callouts: a leader line out to "BPLO 07". They light one after another.
  ctx.font = `700 ${fontPx}px ${MONO}`;
  ctx.textBaseline = "middle";
  ctx.lineWidth = 1.5;
  OFFICE_CELLS.forEach((office, i) => {
    const lit = ramp(offices, calloutAt(i), calloutAt(i) + 0.12);
    if (lit <= 0) return;
    const [x, y] = at(office.hub);
    ctx.fillStyle = withAlpha("stage", lit);
    ctx.strokeStyle = withAlpha("text", lit);
    ctx.beginPath();
    ctx.arc(x, y, 6, 0, TAU);
    ctx.fill();
    ctx.stroke();
    const text = `${office.id} ${String(office.count).padStart(2, "0")}`;
    const textWidth = ctx.measureText(text).width;
    const left = x + 22 + textWidth > zone.x + zone.w; // flip the callout at the right edge
    const dir = left ? -1 : 1;
    ctx.beginPath();
    ctx.moveTo(x + dir * 5, y - 5);
    ctx.lineTo(x + dir * 12, y - 14);
    ctx.lineTo(x + dir * (12 + 8 * lit), y - 14);
    ctx.stroke();
    const tx = left ? x - 24 - textWidth : x + 24;
    ctx.fillStyle = withAlpha("stage", 0.85 * lit);
    ctx.fillRect(tx - 3, y - 14 - fontPx * 0.7, textWidth + 6, fontPx * 1.4);
    ctx.fillStyle = withAlpha("text", lit);
    ctx.fillText(text, tx, y - 14);
  });
  if (trail <= 0) return;

  // ---- Beat 5: the glow trail leaves the question, crosses the graph and lands on the service.
  const reach = ramp(trail, 0, 0.34);
  const count = Math.max(2, Math.ceil(reach * (layout.trail.length - 1)) + 1);
  glowStroke(ctx, "glow", 1, quality, () => polyline(ctx, layout.trail, count, at));
  const [headX, headY] = at(layout.trail[count - 1]!);
  head(ctx, headX, headY, 1, quality);

  const landed = ramp(trail, 0.3, 0.42);
  if (landed > 0) {
    const [x, y] = at(TARGET);
    ctx.lineWidth = 2;
    for (const delay of [0, 0.35]) {
      const pulse = clamp01((landed - delay) / (1 - delay));
      if (pulse <= 0) continue;
      ctx.strokeStyle = withAlpha("glow", 1 - 0.55 * pulse);
      ctx.beginPath();
      ctx.arc(x, y, 5 + 13 * pulse, 0, TAU);
      ctx.stroke();
    }
    ctx.fillStyle = withAlpha("glow", 1);
    ctx.beginPath();
    ctx.arc(x, y, 5, 0, TAU);
    ctx.fill();
  }
}
