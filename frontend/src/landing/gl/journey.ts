// The objects of the two journeys (scenes 3 to 8): constellations, beams, orb, clock ring, thread.
// They are built here and added to the stage as one group, so the stage file stays about the scaffold.
import * as THREE from "three";
import { Line2 } from "three/examples/jsm/lines/Line2.js";
import { LineGeometry } from "three/examples/jsm/lines/LineGeometry.js";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";
import { tone } from "../tokens";
import { STARS, TARGET_STAR, THREAD_STOPS, threadPath, type Frame } from "./director";
import * as S from "./journeyShaders";
import { distance, hash } from "./vec";

export interface Journey {
  group: THREE.Group;
  update(frame: Frame, time: number, camera: THREE.PerspectiveCamera, px: number, detail: boolean): void;
  resize(width: number, height: number): void;
}

const additive = { transparent: true, blending: THREE.AdditiveBlending, depthWrite: false } as const;
const v3 = (c: readonly [number, number, number]) => new THREE.Vector3(c[0], c[1], c[2]);

/** The 40 service points and the faint lines that make each office a constellation. */
function makeStars() {
  const uniforms = {
    uAlpha: { value: 0 },
    uCollapse: { value: 0 },
    uLit: { value: 0 },
    uSqueeze: { value: 1 },
    uPx: { value: 1 },
    uTime: { value: 0 },
    uColor: { value: v3(tone("accent")) },
  };
  const pos: number[] = [];
  const seed: number[] = [];
  const target: number[] = [];
  STARS.forEach((star, i) => {
    pos.push(...star.p);
    seed.push(hash(i, 51));
    target.push(i === TARGET_STAR ? 1 : 0);
  });
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  geometry.setAttribute("aSeed", new THREE.Float32BufferAttribute(seed, 1));
  geometry.setAttribute("aTarget", new THREE.Float32BufferAttribute(target, 1));
  const points = new THREE.Points(geometry, new THREE.ShaderMaterial({ vertexShader: S.STAR_VERT, fragmentShader: S.STAR_FRAG, uniforms, depthTest: false, ...additive }));

  // each point is joined to its two nearest neighbours in the same office
  const linkPos: number[] = [];
  const linkSeed: number[] = [];
  const linkTarget: number[] = [];
  const seen = new Set<string>();
  STARS.forEach((star, i) => {
    const near = STARS.map((other, j) => ({ j, d: other.cluster === star.cluster && j !== i ? distance(star.p, other.p) : Infinity }))
      .sort((a, b) => a.d - b.d)
      .slice(0, 2);
    for (const { j, d } of near) {
      const key = i < j ? `${i}-${j}` : `${j}-${i}`;
      if (!Number.isFinite(d) || seen.has(key)) continue;
      seen.add(key);
      linkPos.push(...star.p, ...STARS[j]!.p);
      linkSeed.push(hash(i, 51), hash(j, 51));
      linkTarget.push(0, 0);
    }
  });
  const linkGeometry = new THREE.BufferGeometry();
  linkGeometry.setAttribute("position", new THREE.Float32BufferAttribute(linkPos, 3));
  linkGeometry.setAttribute("aSeed", new THREE.Float32BufferAttribute(linkSeed, 1));
  linkGeometry.setAttribute("aTarget", new THREE.Float32BufferAttribute(linkTarget, 1));
  const links = new THREE.LineSegments(linkGeometry, new THREE.ShaderMaterial({ vertexShader: S.STAR_VERT, fragmentShader: S.LINK_FRAG, uniforms, depthTest: false, ...additive }));
  points.frustumCulled = links.frustumCulled = false;
  return { points, links, uniforms };
}

