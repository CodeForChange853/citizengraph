// GLSL for the stage. Everything here is original: small procedural shaders, no textures, no files.

/** Value noise and a short fractal sum, shared by the cores and the orb. */
export const NOISE = /* glsl */ `
float hash31(vec3 p) {
  p = fract(p * vec3(0.1031, 0.1030, 0.0973));
  p += dot(p, p.yxz + 33.33);
  return fract((p.x + p.y) * p.z);
}
float noise3(vec3 p) {
  vec3 i = floor(p);
  vec3 f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  return mix(
    mix(mix(hash31(i), hash31(i + vec3(1, 0, 0)), f.x), mix(hash31(i + vec3(0, 1, 0)), hash31(i + vec3(1, 1, 0)), f.x), f.y),
    mix(mix(hash31(i + vec3(0, 0, 1)), hash31(i + vec3(1, 0, 1)), f.x), mix(hash31(i + vec3(0, 1, 1)), hash31(i + vec3(1, 1, 1)), f.x), f.y),
    f.z);
}
float fbm3(vec3 p) {
  float v = 0.0;
  float a = 0.5;
  for (int i = 0; i < 4; i++) {
    v += a * noise3(p);
    p = p * 2.02 + vec3(11.3, 7.1, 3.7);
    a *= 0.5;
  }
  return v;
}
`;

// ---- a core: a small sun with slow plasma and a bright rim ---------------------------------------------
export const CORE_VERT = /* glsl */ `
uniform float uTime;
uniform float uPower;
varying vec3 vNormal;
varying vec3 vView;
varying vec3 vLocal;
${NOISE}
void main() {
  vLocal = position;
  float swell = (noise3(position * 2.4 + vec3(0.0, uTime * 0.35, 0.0)) - 0.5) * 0.05 * uPower;
  vec3 p = position + normal * swell;
  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  vNormal = normalize(normalMatrix * normal);
  vView = normalize(-mv.xyz);
  gl_Position = projectionMatrix * mv;
}
`;
export const CORE_FRAG = /* glsl */ `
uniform float uTime;
uniform float uPower;
uniform vec3 uColor;
varying vec3 vNormal;
varying vec3 vView;
varying vec3 vLocal;
${NOISE}
void main() {
  float facing = clamp(dot(normalize(vNormal), normalize(vView)), 0.0, 1.0);
  float rim = pow(1.0 - facing, 2.2);
  vec3 q = vLocal * 3.2 + vec3(uTime * 0.12, -uTime * 0.2, uTime * 0.07);
  float plasma = fbm3(q + fbm3(q * 1.7) * 1.4);
  float veins = smoothstep(0.42, 0.75, plasma);
  vec3 col = uColor * (0.14 + 1.6 * veins) + vec3(1.0) * veins * veins * 0.55;
  col += uColor * rim * 1.6 + vec3(1.0) * pow(rim, 3.0) * 0.5;
  col *= 0.35 + 0.65 * facing + rim;
  gl_FragColor = vec4(col * uPower, 1.0);
}
`;

// ---- glass: nothing but a rim and a streak of light -------------------------------------------------------
export const GLASS_VERT = /* glsl */ `
varying vec3 vNormal;
varying vec3 vView;
void main() {
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  vNormal = normalize(normalMatrix * normal);
  vView = normalize(-mv.xyz);
  gl_Position = projectionMatrix * mv;
}
`;
export const GLASS_FRAG = /* glsl */ `
uniform float uAlpha;
uniform vec3 uTint;
varying vec3 vNormal;
varying vec3 vView;
void main() {
  vec3 n = normalize(vNormal);
  vec3 v = normalize(vView);
  float facing = abs(dot(n, v));
  float rim = pow(1.0 - facing, 2.4);
  float streak = pow(max(dot(reflect(-v, n * sign(dot(n, v))), normalize(vec3(0.35, 0.8, 0.5))), 0.0), 36.0);
  vec3 col = mix(vec3(0.8, 0.88, 1.0), uTint, 0.45) * (0.02 + 0.3 * rim) + vec3(1.0) * streak * 0.3;
  gl_FragColor = vec4(col * uAlpha, 1.0);
}
`;

