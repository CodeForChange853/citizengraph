import { useEffect, useRef, type RefObject } from "react";
import { useTranslation } from "react-i18next";
import { SERVICE_TOTAL } from "./demo";
import { OFFICE_CELLS, RING_SEGMENTS, RINGS, TARGET, TRAIL, type Pt } from "./geometry";
import { ramp, useTimeline } from "./hooks";
import { withAlpha } from "./palette";
import type { Timeline } from "./timeline";

/** Where the graph sits inside the canvas, in CSS pixels. */
interface Zone {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** 2 = full quality, 1 = lower resolution and a thinner glow, 0 = plain lines at 1x. */
type Quality = 0 | 1 | 2;
const DPR_CAP: Record<Quality, number> = { 2: 2, 1: 1.5, 0: 1 };
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
/** Drop a quality level when frames stay slower than this for a while (about 40 a second). */
const SLOW_FRAME_MS = 25;
const SLOW_FRAMES = 24;

const TOTAL_NODES = SERVICE_TOTAL;

function path(ctx: CanvasRenderingContext2D, points: Pt[], count: number, at: (p: Pt) => [number, number], step = 1) {
  ctx.beginPath();
  for (let i = 0; i < count; i += step) {
    const [x, y] = at(points[i]!);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  if (count > 0 && (count - 1) % step !== 0) ctx.lineTo(...at(points[count - 1]!));
}

/** The whole stage picture as a function of the timeline: no state is kept between frames. */
export function drawStage(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  zone: Zone,
  timeline: Timeline,
  quality: Quality,
  fontPx: number,
): void {
  ctx.clearRect(0, 0, width, height);
  const contours = timeline.progress("contours");
  const offices = timeline.progress("offices");
  const trail = timeline.progress("trail");
  if (contours <= 0) return;

  const at = (p: Pt): [number, number] => [zone.x + p.x * zone.w, zone.y + p.y * zone.h];
  ctx.lineJoin = "round";
  ctx.lineCap = "round";

  // Beat 2: contour rings, each drawing itself round from the middle outwards.
  const cx = zone.x + zone.w / 2;
  const cy = zone.y + zone.h / 2;
  const scale = Math.max(zone.w, zone.h) * 0.95;
  const ringAt = (p: Pt): [number, number] => [cx + p.x * scale, cy + p.y * scale];
  ctx.strokeStyle = withAlpha("line", 1 - 0.45 * offices);
  ctx.lineWidth = 1.25;
  RINGS.forEach((ring, k) => {
    const shown = ramp(contours, k * 0.1, k * 0.1 + 0.4);
    if (shown <= 0) return;
    path(ctx, ring, Math.ceil(shown * RING_SEGMENTS) + 1, ringAt, quality === 0 ? 2 : 1);
    ctx.stroke();
  });

  // Crop marks at the corners of the graph.
  const mark = 12;
  ctx.strokeStyle = withAlpha("text", 0.85 * ramp(contours, 0.5, 1));
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  for (const [x, y, dx, dy] of [
    [zone.x, zone.y, 1, 1],
    [zone.x + zone.w, zone.y, -1, 1],
    [zone.x, zone.y + zone.h, 1, -1],
    [zone.x + zone.w, zone.y + zone.h, -1, -1],
  ] as const) {
    ctx.moveTo(x + dx * mark, y);
    ctx.lineTo(x, y);
    ctx.lineTo(x, y + dy * mark);
  }
  ctx.stroke();
  if (offices <= 0) return;

  // Beat 3: the four office cells, then each office's services.
  const edges = ramp(offices, 0, 0.45);
  ctx.strokeStyle = withAlpha("line", 1);
  ctx.lineWidth = 2;
  for (const office of OFFICE_CELLS) {
    const corners = office.cell.map(at);
    let length = 0;
    corners.forEach((c, i) => {
      const n = corners[(i + 1) % corners.length]!;
      length += Math.hypot(n[0] - c[0], n[1] - c[1]);
    });
    ctx.setLineDash([length * edges, length]);
    ctx.beginPath();
    corners.forEach(([x, y], i) => (i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)));
    ctx.closePath();
    ctx.stroke();
  }
  ctx.setLineDash([]);

  let index = 0;
  const nodeShown = (i: number) => ramp(offices, 0.3 + (0.55 * i) / TOTAL_NODES, 0.36 + (0.55 * i) / TOTAL_NODES);
  // spokes first, so the nodes sit on top of them
  ctx.lineWidth = 1;
  ctx.strokeStyle = withAlpha("line", 0.9);
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
      ctx.arc(x, y, 3 * shown, 0, Math.PI * 2);
    }
  }
  ctx.fill();

  // Office hubs with HUD callouts: a leader line out to "BPLO 07".
  const labels = ramp(offices, 0.2, 0.5);
  ctx.font = `700 ${fontPx}px "Atkinson Hyperlegible Mono", ui-monospace, Consolas, monospace`;
  ctx.textBaseline = "middle";
  ctx.lineWidth = 1.5;
  for (const office of OFFICE_CELLS) {
    const [x, y] = at(office.hub);
    ctx.fillStyle = withAlpha("stage", labels);
    ctx.strokeStyle = withAlpha("text", labels);
    ctx.beginPath();
    ctx.arc(x, y, 6, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    const text = `${office.id} ${String(office.count).padStart(2, "0")}`;
    const textWidth = ctx.measureText(text).width;
    const left = x + 22 + textWidth > zone.x + zone.w; // flip the callout at the right edge
    const dir = left ? -1 : 1;
    ctx.beginPath();
    ctx.moveTo(x + dir * 5, y - 5);
    ctx.lineTo(x + dir * 12, y - 14);
    ctx.lineTo(x + dir * 20, y - 14);
    ctx.stroke();
    const tx = left ? x - 24 - textWidth : x + 24;
    ctx.fillStyle = withAlpha("stage", 0.8 * labels);
    ctx.fillRect(tx - 3, y - 14 - fontPx * 0.7, textWidth + 6, fontPx * 1.4);
    ctx.fillStyle = withAlpha("text", labels);
    ctx.fillText(text, tx, y - 14);
  }
  if (trail <= 0) return;

  // Beat 5: the glow trail draws itself through the graph and lands on the service.
  const reach = ramp(trail, 0, 0.75);
  const count = Math.max(2, Math.ceil(reach * (TRAIL.length - 1)) + 1);
  for (const [lineWidth, alpha] of GLOW[quality]) {
    ctx.strokeStyle = withAlpha("accent", alpha);
    ctx.lineWidth = lineWidth;
    path(ctx, TRAIL, count, at);
    ctx.stroke();
  }
  const [hx, hy] = at(TRAIL[count - 1]!);
  ctx.fillStyle = withAlpha("accent", 1);
  ctx.beginPath();
  ctx.arc(hx, hy, 4, 0, Math.PI * 2);
  ctx.fill();

  const landed = ramp(trail, 0.7, 1);
  if (landed > 0) {
    const [x, y] = at(TARGET);
    ctx.strokeStyle = withAlpha("accent", landed);
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(x, y, 5 + 9 * landed, 0, Math.PI * 2);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(x, y, 5, 0, Math.PI * 2);
    ctx.fill();
  }
}