/** Four beams of light from Core 1 to the offices: thin cones that always face the camera. */
function makeBeams() {
  const COUNT = 4;
  const position = new THREE.BufferAttribute(new Float32Array(COUNT * 9), 3);
  const shade = new THREE.BufferAttribute(new Float32Array(COUNT * 9), 3); // across (-1..1), along (0..1), alpha
  position.setUsage(THREE.DynamicDrawUsage);
  shade.setUsage(THREE.DynamicDrawUsage);
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", position);
  geometry.setAttribute("aShade", shade);
  const mesh = new THREE.Mesh(
    geometry,
    new THREE.ShaderMaterial({
      vertexShader: S.BEAM_VERT,
      fragmentShader: S.BEAM_FRAG,
      uniforms: { uColor: { value: v3(tone("accent")) } },
      side: THREE.DoubleSide,
      depthTest: false,
      ...additive,
    }),
  );
  mesh.frustumCulled = false;
  const from = new THREE.Vector3();
  const tip = new THREE.Vector3();
  const axis = new THREE.Vector3();
  const side = new THREE.Vector3();
  const view = new THREE.Vector3();
  return {
    mesh,
    update(frame: Frame, camera: THREE.PerspectiveCamera) {
      let any = false;
      frame.beams.forEach((beam, i) => {
        const on = beam.a > 0.003 && beam.grow > 0.001;
        any ||= on;
        from.set(beam.from[0], beam.from[1], beam.from[2]);
        tip.set(beam.to[0], beam.to[1], beam.to[2]).sub(from).multiplyScalar(on ? beam.grow : 0).add(from);
        axis.copy(tip).sub(from);
        view.copy(camera.position).sub(tip);
        side.crossVectors(axis, view).normalize().multiplyScalar(beam.width * beam.grow);
        const o = i * 3;
        position.setXYZ(o, from.x, from.y, from.z);
        position.setXYZ(o + 1, tip.x + side.x, tip.y + side.y, tip.z + side.z);
        position.setXYZ(o + 2, tip.x - side.x, tip.y - side.y, tip.z - side.z);
        const a = on ? beam.a : 0;
        shade.setXYZ(o, 0, 0, a);
        shade.setXYZ(o + 1, 1, 1, a);
        shade.setXYZ(o + 2, -1, 1, a);
      });
      mesh.visible = any;
      position.needsUpdate = shade.needsUpdate = true;
    },
  };
}

/** A camera-facing quad with its own shader: the orb and the clock ring. */
function makeDisc(fragmentShader: string, uniforms: Record<string, THREE.IUniform>, blending: Partial<THREE.ShaderMaterialParameters>) {
  const mesh = new THREE.Mesh(
    new THREE.PlaneGeometry(1, 1),
    new THREE.ShaderMaterial({
      vertexShader: S.ORB_VERT,
      fragmentShader,
      uniforms: { uCenter: { value: new THREE.Vector3() }, uSize: { value: 1 }, uAlpha: { value: 0 }, ...uniforms },
      transparent: true,
      depthWrite: false,
      depthTest: false,
      ...blending,
    }),
  );
  mesh.frustumCulled = false;
  return mesh;
}

