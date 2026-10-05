// GLSL for the journeys: service points, beams, the orb, the clock ring.
import { NOISE } from "./shaders";

// ---- the service points; they can spiral into the origin (the collapse into the orb) ------------
export const STAR_VERT = /* glsl */ `
attribute float aSeed;
attribute float aTarget;
uniform float uCollapse;
uniform float uLit;
uniform float uSqueeze;
uniform float uPx;
uniform float uTime;
uniform float uAlpha;
varying float vA;
varying float vTarget;
void main() {
  vec3 p = position;
  p.x *= uSqueeze;
  float c = uCollapse;
  float turn = c * c * (3.0 + aSeed * 5.0);
  float keep = pow(1.0 - c, 1.6);
  p = vec3(p.x * cos(turn) - p.z * sin(turn), p.y * (1.0 - c * 0.8), p.x * sin(turn) + p.z * cos(turn)) * keep;
  vec4 mv = viewMatrix * vec4(p, 1.0);
  gl_Position = projectionMatrix * mv;
  float twinkle = 0.8 + 0.2 * sin(uTime * 1.7 + aSeed * 40.0);
  vTarget = aTarget * uLit;
  vA = uAlpha * twinkle * mix(1.0, 0.4, uLit * (1.0 - aTarget));
  gl_PointSize = clamp(uPx * 0.16 * (0.7 + aSeed * 0.6) * (1.0 + 0.9 * vTarget) / -mv.z, 2.0, 22.0 + 12.0 * vTarget);
}
`;
export const STAR_FRAG = /* glsl */ `
uniform vec3 uColor;
varying float vA;
varying float vTarget;
void main() {
  float d = length(gl_PointCoord - 0.5) * 2.0;
  float core = 1.0 - smoothstep(0.18, 0.4, d);
  float halo = exp(-d * d * 5.0) * (1.0 - smoothstep(0.8, 1.0, d));
  vec3 col = mix(uColor, vec3(1.0), 0.25 + 0.6 * vTarget) * halo * 0.9 + vec3(1.0) * core;
  gl_FragColor = vec4(col * vA, 1.0);
}
`;
export const LINK_FRAG = /* glsl */ `
uniform vec3 uColor;
varying float vA;
void main() {
  gl_FragColor = vec4(uColor * vA * 0.4, 1.0);
}
`;

// ---- a beam: bright along its axis, fading to its edges and its far end ---------------------------
export const BEAM_VERT = /* glsl */ `
attribute vec3 aShade;
varying vec3 vShade;
void main() {
  vShade = aShade;
  gl_Position = projectionMatrix * viewMatrix * vec4(position, 1.0);
}
`;
export const BEAM_FRAG = /* glsl */ `
uniform vec3 uColor;
varying vec3 vShade;
void main() {
  // across is 0 on the axis and +-1 on the edges of the far end; at the apex it is 0 everywhere
  float across = abs(vShade.x) / max(vShade.y, 0.001);
  float body = pow(1.0 - clamp(across, 0.0, 1.0), 1.6);
  float axis = 1.0 - smoothstep(0.0, 0.05, across);
  float along = 0.35 + 0.65 * (1.0 - vShade.y);
  gl_FragColor = vec4((uColor * body * 0.55 + vec3(1.0) * axis * 0.5) * along * vShade.z, 1.0);
}
`;

