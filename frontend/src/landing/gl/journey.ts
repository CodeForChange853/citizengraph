// The objects of the two journeys (scenes 3 to 8): constellations, beams, orb, clock ring, thread.
// They are built here and added to the stage as one group, so the stage file stays about the scaffold.
import * as THREE from "three";
import type { Frame } from "./director";

export interface Journey {
  group: THREE.Group;
  update(frame: Frame, time: number, camera: THREE.PerspectiveCamera, px: number): void;
}

export function buildJourney(): Journey {
  const group = new THREE.Group();
  return {
    group,
    update() {},
  };
}