/** The thread of one request: a faint planned path, and the bright part that has been walked so far. */
function makeThread() {
  const orange = tone("neon");
  const grey = tone("idle");
  const material = new LineMaterial({ linewidth: 3, vertexColors: true, depthTest: false, ...additive });
  const ghostMaterial = new LineMaterial({ linewidth: 1, color: new THREE.Color().setRGB(grey[0], grey[1], grey[2]), dashed: false, depthTest: false, ...additive });
  const geometry = new LineGeometry();
  const ghostGeometry = new LineGeometry();
  const line = new Line2(geometry, material);
  const ghost = new Line2(ghostGeometry, ghostMaterial);
  line.frustumCulled = ghost.frustumCulled = false;
  let builtFor = -1;
  let count = 0;
  let colors = new Float32Array(0);
  let shade = "";
  return {
    line,
    ghost,
    resize(width: number, height: number) {
      material.resolution.set(width, height);
      ghostMaterial.resolution.set(width, height);
    },
    update(frame: Frame, aspect: number) {
      const on = frame.thread.a > 0.003;
      line.visible = ghost.visible = on;
      if (!on) return;
      if (builtFor !== frame.stars.squeeze) {
        builtFor = frame.stars.squeeze;
        const flat = threadPath(aspect).flat();
        count = flat.length / 3;
        geometry.setPositions(flat);
        ghostGeometry.setPositions(flat);
        colors = new Float32Array(count * 3);
        shade = "";
      }
      // colours: orange where the office is working, grey while another agency has it, hot once it is late
      const key = `${frame.thread.grey.toFixed(2)}-${frame.thread.late.toFixed(2)}`;
      if (key !== shade) {
        shade = key;
        for (let i = 0; i < count; i++) {
          const s = i / (count - 1);
          const outside = s > THREAD_STOPS.steps[1] && s <= THREAD_STOPS.steps[2] ? frame.thread.grey : 0;
          const late = s > THREAD_STOPS.deadline ? frame.thread.late : 0;
          for (let c = 0; c < 3; c++) {
            const base = orange[c]! * 0.85 * (1 - outside) + grey[c]! * 0.8 * outside;
            colors[i * 3 + c] = base * (1 - late) + (orange[c]! * 1.2 + 0.5) * late;
          }
        }
        geometry.setColors(colors);
      }
      geometry.instanceCount = Math.max(0, Math.round(frame.thread.draw * (count - 1)));
      material.opacity = frame.thread.a;
      ghostMaterial.opacity = frame.thread.a * 0.35;
    },
  };
}

export function buildJourney(): Journey {
  const group = new THREE.Group();
  const stars = makeStars();
  const beams = makeBeams();
  const orb = makeDisc(
    S.ORB_FRAG,
    { uTime: { value: 0 }, uDetail: { value: 1 }, uHot: { value: v3(tone("neon")) } },
    // premultiplied: the glow adds light, the black disc hides what is behind it
    { blending: THREE.CustomBlending, blendSrc: THREE.OneFactor, blendDst: THREE.OneMinusSrcAlphaFactor },
  );
  const clock = makeDisc(S.CLOCK_FRAG, { uTicks: { value: 0 }, uHand: { value: 0 }, uHot: { value: v3(tone("neon")) } }, { blending: THREE.AdditiveBlending });
  const thread = makeThread();
  orb.renderOrder = 3;
  group.add(beams.mesh, stars.links, stars.points, orb, clock, thread.ghost, thread.line);
  return {
    group,
    update(frame, time, camera, px, detail) {
      const su = stars.uniforms;
      stars.points.visible = stars.links.visible = frame.stars.a > 0.003;
      su.uAlpha.value = frame.stars.a;
      su.uCollapse.value = frame.stars.collapse;
      su.uLit.value = frame.stars.lit;
      su.uSqueeze.value = frame.stars.squeeze;
      su.uPx.value = px;
      su.uTime.value = time;
      beams.update(frame, camera);

      const ou = orb.material.uniforms;
      orb.visible = frame.orb.a > 0.003 && frame.orb.size > 0.003;
      (ou.uCenter!.value as THREE.Vector3).set(frame.orb.p[0], frame.orb.p[1], frame.orb.p[2]);
      ou.uSize!.value = frame.orb.size * 5.4;
      ou.uAlpha!.value = frame.orb.a;
      ou.uTime!.value = time;
      ou.uDetail!.value = detail ? 1 : 0;

      const cu = clock.material.uniforms;
      clock.visible = frame.clock.a > 0.003;
      (cu.uCenter!.value as THREE.Vector3).set(frame.clock.p[0], frame.clock.p[1], frame.clock.p[2]);
      cu.uSize!.value = (frame.clock.size * 2) / 0.9;
      cu.uAlpha!.value = frame.clock.a;
      cu.uTicks!.value = frame.clock.ticks;
      cu.uHand!.value = frame.clock.hand;

      thread.update(frame, camera.aspect);
    },
    resize(width, height) {
      thread.resize(width, height);
    },
  };
}
