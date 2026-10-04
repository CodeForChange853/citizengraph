// The objects of the two journeys (scenes 3 to 8): constellations, beams, orb, clock ring, thread.
// They are built here and added to the stage as one group, so the stage file stays about the scaffold.
import * as THREE from "three";
import { tone } from "../tokens";
import { STARS, TARGET_STAR, type Frame } from "./director";
import * as S from "./journeyShaders";
import { distance, hash } from "./vec";

export interface Journey {
  group: THREE.Group;
  update(frame: Frame, time: number, camera: THREE.PerspectiveCamera, px: number): void;
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

export function buildJourney(): Journey {
  const group = new THREE.Group();
  const stars = makeStars();
  const beams = makeBeams();
  group.add(beams.mesh, stars.links, stars.points);
  return {
    group,
    update(frame, time, camera, px) {
      const su = stars.uniforms;
      stars.points.visible = stars.links.visible = frame.stars.a > 0.003;
      su.uAlpha.value = frame.stars.a;
      su.uCollapse.value = frame.stars.collapse;
      su.uLit.value = frame.stars.lit;
      su.uSqueeze.value = frame.stars.squeeze;
      su.uPx.value = px;
      su.uTime.value = time;
      beams.update(frame, camera);
    },
  };
}
