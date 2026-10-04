// Where the subject of the picture sits on the screen. On a wide screen the words take the left and the
// subject sits right of centre; on a tall screen the subject sits above the words. The title and the
// close are centred. The 3D camera and the page both use this, so cards and labels line up with the picture.
import { ramp } from "./ease";

/** Screens at least this wide for their height put words and picture side by side. */
export const WIDE_ASPECT = 1.15;

export const isWide = (aspect: number): boolean => aspect >= WIDE_ASPECT;

/** The subject centre as shares of the stage width and height, for a playhead position. */
export function subjectPoint(u: number, aspect: number): { x: number; y: number } {
  const wide = isWide(aspect);
  const side = wide ? { x: 0.67, y: 0.5 } : { x: 0.5, y: 0.35 };
  const centre = wide ? { x: 0.5, y: 0.43 } : { x: 0.5, y: 0.37 };
  const w = ramp(u, 0.75, 1.1) * (1 - ramp(u, 7.95, 8.3));
  return { x: centre.x + (side.x - centre.x) * w, y: centre.y + (side.y - centre.y) * w };
}
