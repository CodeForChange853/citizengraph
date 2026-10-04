import { useEffect, useRef, type RefObject } from "react";
import { useTranslation } from "react-i18next";
import { SERVICE_TOTAL } from "./demo";
import { drawStage, type Quality, type StageLayout } from "./draw";
import { buildTrail } from "./geometry";
import { useTimeline } from "./hooks";
import { FrameBudget, WARMUP_MS } from "./quality";
import { POSTER_TIME } from "./timeline";

const DPR_CAP: Record<Quality, number> = { 2: 2, 1: 1.5, 0: 1 };
/** Space kept clear between the graph and the edge of its zone. */
const PAD = 14;

/**
 * The Canvas 2D stage. It redraws only when the timeline moves, never while it is off-screen or the
 * tab is hidden, at a device pixel ratio of 2 at most, and it lowers its own quality if frames run slow.
 * With `still` (reduced motion) it draws one poster frame and never follows the timeline.
 */
export function StageCanvas({ zoneRef, still }: { zoneRef: RefObject<HTMLElement | null>; still: boolean }) {
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
    const stage = canvas.parentElement;

    let quality: Quality = 2;
    let layout: StageLayout | null = null;
    let visible = true;
    let frame = 0;
    let lastFrame = 0;
    const budget = new FrameBudget();
    const mountedAt = performance.now();

    function measure() {
      const box = canvas!.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, DPR_CAP[quality]);
      const width = box.width;
      const height = box.height;
      canvas!.width = Math.max(1, Math.round(width * dpr));
      canvas!.height = Math.max(1, Math.round(height * dpr));
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
      canvas!.dataset.quality = String(quality);

      const z = zoneRef.current?.getBoundingClientRect();
      const zone = z
        ? { x: z.left - box.left + PAD, y: z.top - box.top + PAD, w: z.width - PAD * 2, h: z.height - PAD * 2 }
        : { x: PAD, y: PAD, w: width - PAD * 2, h: height - PAD * 2 };
      // The line under the question, and the end of the question on it.
      const rule = stage?.querySelector(".lp-amber")?.getBoundingClientRect();
      const end = stage?.querySelector("[data-lp-origin]")?.getBoundingClientRect();
      const lineY = rule ? rule.top + rule.height / 2 - box.top : height * 0.6;
      const origin = { x: end ? end.left - box.left : width * 0.3, y: lineY };
      if (zone.w <= 0 || zone.h <= 0) {
        layout = null;
        return;
      }
      layout = {
        width,
        height,
        zone,
        origin,
        lineY,
        fontPx: Math.max(13, 0.8125 * parseFloat(getComputedStyle(document.documentElement).fontSize)),
        trail: buildTrail({ x: (origin.x - zone.x) / zone.w, y: (origin.y - zone.y) / zone.h }),
      };
      schedule();
    }

    function render(now: number) {
      frame = 0;
      if (!visible || document.hidden || !layout) return; // stays dirty until shown again
      const gap = now - lastFrame;
      lastFrame = now;
      const started = performance.now();
      drawStage(context, layout, still ? POSTER_TIME : timeline.time, quality);
      const drawMs = performance.now() - started;
      // Adaptive quality (see quality.ts): too many late frames, or slow drawing, costs a level.
      if (quality > 0 && started - mountedAt > WARMUP_MS && budget.frame(gap, drawMs)) {
        quality = (quality - 1) as Quality;
        measure(); // resizes the backing store for the new pixel ratio and redraws
      }
    }

    function schedule() {
      if (!frame) frame = requestAnimationFrame(render);
    }

    measure();
    const unsubscribe = still ? () => {} : timeline.subscribe(schedule);
    const resize = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    resize?.observe(canvas);
    if (zoneRef.current) resize?.observe(zoneRef.current);
    const terminal = stage?.querySelector(".lp-term");
    if (terminal) resize?.observe(terminal);
    const seen =
      typeof IntersectionObserver === "undefined"
        ? null
        : new IntersectionObserver(([entry]) => {
            visible = entry?.isIntersecting ?? true;
            if (visible) schedule();
          });
    seen?.observe(canvas);
    document.addEventListener("visibilitychange", schedule);
    void document.fonts?.ready.then(measure); // the web font moves the end of the question

    return () => {
      unsubscribe();
      resize?.disconnect();
      seen?.disconnect();
      document.removeEventListener("visibilitychange", schedule);
      if (frame) cancelAnimationFrame(frame);
    };
  }, [timeline, zoneRef, still]);

  return (
    <canvas ref={ref} className="lp-canvas" role="img" aria-label={t("landing.stageAlt", { count: SERVICE_TOTAL })} />
  );
}
