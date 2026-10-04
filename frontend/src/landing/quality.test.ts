import { describe, expect, it } from "vitest";
import { FrameBudget, IDLE_GAP_MS, LATE_LIMIT, WINDOW_FRAMES } from "./quality";

/** Feed gaps until the budget asks for a step down; returns the frame number, or -1 if it never does. */
function firstStep(gaps: number[], draw = 2): number {
  const budget = new FrameBudget();
  for (let i = 0; i < gaps.length; i++) if (budget.frame(gaps[i]!, draw)) return i + 1;
  return -1;
}

const repeat = (pattern: number[], times: number) => Array.from({ length: times }, () => pattern).flat();

describe("adaptive quality budget", () => {
  it("never steps down on a steady 60 or 120 frames a second", () => {
    expect(firstStep(repeat([16.7], 600))).toBe(-1);
    expect(firstStep(repeat([8.3], 600))).toBe(-1);
  });

  it("steps down when one frame in four is late (4x CPU slow-down), which the old net counter missed", () => {
    const gaps = repeat([16.7, 16.7, 16.7, 33.4], 150);
    // the old rule: +1 for a late frame, -1 (not below 0) for an on-time one, step at 24
    let net = 0;
    let oldStepped = false;
    for (const gap of gaps) {
      net = gap > 25 ? net + 1 : Math.max(0, net - 1);
      if (net >= 24) oldStepped = true;
    }
    expect(oldStepped).toBe(false);
    const at = firstStep(gaps);
    expect(at).toBe(LATE_LIMIT * 4); // the sixth late frame, about 0.5 s in
  });

  it("steps down fast when every frame is late", () => {
    expect(firstStep(repeat([33.4], 100))).toBe(LATE_LIMIT);
  });

  it("forgives an odd hiccup: one late frame in a window is not a slow device", () => {
    expect(firstStep(repeat([...repeat([16.7], WINDOW_FRAMES - 1), 50], 20))).toBe(-1);
  });

  it("does not count the gap after an idle spell", () => {
    expect(firstStep(repeat([16.7, IDLE_GAP_MS, 16.7, 900], 100))).toBe(-1);
  });

  it("steps down when drawing itself is too slow even if frames arrive on time", () => {
    expect(firstStep(repeat([16.7], 100), 14)).toBe(20);
    expect(firstStep(repeat([16.7], 100), 6)).toBe(-1);
  });

  it("starts a fresh window after each step, so the next level is judged on its own frames", () => {
    const budget = new FrameBudget();
    const steps: number[] = [];
    repeat([33.4], 30).forEach((gap, i) => {
      if (budget.frame(gap, 2)) steps.push(i + 1);
    });
    expect(steps).toEqual([6, 12, 18, 24, 30]);
  });
});
