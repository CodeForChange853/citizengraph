// Small easing helpers shared by the picture, the page and the tests.

export const clamp01 = (v: number): number => Math.min(1, Math.max(0, v));

/** 0 before `from`, 1 after `to`, straight in between. */
export const seg = (v: number, from: number, to: number): number => clamp01((v - from) / (to - from));

/** 0 before `from`, 1 after `to`, smooth (smoothstep) in between. */
export function ramp(v: number, from: number, to: number): number {
  const t = seg(v, from, to);
  return t * t * (3 - 2 * t);
}

/** Fast start, soft landing: for anything that draws itself or arrives. */
export const easeOutCubic = (t: number): number => 1 - (1 - clamp01(t)) ** 3;

/** Soft start and landing: for camera moves. */
export function easeInOut(t: number): number {
  const x = clamp01(t);
  return x < 0.5 ? 4 * x * x * x : 1 - (-2 * x + 2) ** 3 / 2;
}

export const mix = (a: number, b: number, t: number): number => a + (b - a) * t;

/** Up over [a, b], held, down over [c, d]. */
export const window4 = (v: number, a: number, b: number, c: number, d: number): number => ramp(v, a, b) * (1 - ramp(v, c, d));