// ---- instanced billboards: soft glows and thin rings ---------------------------------------------------
export const BILLBOARD_VERT = /* glsl */ `
attribute vec3 iPos;
attribute float iSize;
attribute vec4 iColor;
attribute float iWidth;
varying vec2 vUv;
varying vec4 vColor;
varying float vWidth;
void main() {
  vUv = position.xy * 2.0;
  vColor = iColor;
  vWidth = iWidth;
  vec4 mv = viewMatrix * vec4(iPos, 1.0);
  mv.xy += position.xy * iSize;
  gl_Position = projectionMatrix * mv;
}
`;
export const GLOW_FRAG = /* glsl */ `
varying vec2 vUv;
varying vec4 vColor;
void main() {
  float d = length(vUv);
  float a = exp(-d * d * 5.5) * (1.0 - smoothstep(0.8, 1.0, d));
  gl_FragColor = vec4(vColor.rgb * a * vColor.a, 1.0);
}
`;
/** The quad is 1.25 radii across each way, so the ring has room for its soft edge. */
export const RING_PAD = 1.25;
export const RING_FRAG = /* glsl */ `
varying vec2 vUv;
varying vec4 vColor;
varying float vWidth;
void main() {
  float r = length(vUv) * ${RING_PAD.toFixed(2)};
  float off = abs(r - 1.0);
  float aa = fwidth(r) * 1.2;
  float line = 1.0 - smoothstep(vWidth * 0.5, vWidth * 0.5 + aa, off);
  float halo = exp(-off * off / (vWidth * vWidth * 18.0 + 0.0004)) * 0.35;
  gl_FragColor = vec4(vColor.rgb * (line + halo) * vColor.a, 1.0);
}
`;

// ---- sparks: GPU particles, a pure function of their life ---------------------------------------------
export const BURST_VERT = /* glsl */ `
attribute vec4 aSeed;
uniform vec3 uOrigin;
uniform float uT;
uniform float uSpread;
uniform float uPx;
varying float vFade;
void main() {
  vec3 dir = normalize(aSeed.xyz * 2.0 - 1.0);
  float speed = 0.25 + aSeed.w;
  float e = 1.0 - pow(1.0 - uT, 3.0);
  vec3 p = uOrigin + dir * speed * e * uSpread + vec3(0.0, -0.5 * uT * uT, 0.0);
  vec4 mv = viewMatrix * vec4(p, 1.0);
  gl_Position = projectionMatrix * mv;
  vFade = pow(1.0 - uT, 1.5) * step(0.0005, uT) * (0.4 + 0.6 * aSeed.w);
  gl_PointSize = max(1.0, uPx * 0.07 * (1.0 - uT * 0.7) * (0.4 + aSeed.w) / -mv.z);
}
`;
export const BURST_FRAG = /* glsl */ `
uniform vec3 uColor;
varying float vFade;
void main() {
  float d = length(gl_PointCoord - 0.5) * 2.0;
  float a = exp(-d * d * 4.0) * (1.0 - smoothstep(0.8, 1.0, d));
  gl_FragColor = vec4(mix(uColor, vec3(1.0), 0.35 * a) * a * vFade * 1.6, 1.0);
}
`;

// ---- wireframe lines that fade with distance (the corridor) ---------------------------------------------
export const WIRE_VERT = /* glsl */ `
attribute float aGlow;
uniform float uAlpha;
varying float vA;
void main() {
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  float dist = -mv.z;
  float fog = (1.0 - smoothstep(7.0, 30.0, dist)) * smoothstep(0.2, 1.6, dist);
  vA = uAlpha * aGlow * (0.12 + 0.88 * fog);
  gl_Position = projectionMatrix * mv;
}
`;
export const WIRE_FRAG = /* glsl */ `
uniform vec3 uColor;
varying float vA;
void main() {
  gl_FragColor = vec4(uColor * vA, 1.0);
}
`;

// ---- paper: a sheet with ruled lines, or a checklist row with a box and a bar ------------------------
export const SHEET_VERT = /* glsl */ `
attribute float iAlpha;
attribute float iRow;
attribute vec2 iSize;
varying vec2 vUv;
varying float vAlpha;
varying float vRow;
varying vec2 vSize;
void main() {
  vUv = uv;
  vAlpha = iAlpha;
  vRow = iRow;
  vSize = iSize;
  gl_Position = projectionMatrix * modelViewMatrix * instanceMatrix * vec4(position, 1.0);
}
`;
export const SHEET_FRAG = /* glsl */ `
uniform vec3 uColor;
uniform vec3 uTick;
varying vec2 vUv;
varying float vAlpha;
varying float vRow;
varying vec2 vSize;
float box(vec2 p, vec2 lo, vec2 hi) {
  vec2 s = step(lo, p) * step(p, hi);
  return s.x * s.y;
}
void main() {
  vec2 m = min(vUv, 1.0 - vUv) * vSize; // distance to the nearest edge, in world units
  float edge = min(m.x, m.y);
  float border = 1.0 - smoothstep(0.006, 0.014, edge);
  // paper: six ruled lines, the top one a short heading
  float lines = 0.0;
  for (int i = 0; i < 6; i++) {
    float y = 0.82 - float(i) * 0.12;
    float w = i == 0 ? 0.45 : (i == 5 ? 0.6 : 0.84);
    lines += box(vUv, vec2(0.12, y - 0.016), vec2(0.12 + w * 0.76, y + 0.016));
  }
  // row: a tick box on the left and one bar
  float h = vSize.y;
  vec2 w = vUv * vSize;
  float tick = box(w, vec2(h * 0.28, h * 0.28), vec2(h * 0.72, h * 0.72));
  float bar = box(w, vec2(h * 1.1, h * 0.38), vec2(vSize.x * 0.82, h * 0.62));
  float ink = mix(lines * 0.34, bar * 0.4, vRow);
  vec3 col = uColor * (border * 0.9 + ink + 0.045) + uTick * tick * vRow * 0.9;
  gl_FragColor = vec4(col * vAlpha, 1.0);
}
`;

