// The canvas and its frame loop. This file and everything it imports (three.js, the shaders) is a chunk
// of its own, loaded by the landing page after its first paint and only when WebGL is there.
import { useEffect, useRef, type RefObject } from "react";
import type { Playhead } from "../playhead";
import { FrameBudget, scrubOpacity, WARMUP_MS } from "../quality";
import { direct, type AnchorId } from "./director";
import { createStage, LOWEST_LEVEL, type Stage } from "./stage";

/** With nothing moving for this long the loop draws every second frame: the idle shimmer needs no more. */
const IDLE_AFTER_MS = 2000;

interface Props {
  playhead: Playhead;
  /** The stage element: labels with a `data-anchor` inside it are pinned to points of the picture. */
  stageRef: RefObject<HTMLElement | null>;
  /** Called when WebGL cannot start or the context is lost: the page falls back to the still posters. */
  onLost: () => void;
  /** Called once, after the first frame is on screen. */
  onReady: () => void;
}

export default function Stage3D({ playhead, stageRef, onLost, onReady }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const host = stageRef.current;
    if (!canvas || !host) return;
    let stage: Stage;
    try {
      stage = createStage(canvas);
    } catch {
      onLost();
      return;
    }
    const budget = new FrameBudget();
    const labels = new Map<AnchorId, { el: HTMLElement; half: number }>();
    let raf = 0;
    let last = 0;
    let clock = 0; // seconds the picture has been running: it stops with the loop
    let born = 0;
    let lastMove = 0;
    let skip = false;
    let onScreen = true;
    let first = true;
    let size = { w: 1, h: 1 };
    let lastPos = playhead.pos;
    let speed = 0;
    let shownOpacity = 1;

    function findLabels() {
      labels.clear();
      host!.querySelectorAll<HTMLElement>("[data-anchor]").forEach((el) => {
        labels.set(el.dataset.anchor as AnchorId, { el, half: el.offsetWidth / 2 });
      });
    }

    function resize() {
      const box = host!.getBoundingClientRect();
      size = { w: box.width, h: box.height };
      stage.resize(box.width, box.height, window.devicePixelRatio || 1);
      findLabels();
      canvas!.dataset.level = String(stage.level);
    }

    function draw(now: number) {
      raf = 0;
      if (document.hidden || !onScreen) {
        last = 0;
        return;
      }
      raf = requestAnimationFrame(draw);
      const gap = last ? now - last : 0;
      last = now;
      if (!born) born = now;
      if (playhead.moving) lastMove = now;
      // idle: half rate
      skip = now - lastMove > IDLE_AFTER_MS ? !skip : false;
      if (skip) return;
      clock += Math.min(gap, 100) / 1000;

      // scrubbing guard: dim the picture while the story is dragged through faster than it is meant to run
      if (gap > 0) {
        const current = Math.abs(playhead.pos - lastPos) / (Math.min(gap, 100) / 1000);
        speed += (current - speed) * Math.min(1, gap / 180);
        lastPos = playhead.pos;
        const opacity = scrubOpacity(speed);
        if (Math.abs(opacity - shownOpacity) > 0.01) {
          shownOpacity = opacity;
          canvas!.style.opacity = opacity.toFixed(2);
        }
      }

      const started = performance.now();
      const frame = direct(playhead.pos, playhead.hook, clock, size.w / size.h);
      stage.render(frame, clock);
      const points = stage.anchors(frame);
      for (const [id, label] of labels) {
        const point = points[id];
        if (!point || point.a <= 0.01) {
          if (label.el.style.visibility !== "hidden") label.el.style.visibility = "hidden";
          continue;
        }
        const x = Math.min(size.w - label.half - 10, Math.max(label.half + 10, point.x));
        label.el.style.visibility = "visible";
        label.el.style.opacity = point.a.toFixed(3);
        label.el.style.transform = `translate3d(${x.toFixed(1)}px, ${point.y.toFixed(1)}px, 0)`;
      }
      const drawMs = performance.now() - started;

      if (first) {
        first = false;
        onReady();
      }
      // adaptive quality: only while the picture is really animating at full rate, after a short warm-up
      if (gap && now - born > WARMUP_MS && now - lastMove < IDLE_AFTER_MS && stage.level < LOWEST_LEVEL && budget.frame(gap, drawMs)) {
        stage.setLevel(stage.level + 1);
        canvas!.dataset.level = String(stage.level);
      }
    }

    function wake() {
      if (!raf && !document.hidden && onScreen) raf = requestAnimationFrame(draw);
    }
    function lost(event: Event) {
      event.preventDefault();
      onLost();
    }

    resize();
    const resizer = new ResizeObserver(resize);
    resizer.observe(host);
    const watcher = new IntersectionObserver(([entry]) => {
      onScreen = !!entry?.isIntersecting;
      wake();
    });
    watcher.observe(host);
    document.addEventListener("visibilitychange", wake);
    canvas.addEventListener("webglcontextlost", lost);
    wake();

    return () => {
      if (raf) cancelAnimationFrame(raf);
      resizer.disconnect();
      watcher.disconnect();
      document.removeEventListener("visibilitychange", wake);
      canvas.removeEventListener("webglcontextlost", lost);
      stage.dispose();
    };
  }, [playhead, stageRef, onLost, onReady]);

  return <canvas ref={canvasRef} className="lp-canvas" aria-hidden="true" />;
}
