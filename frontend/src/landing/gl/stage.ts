// The WebGL stage. It owns the renderer and the objects and draws one Frame from the director.
// It keeps no story state: every call to render() is the whole picture for one playhead position.
import * as THREE from "three";
import { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js";
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js";
import { RenderPass } from "three/examples/jsm/postprocessing/RenderPass.js";
import { ShaderPass } from "three/examples/jsm/postprocessing/ShaderPass.js";
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js";
import { tone, TOKENS } from "../tokens";
import { FLOOR_Y, SHEET_COUNT, SHEET_SIZE, TITLE_Z, type AnchorId, type CoreState, type Frame, type Glow, type Ring } from "./director";
import { buildJourney, type Journey } from "./journey";
import * as S from "./shaders";
import { hash } from "./vec";

/** Quality levels, best first. The stage only ever steps down (quality.ts decides when). */
export const LEVELS = [
  { name: "full", pixelRatio: 1.5, bloom: 1, samples: 4, post: true, sparks: 1 },
  { name: "high", pixelRatio: 1, bloom: 1, samples: 2, post: true, sparks: 1 },
  { name: "medium", pixelRatio: 1, bloom: 0.5, samples: 0, post: true, sparks: 0.5 },
  { name: "low", pixelRatio: 0.75, bloom: 0, samples: 0, post: false, sparks: 0.35 },
] as const;
export const TOP_LEVEL = 0;
export const LOWEST_LEVEL = LEVELS.length - 1;

export interface ScreenPoint {
  x: number;
  y: number;
  a: number;
}
export interface Stage {
  resize(width: number, height: number, devicePixelRatio: number): void;
  render(frame: Frame, time: number): void;
  /** Where the page should pin its labels, in CSS pixels of the stage. */
  anchors(frame: Frame): Record<AnchorId, ScreenPoint>;
  setLevel(level: number): void;
  readonly level: number;
  dispose(): void;
}

const MAX_GLOWS = 24;
const MAX_RINGS = 20;
const MAX_BURSTS = 5;
const BURST_POINTS = 110;

const additive = { transparent: true, blending: THREE.AdditiveBlending, depthWrite: false } as const;
const v3 = (c: readonly [number, number, number]) => new THREE.Vector3(c[0], c[1], c[2]);

function makeCore(color: readonly [number, number, number]): THREE.Mesh<THREE.SphereGeometry, THREE.ShaderMaterial> {
  const material = new THREE.ShaderMaterial({
    vertexShader: S.CORE_VERT,
    fragmentShader: S.CORE_FRAG,
    uniforms: { uTime: { value: 0 }, uPower: { value: 1 }, uColor: { value: v3(color) } },
  });
  return new THREE.Mesh(new THREE.SphereGeometry(0.42, 48, 32), material);
}

/** A closed loop of line segments from 2D points in the plane x = 0. */
function loopSegments(points: [number, number][]): number[] {
  const out: number[] = [];
  points.forEach(([y, z], i) => {
    const [y2, z2] = points[(i + 1) % points.length]!;
    out.push(0, y, z, 0, y2, z2);
  });
  return out;
}

function roundedRect(half: number, radius: number, steps = 6): [number, number][] {
  const pts: [number, number][] = [];
  const corners: [number, number, number][] = [
    [half - radius, half - radius, 0],
    [-(half - radius), half - radius, Math.PI / 2],
    [-(half - radius), -(half - radius), Math.PI],
    [half - radius, -(half - radius), Math.PI * 1.5],
  ];
  for (const [cx, cy, start] of corners) {
    for (let i = 0; i <= steps; i++) {
      const a = start + (i / steps) * (Math.PI / 2);
      pts.push([cx + Math.cos(a) * radius, cy + Math.sin(a) * radius]);
    }
  }
  return pts;
}

/** One half of the glass module: a rounded cell with a bright seam where it meets the other half. */
function makeGlassHalf(side: -1 | 1, tint: readonly [number, number, number]) {
  const group = new THREE.Group();
  const material = new THREE.ShaderMaterial({
    vertexShader: S.GLASS_VERT,
    fragmentShader: S.GLASS_FRAG,
    uniforms: { uAlpha: { value: 1 }, uTint: { value: v3(tint) } },
    side: THREE.DoubleSide,
    ...additive,
  });
  const shell = new THREE.Mesh(new RoundedBoxGeometry(1.34, 1.3, 1.3, 5, 0.24), material);
  const seamGeometry = new THREE.BufferGeometry();
  const loop = loopSegments(roundedRect(0.65, 0.24));
  const far = loop.map((v, i) => (i % 3 === 0 ? side * 0.62 : v * 0.8)); // a smaller loop on the outer end cap
  const near = loop.map((v, i) => (i % 3 === 0 ? -side * 0.67 : v));
  seamGeometry.setAttribute("position", new THREE.Float32BufferAttribute([...near, ...far], 3));
  const seamMaterial = new THREE.LineBasicMaterial({ color: new THREE.Color().setRGB(0.8, 0.86, 0.94), ...additive });
  const seam = new THREE.LineSegments(seamGeometry, seamMaterial);
  group.add(shell, seam);
  return { group, material, seamMaterial, side };
}

/** The queue corridor of scene 1 as one set of line segments: frames, floor, posts and ropes, people, counters. */
function makeCorridor(): THREE.LineSegments<THREE.BufferGeometry, THREE.ShaderMaterial> {
  const pos: number[] = [];
  const glow: number[] = [];
  const line = (a: number[], b: number[], g: number) => {
    pos.push(...a, ...b);
    glow.push(g, g);
  };
  const [X, FLOOR, TOP] = [1.9, -1.1, 1.5];
  for (let z = 40; z >= 4; z -= 3) {
    line([-X, FLOOR, z], [X, FLOOR, z], 0.9);
    line([X, FLOOR, z], [X, TOP, z], 0.9);
    line([X, TOP, z], [-X, TOP, z], 0.9);
    line([-X, TOP, z], [-X, FLOOR, z], 0.9);
  }
  for (const x of [-X, X]) {
    line([x, FLOOR, 42], [x, FLOOR, 2], 0.7);
    line([x, TOP, 42], [x, TOP, 2], 0.7);
  }
  for (let z = 41; z >= 3; z -= 1) line([-X, FLOOR, z], [X, FLOOR, z], 0.22);
  for (const x of [-0.63, 0.63]) line([x, FLOOR, 42], [x, FLOOR, 2], 0.22);
  // the queue lane on the left: posts with sagging ropes
  for (const x of [-1.5, -0.55]) {
    for (let z = 39; z >= 6; z -= 3) {
      line([x, FLOOR, z], [x, -0.3, z], 0.8);
      line([x - 0.06, -0.3, z], [x + 0.06, -0.3, z], 0.8);
      if (z > 6) {
        for (let i = 0; i < 6; i++) {
          const [t0, t1] = [i / 6, (i + 1) / 6];
          const sag = (t: number) => -0.34 - 0.16 * Math.sin(t * Math.PI);
          line([x, sag(t0), z - 3 * t0], [x, sag(t1), z - 3 * t1], 0.55);
        }
      }
    }
  }
  // people waiting: an outline of a head and shoulders, nobody in particular
  for (let i = 0; i < 12; i++) {
    const z = 38.4 - i * 2.75;
    const x = -1.02 + (hash(i, 21) - 0.5) * 0.3;
    const tall = 0.92 + hash(i, 22) * 0.16;
    const y = (v: number) => FLOOR + (v - FLOOR) * tall;
    const head: [number, number][] = Array.from({ length: 10 }, (_, k) => {
      const a = (k / 10) * Math.PI * 2;
      return [x + Math.cos(a) * 0.12, y(0.02) + Math.sin(a) * 0.14];
    });
    head.forEach(([hx, hy], k) => {
      const [nx, ny] = head[(k + 1) % head.length]!;
      line([hx, hy, z], [nx, ny, z], 0.6);
    });
    const body: [number, number][] = [
      [x - 0.2, y(-0.34)],
      [x - 0.1, y(-0.18)],
      [x + 0.1, y(-0.18)],
      [x + 0.2, y(-0.34)],
      [x + 0.17, FLOOR],
      [x - 0.17, FLOOR],
    ];
    body.forEach(([bx, by], k) => {
      const [nx, ny] = body[(k + 1) % body.length]!;
      line([bx, by, z], [nx, ny, z], 0.6);
    });
  }
  // counters on the right wall: a window and a ledge
  for (let z = 38.2; z >= 6; z -= 3) {
    const [z0, z1] = [z, z - 1.6];
    line([X, 0.55, z0], [X, 0.55, z1], 0.7);
    line([X, -0.35, z0], [X, -0.35, z1], 0.7);
    line([X, 0.55, z0], [X, -0.35, z0], 0.7);
    line([X, 0.55, z1], [X, -0.35, z1], 0.7);
    line([X - 0.28, -0.35, z0], [X - 0.28, -0.35, z1], 0.5);
    line([X - 0.28, -0.35, z0], [X, -0.35, z0], 0.5);
    line([X - 0.28, -0.35, z1], [X, -0.35, z1], 0.5);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  geometry.setAttribute("aGlow", new THREE.Float32BufferAttribute(glow, 1));
  const material = new THREE.ShaderMaterial({
    vertexShader: S.WIRE_VERT,
    fragmentShader: S.WIRE_FRAG,
    uniforms: { uAlpha: { value: 0 }, uColor: { value: v3(tone("text")) } },
    ...additive,
  });
  const lines = new THREE.LineSegments(geometry, material);
  lines.frustumCulled = false;
  return lines;
}

/** A pool of camera-facing quads drawn in one call: soft glows or thin rings. */
function makeBillboards(max: number, fragmentShader: string) {
  const geometry = new THREE.InstancedBufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute([-0.5, -0.5, 0, 0.5, -0.5, 0, 0.5, 0.5, 0, -0.5, 0.5, 0], 3));
  geometry.setIndex([0, 1, 2, 0, 2, 3]);
  const pos = new THREE.InstancedBufferAttribute(new Float32Array(max * 3), 3);
  const size = new THREE.InstancedBufferAttribute(new Float32Array(max), 1);
  const color = new THREE.InstancedBufferAttribute(new Float32Array(max * 4), 4);
  const width = new THREE.InstancedBufferAttribute(new Float32Array(max), 1);
  for (const a of [pos, size, color, width]) a.setUsage(THREE.DynamicDrawUsage);
  geometry.setAttribute("iPos", pos);
  geometry.setAttribute("iSize", size);
  geometry.setAttribute("iColor", color);
  geometry.setAttribute("iWidth", width);
  const material = new THREE.ShaderMaterial({ vertexShader: S.BILLBOARD_VERT, fragmentShader, depthTest: false, ...additive });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.frustumCulled = false;
  mesh.renderOrder = 5;
  return {
    mesh,
    set(items: { p: readonly number[]; size: number; color: readonly number[]; a: number; width?: number }[]) {
      let n = 0;
      for (const item of items) {
        if (n >= max || item.a <= 0.002 || item.size <= 0) continue;
        pos.setXYZ(n, item.p[0]!, item.p[1]!, item.p[2]!);
        size.setX(n, item.size);
        color.setXYZW(n, item.color[0]!, item.color[1]!, item.color[2]!, item.a);
        width.setX(n, item.width ?? 0);
        n++;
      }
      geometry.instanceCount = n;
      pos.needsUpdate = size.needsUpdate = color.needsUpdate = width.needsUpdate = true;
      mesh.visible = n > 0;
    },
  };
}

export function createStage(canvas: HTMLCanvasElement): Stage {
  THREE.ColorManagement.enabled = false; // shader colours are the token colours, as written
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: false, alpha: false, powerPreference: "high-performance" });
  renderer.outputColorSpace = THREE.LinearSRGBColorSpace;
  renderer.setClearColor(new THREE.Color(TOKENS.stage), 1);
  renderer.autoClear = true;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 120);
  const size = { w: 1, h: 1, dpr: 1 };
  let level: number = TOP_LEVEL;

  // -- objects ---------------------------------------------------------------------------------------------
  const cyan = makeCore(tone("accent"));
  const orange = makeCore(tone("neon"));
  const halves = [makeGlassHalf(-1, tone("accent")), makeGlassHalf(1, tone("neon"))];
  const glass = new THREE.Group();
  glass.add(halves[0]!.group, halves[1]!.group);
  const corridor = makeCorridor();

  const sheetGeometry = new THREE.PlaneGeometry(SHEET_SIZE[0], SHEET_SIZE[1]);
  const sheetAlpha = new THREE.InstancedBufferAttribute(new Float32Array(SHEET_COUNT), 1);
  const sheetRow = new THREE.InstancedBufferAttribute(new Float32Array(SHEET_COUNT), 1);
  const sheetSize = new THREE.InstancedBufferAttribute(new Float32Array(SHEET_COUNT * 2), 2);
  for (const a of [sheetAlpha, sheetRow, sheetSize]) a.setUsage(THREE.DynamicDrawUsage);
  sheetGeometry.setAttribute("iAlpha", sheetAlpha);
  sheetGeometry.setAttribute("iRow", sheetRow);
  sheetGeometry.setAttribute("iSize", sheetSize);
  const sheets = new THREE.InstancedMesh(
    sheetGeometry,
    new THREE.ShaderMaterial({
      vertexShader: S.SHEET_VERT,
      fragmentShader: S.SHEET_FRAG,
      uniforms: { uColor: { value: v3(tone("text")) }, uTick: { value: v3(tone("accent")) } },
      side: THREE.DoubleSide,
      ...additive,
    }),
    SHEET_COUNT,
  );
  sheets.frustumCulled = false;
  sheets.instanceMatrix.setUsage(THREE.DynamicDrawUsage);

  const floor = new THREE.Mesh(
    new THREE.PlaneGeometry(140, 140),
    new THREE.ShaderMaterial({
      vertexShader: S.FLOOR_VERT,
      fragmentShader: S.FLOOR_FRAG,
      uniforms: {
        uAlpha: { value: 0 },
        uWarp: { value: 0 },
        uCenter: { value: new THREE.Vector3() },
        uColor: { value: v3(tone("idle")) },
        uHot: { value: v3(tone("neon")) },
        uEye: { value: new THREE.Vector3() },
      },
      ...additive,
    }),
  );
  floor.rotation.x = -Math.PI / 2;
  floor.position.set(3.5, FLOOR_Y, -2);

  const dustGeometry = new THREE.BufferGeometry();
  const DUST = 320;
  const dustPos = new Float32Array(DUST * 3);
  const dustSize = new Float32Array(DUST);
  for (let i = 0; i < DUST; i++) {
    dustPos[i * 3] = -9 + hash(i, 31) * 25;
    dustPos[i * 3 + 1] = -1.2 + hash(i, 32) * 4.4;
    dustPos[i * 3 + 2] = -14 + hash(i, 33) * (TITLE_Z + 24);
    dustSize[i] = 0.5 + hash(i, 34);
  }
  dustGeometry.setAttribute("position", new THREE.BufferAttribute(dustPos, 3));
  dustGeometry.setAttribute("aSize", new THREE.BufferAttribute(dustSize, 1));
  const dust = new THREE.Points(
    dustGeometry,
    new THREE.ShaderMaterial({
      vertexShader: S.DUST_VERT,
      fragmentShader: S.DUST_FRAG,
      uniforms: { uAlpha: { value: 0 }, uPx: { value: 1 }, uColor: { value: v3(tone("muted")) } },
      ...additive,
    }),
  );
  dust.frustumCulled = false;

  const glows = makeBillboards(MAX_GLOWS, S.GLOW_FRAG);
  const rings = makeBillboards(MAX_RINGS, S.RING_FRAG);

  const burstGeometry = new THREE.BufferGeometry();
  const seeds = new Float32Array(BURST_POINTS * 4);
  for (let i = 0; i < seeds.length; i++) seeds[i] = hash(i, 41);
  burstGeometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array(BURST_POINTS * 3), 3));
  burstGeometry.setAttribute("aSeed", new THREE.BufferAttribute(seeds, 4));
  const bursts = Array.from({ length: MAX_BURSTS }, () => {
    const points = new THREE.Points(
      burstGeometry,
      new THREE.ShaderMaterial({
        vertexShader: S.BURST_VERT,
        fragmentShader: S.BURST_FRAG,
        uniforms: { uOrigin: { value: new THREE.Vector3() }, uT: { value: 0 }, uSpread: { value: 1 }, uPx: { value: 1 }, uColor: { value: new THREE.Vector3() } },
        depthTest: false,
        ...additive,
      }),
    );
    points.frustumCulled = false;
    points.visible = false;
    return points;
  });

  const journey: Journey = buildJourney();

  scene.add(floor, dust, corridor, sheets, cyan, orange, glass, journey.group, glows.mesh, rings.mesh, ...bursts);

  // -- post chain ---------------------------------------------------------------------------------------------
  let composer: EffectComposer | null = null;
  let bloom: UnrealBloomPass | null = null;
  let final: ShaderPass | null = null;

  function buildComposer() {
    composer?.dispose();
    composer = null;
    const spec = LEVELS[level]!;
    if (!spec.post) return;
    const target = new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType, samples: spec.samples });
    composer = new EffectComposer(renderer, target);
    composer.addPass(new RenderPass(scene, camera));
    bloom = new UnrealBloomPass(new THREE.Vector2(256, 256), 0.6, 0.5, 0.22);
    composer.addPass(bloom);
    final = new ShaderPass(S.FINAL_SHADER);
    composer.addPass(final);
  }

  function applySize() {
    const spec = LEVELS[level]!;
    const ratio = Math.min(size.dpr, spec.pixelRatio);
    renderer.setPixelRatio(ratio);
    renderer.setSize(size.w, size.h, false);
    if (composer) {
      composer.setPixelRatio(ratio);
      composer.setSize(size.w, size.h);
      bloom?.setSize(size.w * ratio * spec.bloom, size.h * ratio * spec.bloom);
    }
    camera.aspect = size.w / size.h;
  }

  buildComposer();

  const matrix = new THREE.Matrix4();
  const quat = new THREE.Quaternion();
  const position = new THREE.Vector3();
  const scaling = new THREE.Vector3();
  const projected = new THREE.Vector3();

  function placeCore(mesh: typeof cyan, state: CoreState, time: number) {
    mesh.visible = state.scale > 0.005 && state.power > 0.01;
    mesh.position.set(state.p[0], state.p[1], state.p[2]);
    mesh.scale.setScalar(Math.max(0.001, state.scale));
    mesh.rotation.y = time * 0.15;
    mesh.material.uniforms.uTime!.value = time;
    mesh.material.uniforms.uPower!.value = state.power;
  }

  function setCamera(frame: Frame) {
    camera.fov = frame.cam.fov;
    camera.position.set(frame.cam.p[0], frame.cam.p[1], frame.cam.p[2]);
    camera.up.set(0, 1, 0);
    camera.lookAt(frame.cam.look[0], frame.cam.look[1], frame.cam.look[2]);
    // shift the picture so the subject sits where the page layout wants it
    camera.setViewOffset(size.w, size.h, (0.5 - frame.subject.x) * size.w, (0.5 - frame.subject.y) * size.h, size.w, size.h);
    camera.updateMatrixWorld();
  }

  return {
    get level() {
      return level;
    },
    setLevel(next: number) {
      const clamped = Math.min(LOWEST_LEVEL, Math.max(TOP_LEVEL, next));
      if (clamped === level) return;
      level = clamped;
      buildComposer();
      applySize();
    },
    resize(width: number, height: number, devicePixelRatio: number) {
      size.w = Math.max(1, Math.round(width));
      size.h = Math.max(1, Math.round(height));
      size.dpr = devicePixelRatio;
      applySize();
    },
    anchors(frame: Frame) {
      const out = {} as Record<AnchorId, ScreenPoint>;
      for (const [id, anchor] of Object.entries(frame.anchors) as [AnchorId, Frame["anchors"][AnchorId]][]) {
        projected.set(anchor.p[0], anchor.p[1], anchor.p[2]).project(camera);
        const visible = projected.z < 1 && Math.abs(projected.x) < 1.3 && Math.abs(projected.y) < 1.3;
        out[id] = { x: (projected.x * 0.5 + 0.5) * size.w, y: (0.5 - projected.y * 0.5) * size.h, a: visible ? anchor.a : 0 };
      }
      return out;
    },
    render(frame: Frame, time: number) {
      const spec = LEVELS[level]!;
      setCamera(frame);
      const px = (size.h * Math.min(size.dpr, spec.pixelRatio)) / (2 * Math.tan((frame.cam.fov * Math.PI) / 360));

      placeCore(cyan, frame.cyan, time);
      placeCore(orange, frame.orange, time + 40);

      glass.visible = frame.glass.a > 0.003;
      glass.position.set(frame.glass.p[0], frame.glass.p[1], frame.glass.p[2]);
      for (const half of halves) {
        half.group.position.x = half.side * (0.69 + frame.glass.open);
        half.group.rotation.y = -half.side * Math.min(0.5, frame.glass.open * 0.4);
        half.material.uniforms.uAlpha!.value = frame.glass.a;
        half.seamMaterial.opacity = frame.glass.a * 0.55;
      }

      corridor.visible = frame.corridor.a > 0.003;
      corridor.material.uniforms.uAlpha!.value = frame.corridor.a * 0.8;

      let shown = 0;
      frame.sheets.forEach((sheet, i) => {
        if (sheet.a > 0.003) shown++;
        position.set(sheet.p[0], sheet.p[1], sheet.p[2]);
        quat.set(sheet.q[0], sheet.q[1], sheet.q[2], sheet.q[3]);
        scaling.set(Math.max(1e-4, sheet.sx), Math.max(1e-4, sheet.sy), 1);
        sheets.setMatrixAt(i, matrix.compose(position, quat, scaling));
        sheetAlpha.setX(i, sheet.a);
        sheetRow.setX(i, sheet.row);
        sheetSize.setXY(i, sheet.sx * SHEET_SIZE[0], sheet.sy * SHEET_SIZE[1]);
      });
      sheets.visible = shown > 0;
      if (shown > 0) sheets.instanceMatrix.needsUpdate = sheetAlpha.needsUpdate = sheetRow.needsUpdate = sheetSize.needsUpdate = true;

      const fu = floor.material.uniforms;
      floor.visible = frame.floor.a > 0.003;
      fu.uAlpha!.value = frame.floor.a;
      fu.uWarp!.value = frame.floor.warp;
      (fu.uCenter!.value as THREE.Vector3).set(frame.floor.center[0], frame.floor.center[1], frame.floor.center[2]);
      (fu.uEye!.value as THREE.Vector3).copy(camera.position);

      dust.visible = frame.dust.a > 0.003;
      dust.material.uniforms.uAlpha!.value = frame.dust.a;
      dust.material.uniforms.uPx!.value = px;

      journey.update(frame, time, camera, px);

      glows.set(frame.glows.map((g: Glow) => ({ p: g.p, size: g.size, color: g.color, a: g.a })));
      rings.set(frame.rings.map((r: Ring) => ({ p: r.p, size: r.radius * 2 * S.RING_PAD, color: r.color, a: r.a, width: r.width })));

      bursts.forEach((points, i) => {
        const burst = frame.bursts[i];
        const on = !!burst && burst.t > 0 && burst.t < 1;
        points.visible = on;
        if (!on) return;
        const bu = points.material.uniforms;
        (bu.uOrigin!.value as THREE.Vector3).set(burst.p[0], burst.p[1], burst.p[2]);
        bu.uT!.value = burst.t;
        bu.uSpread!.value = burst.spread;
        bu.uPx!.value = px;
        (bu.uColor!.value as THREE.Vector3).set(burst.color[0], burst.color[1], burst.color[2]);
        points.geometry.setDrawRange(0, Math.floor(BURST_POINTS * spec.sparks));
      });

      if (composer && final) {
        final.uniforms.uFringe!.value = frame.fringe;
        final.uniforms.uTime!.value = time;
        composer.render();
      } else {
        renderer.render(scene, camera);
      }
    },
    dispose() {
      composer?.dispose();
      scene.traverse((object) => {
        const mesh = object as THREE.Mesh;
        mesh.geometry?.dispose();
        const material = mesh.material as THREE.Material | THREE.Material[] | undefined;
        if (Array.isArray(material)) material.forEach((m) => m.dispose());
        else material?.dispose();
      });
      renderer.dispose();
    },
  };
}