/**
 * The Canvas 2D stage. It redraws only when the timeline moves, never while it is off-screen or the
 * tab is hidden, at a device pixel ratio of 2 at most, and it lowers its own quality if frames run slow.
 */
export function StageCanvas({ zoneRef }: { zoneRef: RefObject<HTMLElement | null> }) {
  const { t } = useTranslation();
  const timeline = useTimeline();
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    let ctx: CanvasRenderingContext2D | null = null;
    try {
      ctx = canvas.getContext("2d");
    } catch {
      // no canvas (tests): the DOM carries the content
    }
    if (!ctx) return;
    const context = ctx;

    let quality: Quality = 2;
    let width = 0;
    let height = 0;
    let zone: Zone = { x: 0, y: 0, w: 0, h: 0 };
    let fontPx = 13;
    let visible = true;
    let frame = 0;
    let lastFrame = 0;
    let slow = 0;

    function measure() {
      const box = canvas!.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, DPR_CAP[quality]);
      width = box.width;
      height = box.height;
      canvas!.width = Math.max(1, Math.round(width * dpr));
      canvas!.height = Math.max(1, Math.round(height * dpr));
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
      const z = zoneRef.current?.getBoundingClientRect();
      const pad = 14;
      // The graph leaves the HUD row above it and the arc text below it clear.
      const above = zoneRef.current?.querySelector(".lp-stagehud")?.getBoundingClientRect().height ?? 0;
      const below = (zoneRef.current?.querySelector(".lp-arc")?.getBoundingClientRect().height ?? 0) * 0.7;
      zone = z
        ? {
            x: z.left - box.left + pad,
            y: z.top - box.top + pad + above,
            w: z.width - pad * 2,
            h: z.height - pad * 2 - above - below,
          }
        : { x: pad, y: pad, w: width - pad * 2, h: height - pad * 2 };
      fontPx = Math.max(13, 0.8125 * parseFloat(getComputedStyle(document.documentElement).fontSize));
      canvas!.dataset.quality = String(quality);
      schedule();
    }

    function render(now: number) {
      frame = 0;
      if (!visible || document.hidden || zone.w <= 0 || zone.h <= 0) return; // stays dirty until shown again
      // Adaptive frame budget: back-to-back frames that keep arriving late cost a quality level.
      const gap = now - lastFrame;
      lastFrame = now;
      if (gap < 1000) {
        slow = gap > SLOW_FRAME_MS ? slow + 1 : Math.max(0, slow - 1);
        if (slow >= SLOW_FRAMES && quality > 0) {
          quality = (quality - 1) as Quality;
          slow = 0;
          measure();
        }
      }
      drawStage(context, width, height, zone, timeline, quality, fontPx);
    }

    function schedule() {
      if (!frame) frame = requestAnimationFrame(render);
    }

    measure();
    const unsubscribe = timeline.subscribe(schedule);
    const resize = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    resize?.observe(canvas);
    if (zoneRef.current) resize?.observe(zoneRef.current);
    const seen =
      typeof IntersectionObserver === "undefined"
        ? null
        : new IntersectionObserver(([entry]) => {
            visible = entry?.isIntersecting ?? true;
            if (visible) schedule();
          });
    seen?.observe(canvas);
    document.addEventListener("visibilitychange", schedule);
    void document.fonts?.ready.then(schedule);

    return () => {
      unsubscribe();
      resize?.disconnect();
      seen?.disconnect();
      document.removeEventListener("visibilitychange", schedule);
      if (frame) cancelAnimationFrame(frame);
    };
  }, [timeline, zoneRef]);

  return (
    <canvas ref={ref} className="lp-canvas" role="img" aria-label={t("landing.stageAlt", { count: SERVICE_TOTAL })} />
  );
}
