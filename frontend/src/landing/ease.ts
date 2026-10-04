// Pure easing helpers shared by the canvas and the DOM pieces.

export const clamp01 = (v: number): number => Math.min(1, Math.max(0, v));

/** Smooth 0..1 ramp between two points of a progress value (smoothstep). */
export function ramp(p: number, from: number, to: number): number {
  const x = clamp01((p - from) / (to - from));
  return x * x * (3 - 2 * x);
}

/** Fast start, soft landing: for anything that draws itself. */
export function easeOutCubic(p: number): number {
  const x = 1 - clamp01(p);
  return 1 - x * x * x;
}
