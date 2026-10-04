import type { SceneId } from "./scenes";

/**
 * A still picture of a scene, drawn as lines. It stands in for the 3D picture when WebGL is not there
 * and when the device asks for reduced motion. Filled in with the fallbacks (phase H).
 */
export function Poster({ scene, label }: { scene: SceneId; label: string }) {
  return <svg className="lp-posterart" data-poster={scene} viewBox="0 0 400 300" role="img" aria-label={label} />;
}