// ---- the floor grid, which can bend toward the orb -------------------------------------------------------
export const FLOOR_VERT = /* glsl */ `
varying vec3 vWorld;
void main() {
  vec4 w = modelMatrix * vec4(position, 1.0);
  vWorld = w.xyz;
  gl_Position = projectionMatrix * viewMatrix * w;
}
`;
export const FLOOR_FRAG = /* glsl */ `
uniform float uAlpha;
uniform float uWarp;
uniform vec3 uCenter;
uniform vec3 uColor;
uniform vec3 uHot;
uniform vec3 uEye;
varying vec3 vWorld;
void main() {
  vec2 d = vWorld.xz - uCenter.xz;
  float r2 = dot(d, d);
  vec2 q = uCenter.xz + d * (1.0 + uWarp * 2.6 / (r2 + 0.9));
  vec2 g = abs(fract(q * 0.8 - 0.5) - 0.5) / fwidth(q * 0.8);
  float line = 1.0 - min(min(g.x, g.y), 1.0);
  float dist = length(vWorld - uEye);
  float fade = exp(-dist * 0.085) * smoothstep(0.5, 2.5, dist);
  float well = uWarp * exp(-r2 * 0.12);
  vec3 col = mix(uColor, uHot, clamp(well, 0.0, 1.0) * 0.8);
  gl_FragColor = vec4(col * line * fade * uAlpha * (1.0 + well), 1.0);
}
`;

// ---- dust: a few still points for depth ---------------------------------------------------------------------
export const DUST_VERT = /* glsl */ `
attribute float aSize;
uniform float uPx;
varying float vA;
void main() {
  vec4 mv = viewMatrix * vec4(position, 1.0);
  gl_Position = projectionMatrix * mv;
  float dist = -mv.z;
  vA = (1.0 - smoothstep(10.0, 28.0, dist)) * smoothstep(0.5, 2.5, dist);
  gl_PointSize = max(1.0, uPx * 0.022 * aSize / dist);
}
`;
export const DUST_FRAG = /* glsl */ `
uniform float uAlpha;
uniform vec3 uColor;
varying float vA;
void main() {
  float d = length(gl_PointCoord - 0.5) * 2.0;
  gl_FragColor = vec4(uColor * (1.0 - smoothstep(0.3, 1.0, d)) * vA * uAlpha, 1.0);
}
`;

// ---- last pass: lens fringe, vignette, grain ---------------------------------------------------------------
export const FINAL_SHADER = {
  uniforms: {
    tDiffuse: { value: null },
    uFringe: { value: 0.0015 },
    uTime: { value: 0 },
    uGrain: { value: 0.035 },
    uCenter: { value: [0.5, 0.5] },
  },
  vertexShader: /* glsl */ `
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`,
  fragmentShader: /* glsl */ `
uniform sampler2D tDiffuse;
uniform float uFringe;
uniform float uTime;
uniform float uGrain;
uniform vec2 uCenter;
varying vec2 vUv;
float hash21(vec2 p) {
  vec3 q = fract(vec3(p.xyx) * 0.1031);
  q += dot(q, q.yzx + 33.33);
  return fract((q.x + q.y) * q.z);
}
void main() {
  vec2 d = vUv - uCenter;
  float r2 = dot(d, d);
  vec2 shift = d * uFringe * (1.0 + r2 * 5.0);
  vec3 col = vec3(texture2D(tDiffuse, vUv + shift).r, texture2D(tDiffuse, vUv).g, texture2D(tDiffuse, vUv - shift).b);
  vec2 e = vUv - 0.5;
  col *= 1.0 - smoothstep(0.35, 1.05, length(e) * 1.25) * 0.65;
  float n = hash21(gl_FragCoord.xy + fract(uTime) * 61.0) - 0.5;
  col += n * uGrain * (0.4 + 0.6 * (1.0 - clamp(dot(col, vec3(0.333)), 0.0, 1.0)));
  gl_FragColor = vec4(clamp(col, 0.0, 1.0), 1.0);
}
`,
};
