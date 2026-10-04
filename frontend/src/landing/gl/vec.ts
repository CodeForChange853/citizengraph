// Small vector helpers for the director. Plain arrays, no three.js, so the director can be tested alone.

export type V3 = [number, number, number];
export type Quat = [number, number, number, number];

export const add = (a: V3, b: V3): V3 => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
export const sub = (a: V3, b: V3): V3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
export const scale = (a: V3, s: number): V3 => [a[0] * s, a[1] * s, a[2] * s];
export const lerp3 = (a: V3, b: V3, t: number): V3 => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
export const length = (a: V3): number => Math.hypot(a[0], a[1], a[2]);
export const distance = (a: V3, b: V3): number => length(sub(a, b));

export function normalize(a: V3): V3 {
  const l = length(a) || 1;
  return [a[0] / l, a[1] / l, a[2] / l];
}

export function cross(a: V3, b: V3): V3 {
  return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
}

/** A repeatable number in 0 to 1 for an index and a channel: the same every visit, nothing random at run time. */
export function hash(i: number, channel = 0): number {
  const x = Math.sin(i * 127.1 + channel * 311.7 + 0.5) * 43758.5453;
  return x - Math.floor(x);
}

export interface Basis {
  right: V3;
  up: V3;
  /** From the camera toward what it looks at. */
  forward: V3;
}

/** The camera's axes when it stands at `eye` and looks at `target` (world up is +y). */
export function lookBasis(eye: V3, target: V3): Basis {
  const forward = normalize(sub(target, eye));
  const right = normalize(cross(forward, [0, 1, 0]));
  const up = cross(right, forward);
  return { right, up, forward };
}

/** A point given in the camera's own axes (x right, y up, z toward the viewer), as a world point. */
export function fromCamera(eye: V3, basis: Basis, local: V3): V3 {
  return [
    eye[0] + basis.right[0] * local[0] + basis.up[0] * local[1] - basis.forward[0] * local[2],
    eye[1] + basis.right[1] * local[0] + basis.up[1] * local[1] - basis.forward[1] * local[2],
    eye[2] + basis.right[2] * local[0] + basis.up[2] * local[1] - basis.forward[2] * local[2],
  ];
}

/** The rotation that turns a flat sheet (facing +z) to face the camera. */
export function basisQuat(basis: Basis): Quat {
  // rotation matrix columns: right, up, back
  const [m00, m10, m20] = basis.right;
  const [m01, m11, m21] = basis.up;
  const m02 = -basis.forward[0];
  const m12 = -basis.forward[1];
  const m22 = -basis.forward[2];
  const trace = m00 + m11 + m22;
  if (trace > 0) {
    const s = 0.5 / Math.sqrt(trace + 1);
    return [(m21 - m12) * s, (m02 - m20) * s, (m10 - m01) * s, 0.25 / s];
  }
  if (m00 > m11 && m00 > m22) {
    const s = 2 * Math.sqrt(1 + m00 - m11 - m22);
    return [0.25 * s, (m01 + m10) / s, (m02 + m20) / s, (m21 - m12) / s];
  }
  if (m11 > m22) {
    const s = 2 * Math.sqrt(1 + m11 - m00 - m22);
    return [(m01 + m10) / s, 0.25 * s, (m12 + m21) / s, (m02 - m20) / s];
  }
  const s = 2 * Math.sqrt(1 + m22 - m00 - m11);
  return [(m02 + m20) / s, (m12 + m21) / s, 0.25 * s, (m10 - m01) / s];
}

/** Rotation from three turns about x, y and z (radians), applied in that order. */
export function eulerQuat(x: number, y: number, z: number): Quat {
  const [c1, s1] = [Math.cos(x / 2), Math.sin(x / 2)];
  const [c2, s2] = [Math.cos(y / 2), Math.sin(y / 2)];
  const [c3, s3] = [Math.cos(z / 2), Math.sin(z / 2)];
  return [s1 * c2 * c3 + c1 * s2 * s3, c1 * s2 * c3 - s1 * c2 * s3, c1 * c2 * s3 + s1 * s2 * c3, c1 * c2 * c3 - s1 * s2 * s3];
}

export function mulQuat(a: Quat, b: Quat): Quat {
  return [
    a[3] * b[0] + a[0] * b[3] + a[1] * b[2] - a[2] * b[1],
    a[3] * b[1] - a[0] * b[2] + a[1] * b[3] + a[2] * b[0],
    a[3] * b[2] + a[0] * b[1] - a[1] * b[0] + a[2] * b[3],
    a[3] * b[3] - a[0] * b[0] - a[1] * b[1] - a[2] * b[2],
  ];
}

/** Points along a smooth curve through `points` (Catmull-Rom), `perSpan` samples between each pair. */
export function smoothPath(points: V3[], perSpan: number): V3[] {
  const out: V3[] = [];
  const at = (i: number) => points[Math.min(points.length - 1, Math.max(0, i))]!;
  for (let i = 0; i < points.length - 1; i++) {
    const [p0, p1, p2, p3] = [at(i - 1), at(i), at(i + 1), at(i + 2)];
    for (let k = 0; k < perSpan; k++) {
      const t = k / perSpan;
      const t2 = t * t;
      const t3 = t2 * t;
      out.push([0, 1, 2].map((c) => 0.5 * (2 * p1[c]! + (-p0[c]! + p2[c]!) * t + (2 * p0[c]! - 5 * p1[c]! + 4 * p2[c]! - p3[c]!) * t2 + (-p0[c]! + 3 * p1[c]! - 3 * p2[c]! + p3[c]!) * t3)) as V3);
    }
  }
  out.push(points[points.length - 1]!);
  return out;
}