// ---- the orb: a black disc, a thin hot rim, a tilted accretion ring with streaks, a bent grid -----
export const ORB_VERT = /* glsl */ `
uniform vec3 uCenter;
uniform float uSize;
varying vec2 vUv;
void main() {
  vUv = position.xy * 2.0;
  vec4 mv = viewMatrix * vec4(uCenter, 1.0);
  mv.xy += position.xy * uSize;
  gl_Position = projectionMatrix * mv;
}
`;
export const ORB_FRAG = /* glsl */ `
uniform float uAlpha;
uniform float uTime;
uniform float uDetail;
uniform vec3 uHot;
varying vec2 vUv;
${NOISE}
const float HORIZON = 0.2;
float streaks(float angle, float radius, float t) {
  return fbm3(vec3(angle * 2.2 + t, radius * 9.0, t * 0.25));
}
void main() {
  vec2 p = vUv;
  float r = length(p);
  float angle = atan(p.y, p.x);
  float edge = 1.0 - smoothstep(0.86, 1.0, r);

  // the grid of space, pulled toward the centre
  float pull = 1.0 + 0.055 / (r * r + 0.02);
  vec2 q = p * pull * 5.0;
  vec2 g = abs(fract(q - 0.5) - 0.5) / fwidth(q);
  float grid = (1.0 - min(min(g.x, g.y), 1.0)) * smoothstep(HORIZON * 1.25, HORIZON * 2.4, r) * edge * 0.22;

  // the accretion ring: a disc seen almost edge on, turning
  vec2 e = vec2(p.x, p.y / 0.26);
  float er = length(e);
  float ea = atan(e.y, e.x);
  float band = smoothstep(0.3, 0.42, er) * (1.0 - smoothstep(0.62, 0.95, er));
  float fine = uDetail > 0.5 ? streaks(ea, er, uTime * 0.22) : 0.6;
  float disc = band * (0.15 + 2.2 * fine * fine * fine) * (1.25 - er);
  // the far half of the ring is hidden behind the disc
  float hidden = step(0.0, p.y) * (1.0 - smoothstep(HORIZON * 0.92, HORIZON * 1.02, r));
  disc *= 1.0 - hidden;

  // light bent over the top and under the bottom of the disc: a thin halo
  float halo = exp(-pow((r - HORIZON * 1.32) / 0.035, 2.0)) * (0.55 + 0.45 * abs(sin(angle)));
  float rim = exp(-pow((r - HORIZON * 1.02) / 0.012, 2.0));
  float glow = exp(-r * r * 9.0) * 0.28;

  vec3 col = uHot * (disc * 0.62 + halo * 0.55 + glow * 0.5) + vec3(1.0, 0.86, 0.7) * (disc * disc * 0.22 + rim * 0.7) + vec3(0.55, 0.6, 0.68) * grid;
  // the disc itself is black and hides what is behind it; the front of the ring passes over it
  float hole = (1.0 - smoothstep(HORIZON * 0.94, HORIZON, r)) * (1.0 - clamp(disc * 2.0, 0.0, 1.0) * step(p.y, 0.0));
  gl_FragColor = vec4(col * edge * uAlpha * (1.0 - hole), hole * uAlpha);
}
`;

// ---- the clock ring round Core 2: a circle, sixty ticks, one hand with a fading sweep behind it ----
export const CLOCK_FRAG = /* glsl */ `
uniform float uAlpha;
uniform float uTicks;
uniform float uHand;
uniform vec3 uHot;
varying vec2 vUv;
const float PI = 3.14159265;
void main() {
  vec2 p = vUv;
  float r = length(p);
  float aa = fwidth(r) * 1.3;
  float angle = atan(p.x, p.y); // clockwise from the top
  float circle = 1.0 - smoothstep(0.006, 0.006 + aa, abs(r - 0.9));
  float turn = fract(angle / (2.0 * PI));
  float cell = abs(fract(turn * 60.0) - 0.5);
  float major = step(abs(fract(turn * 12.0 + 0.5) - 0.5), 0.1);
  float inner = mix(0.84, 0.77, major);
  float aw = fwidth(turn * 60.0) * 1.2;
  float tick = smoothstep(0.5 - 0.09 - aw, 0.5 - 0.09, cell) * step(inner, r) * step(r, 0.9);
  float behind = fract((uHand - angle) / (2.0 * PI)); // 0 at the hand, growing behind it
  float reach = step(0.5, r) * step(r, 0.9);
  float sweep = pow(1.0 - behind, 6.0) * reach * 0.28;
  float handLine = (1.0 - smoothstep(0.0, 0.006 + aw * 0.02, min(behind, 1.0 - behind))) * step(0.42, r) * step(r, 0.9);
  vec3 col = uHot * (circle * 0.9 + sweep * uTicks) + vec3(1.0) * (tick * 0.75 * uTicks + handLine * uTicks);
  gl_FragColor = vec4(col * uAlpha, 1.0);
}
`;
