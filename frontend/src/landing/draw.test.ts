import { describe, expect, it } from "vitest";
import { drawStage, type Quality, type StageLayout } from "./draw";
import { buildTrail } from "./geometry";
import { beat, INTRO_END, POSTER_TIME, TIMELINE_END } from "./timeline";

/** A stand-in 2D context that records what was drawn (jsdom has no canvas). */
interface Call {
  op: string;
  style: string;
}

function recorder() {
  const calls: Call[] = [];
  const noop = () => {};
  const ctx = {
    strokeStyle: "",
    fillStyle: "",
    lineWidth: 1,
    lineJoin: "",
    lineCap: "",
    font: "",
    textBaseline: "",
    textAlign: "",
    globalAlpha: 1,
    clearRect: noop,
    beginPath: noop,
    closePath: noop,
    moveTo: noop,
    lineTo: noop,
    arc: noop,
    ellipse: noop,
    rect: noop,
    save: noop,
    restore: noop,
    translate: noop,
    rotate: noop,
    scale: noop,
    setLineDash: noop,
    fillRect(): void {
      calls.push({ op: "fillRect", style: this.fillStyle });
    },
    fillText(text: string): void {
      calls.push({ op: `text:${text}`, style: this.fillStyle });
    },
    measureText: (text: string) => ({ width: text.length * 8 }),
    createRadialGradient: () => ({ addColorStop: noop }),
    stroke(): void {
      calls.push({ op: "stroke", style: this.strokeStyle });
    },
    fill(): void {
      calls.push({ op: "fill", style: String(this.fillStyle) });
    },
  };
  return { ctx: ctx as unknown as CanvasRenderingContext2D, calls };
}

const zone = { x: 700, y: 120, w: 600, h: 520 };
const origin = { x: 420, y: 400 };
const layout: StageLayout = {
  width: 1366,
  height: 768,
  zone,
  origin,
  lineY: 400,
  fontPx: 13,
  trail: buildTrail({ x: (origin.x - zone.x) / zone.w, y: (origin.y - zone.y) / zone.h }),
};

function drawn(time: number, quality: Quality = 2) {
  const { ctx, calls } = recorder();
  drawStage(ctx, layout, time, quality);
  return calls;
}

describe("stage picture", () => {
  it("is alive on the very first frame: grid, crop marks and the glowing start of the line", () => {
    const calls = drawn(0);
    expect(calls.filter((c) => c.op === "stroke").length).toBeGreaterThanOrEqual(6);
    expect(calls.filter((c) => c.op === "fill").length).toBeGreaterThanOrEqual(1); // the start point
  });

  it("draws every moment of the timeline without failing, at every quality level", () => {
    for (const quality of [0, 1, 2] as const) {
      for (let time = 0; time <= TIMELINE_END; time += 125) expect(() => drawn(time, quality)).not.toThrow();
    }
    expect(() => drawn(POSTER_TIME)).not.toThrow();
  });

  it("is a pure function of the time: the same time gives the same frame", () => {
    const time = beat("offices").start + 900;
    expect(drawn(time)).toEqual(drawn(time));
    drawn(TIMELINE_END); // drawing a later frame in between leaves no state behind
    expect(drawn(time)).toEqual(drawn(time));
  });

  it("labels the four offices with their service counts once beat 3 has played", () => {
    const text = drawn(INTRO_END)
      .filter((c) => c.op.startsWith("text:"))
      .map((c) => c.op.slice(5));
    expect(text).toEqual(expect.arrayContaining(["BPLO 07", "LCRO 17", "CHO 15", "CSWDO 01"]));
  });

  it("draws less at lower quality: fewer glow passes and no sparks at level 0", () => {
    const time = 300; // the line is drawing and sparks fly off its head
    expect(drawn(time, 0).length).toBeLessThan(drawn(time, 1).length);
    expect(drawn(time, 1).length).toBeLessThan(drawn(time, 2).length);
  });
});
