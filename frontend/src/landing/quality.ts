// Adaptive quality for the stage canvas: decide when to step down a level.
//
// The earlier rule counted late frames up and on-time frames down and stepped at a net count of 24.
// Under a 4x CPU slow-down only about one frame in four is late, so every late frame was cancelled by
// the on-time frames round it and the count never (or only after many seconds) reached 24.
//
// The rule now looks at a sliding window of the last frames while the picture is animating:
//   - a frame is LATE when it arrives more than 25 ms after the previous one (below 40 frames a second);
//   - step down as soon as 6 of the last 40 frames (15 %) were late, or when drawing alone has averaged
//     more than 10 ms over at least 20 frames;
//   - a gap of 250 ms or more means the picture was idle (nothing to draw), so it is not counted;
//   - after a step the window starts again, so the next step needs fresh evidence at the new level.
// The canvas also ignores the first second and a half after it mounts, while the chunk and fonts settle.
// Quality only ever goes down during a visit.

export const LATE_MS = 25;
export const WINDOW_FRAMES = 40;
export const LATE_LIMIT = 6;
export const IDLE_GAP_MS = 250;
export const DRAW_BUDGET_MS = 10;
export const DRAW_MIN_FRAMES = 20;
export const WARMUP_MS = 1500;

export class FrameBudget {
  private late: boolean[] = [];
  private draws: number[] = [];

  /**
   * Record one drawn frame: the time since the previous frame and how long drawing took.
   * Returns true when the quality should drop one level.
   */
  frame(gapMs: number, drawMs: number): boolean {
    if (gapMs >= IDLE_GAP_MS) return false; // first frame after a pause: says nothing about speed
    this.late.push(gapMs > LATE_MS);
    this.draws.push(drawMs);
    if (this.late.length > WINDOW_FRAMES) {
      this.late.shift();
      this.draws.shift();
    }
    const lateCount = this.late.reduce((n, isLate) => n + (isLate ? 1 : 0), 0);
    const meanDraw = this.draws.reduce((sum, ms) => sum + ms, 0) / this.draws.length;
    const slow = lateCount >= LATE_LIMIT || (this.draws.length >= DRAW_MIN_FRAMES && meanDraw > DRAW_BUDGET_MS);
    if (slow) this.reset();
    return slow;
  }

  reset(): void {
    this.late = [];
    this.draws = [];
  }
}
