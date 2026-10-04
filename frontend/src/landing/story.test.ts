import { describe, expect, it } from "vitest";
import { BEAT, CUES } from "./beats";
import { direct, heartbeat, STARS, CLUSTERS, TITLE_Z, WATCH } from "./gl/director";
import { distance } from "./gl/vec";
import { subjectPoint } from "./layout";
import { CUT_DISTANCE, Playhead, type CueKind } from "./playhead";
import { anchorPos, END, FILM_SECONDS, filmPos, filmTime, fractionToPos, posToFraction, SCENES, sceneAt, TOTAL_VH, visibility } from "./scenes";

describe("scene table", () => {
  it("has nine scenes of about 100 to 150 vh per idea and a film of about a minute", () => {
    expect(SCENES.map((s) => s.id)).toEqual(["title", "question", "guide", "journey", "answer", "watch", "request", "together", "close"]);
    expect(TOTAL_VH).toBe(1480);
    // the journey has four shots and the request three: each shot is its own idea
    expect(SCENES[3]!.vh / 4).toBe(100);
    expect(SCENES[6]!.vh / 3).toBeLessThanOrEqual(150);
    for (const s of SCENES.filter((_, i) => i !== 3 && i !== 6)) {
      expect(s.vh).toBeGreaterThanOrEqual(100);
      expect(s.vh).toBeLessThanOrEqual(150);
    }
    expect(FILM_SECONDS).toBeGreaterThan(55);
    expect(FILM_SECONDS).toBeLessThan(65);
  });

  it("maps scroll distance to the playhead and back", () => {
    expect(fractionToPos(0)).toBe(0);
    expect(fractionToPos(1)).toBe(END);
    expect(fractionToPos(100 / TOTAL_VH)).toBeCloseTo(1);
    expect(fractionToPos((100 + 120 + 120 + 200) / TOTAL_VH)).toBeCloseTo(3.5);
    for (let u = 0; u <= END; u += 0.37) expect(fractionToPos(posToFraction(u))).toBeCloseTo(u, 6);
    expect(sceneAt(3.25)).toEqual({ index: 3, p: 0.25 });
    expect(sceneAt(99).index).toBe(8);
  });

  it("puts every chapter link inside its own scene, where the headline has landed", () => {
    SCENES.forEach((_, i) => {
      const at = anchorPos(i);
      expect(at).toBeGreaterThanOrEqual(i);
      expect(at).toBeLessThanOrEqual(i + 1);
      expect(visibility(i, Math.min(at, END))).toBe(1);
    });
  });

  it("never shows the words of two scenes at once", () => {
    for (let u = 0; u <= END; u += 0.005) {
      const seen = SCENES.filter((_, i) => visibility(i, u) > 0.5).length;
      expect(seen).toBeLessThanOrEqual(1);
    }
  });

  it("runs the film through every scene after the hook, and can invert it", () => {
    expect(filmPos(0)).toBe(0);
    expect(filmPos(3)).toBe(0);
    expect(filmPos(FILM_SECONDS)).toBe(END);
    for (let u = 0.1; u < END; u += 0.7) expect(filmPos(filmTime(u))).toBeCloseTo(u, 6);
  });
});

describe("playhead", () => {
  const run = (playhead: Playhead, ms: number, step = 16) => {
    for (let t = 0; t < ms; t += step) playhead.tick(step);
  };

  it("plays the hook for 3 seconds by itself and then rests", () => {
    const playhead = new Playhead();
    expect(playhead.moving).toBe(true);
    run(playhead, 1500);
    expect(playhead.hook).toBeCloseTo(0.5, 1);
    run(playhead, 1600);
    expect(playhead.hook).toBe(1);
    expect(playhead.moving).toBe(false);
    expect(playhead.pos).toBe(0);
  });

  it("eases toward the scroll position, in both directions, and settles on it exactly", () => {
    const playhead = new Playhead();
    playhead.finish(2);
    playhead.setTarget(2.4);
    playhead.tick(16);
    expect(playhead.pos).toBeGreaterThan(2);
    expect(playhead.pos).toBeLessThan(2.4);
    run(playhead, 1500);
    expect(playhead.pos).toBe(2.4);
    playhead.setTarget(2.1);
    run(playhead, 1500);
    expect(playhead.pos).toBe(2.1);
  });

  it("cuts on a big jump instead of whipping through the scenes, and fires no cues", () => {
    const heard: CueKind[] = [];
    const playhead = new Playhead(CUES);
    playhead.onCue((kind) => heard.push(kind));
    playhead.setTarget(6.2);
    expect(playhead.pos).toBe(6.2);
    expect(playhead.cuts).toBe(1);
    expect(playhead.hook).toBe(1);
    run(playhead, 500);
    expect(heard).toEqual([]);
    playhead.setTarget(6.2 + CUT_DISTANCE - 0.1);
    expect(playhead.cuts).toBe(1);
  });

  it("fires each cue once when the playhead crosses it going forward, never going back", () => {
    const heard: CueKind[] = [];
    const playhead = new Playhead(CUES);
    playhead.onCue((kind) => heard.push(kind));
    run(playhead, 3100); // the hook: both cores ignite
    expect(heard).toEqual(["ignite", "ignite"]);
    playhead.finish(4.6);
    playhead.setTarget(4.95);
    run(playhead, 2000);
    expect(heard.slice(2)).toEqual(["tick", "tick", "tick", "tick"]);
    playhead.setTarget(4.6);
    run(playhead, 2000);
    expect(heard).toHaveLength(6);
  });
});

describe("director", () => {
  const frame = (u: number, aspect = 16 / 9, time = 0, hook = 1) => direct(u, hook, time, aspect);

  it("opens on black with one orange spark and nothing else", () => {
    const f = frame(0, 16 / 9, 0, 0);
    expect(f.cyan.scale).toBe(0);
    expect(f.orange.scale).toBe(0);
    expect(f.glass.a).toBe(0);
    expect(f.corridor.a).toBe(0);
    const lit = f.glows.filter((g) => g.a > 0.05 && g.size > 0);
    expect(lit.length).toBeGreaterThan(0);
    for (const g of lit) expect(g.p).toEqual([0, 0, TITLE_Z]);
  });

  it("ends the hook with both cores lit inside the glass module", () => {
    const f = frame(0);
    expect(f.cyan.scale).toBeCloseTo(1);
    expect(f.orange.scale).toBeCloseTo(1);
    expect(f.cyan.p[0]).toBeLessThan(0);
    expect(f.orange.p[0]).toBeGreaterThan(0);
    expect(f.glass.a).toBe(1);
    expect(f.glass.open).toBe(0);
  });

  it("flies down the corridor in scene 1 and arrives at the module", () => {
    expect(frame(1.5).corridor.a).toBe(1);
    expect(frame(1.5).cam.p[2]).toBeLessThan(TITLE_Z);
    expect(frame(1.5).cam.p[2]).toBeGreaterThan(8);
    expect(frame(1.5).sheets.some((s) => s.a > 0.5)).toBe(true);
    const arrived = frame(2.3);
    expect(arrived.corridor.a).toBe(0);
    expect(arrived.cam.look).toEqual([0, 0, 0]);
  });

  it("gives the stage to the cyan core in scene 2 and to the orange core in scene 5", () => {
    const guide = frame(2.7);
    expect(guide.cyan.scale).toBeGreaterThan(1.4);
    expect(guide.orange.power).toBeLessThan(0.5);
    expect(guide.glass.open).toBeGreaterThan(1);
    const watch = frame(5.7);
    expect(watch.orange.scale).toBeGreaterThan(1.3);
    expect(watch.orange.power).toBeGreaterThan(0.9);
    expect(distance(watch.orange.p, WATCH)).toBeLessThan(0.01);
    expect(distance(watch.cam.look, WATCH)).toBeLessThan(0.3);
    expect(watch.clock.a).toBe(1);
    expect(watch.clock.ticks).toBe(1);
  });

  it("has 40 service points in four offices: 7, 17, 15 and 1", () => {
    expect(STARS).toHaveLength(40);
    expect(CLUSTERS.map((c) => c.count)).toEqual([7, 17, 15, 1]);
    expect([0, 1, 2, 3].map((c) => STARS.filter((s) => s.cluster === c).length)).toEqual([7, 17, 15, 1]);
  });

  it("fans the beam to four offices, then narrows it to one service", () => {
    const fan = frame(BEAT.fan[1] + 0.01);
    expect(fan.beams).toHaveLength(4);
    expect(fan.beams.every((b) => b.grow > 0.9 && b.a > 0)).toBe(true);
    const one = frame(3.74);
    expect(one.beams.filter((b) => b.a > 0.01)).toHaveLength(1);
    expect(one.stars.lit).toBe(1);
    expect(one.anchors.service.a).toBe(1);
    expect(one.anchors.office1.a).toBe(0);
  });

  it("collapses the points into the orb, then lets the orb go when the card opens", () => {
    expect(frame(4.4).orb.size).toBeCloseTo(1);
    expect(frame(4.4).stars.a).toBe(0);
    expect(frame(4.4).floor.warp).toBeGreaterThan(0.9);
    expect(frame(4.8).orb.size).toBe(0);
  });

  it("draws the thread only as far as the late step and never finishes it", () => {
    expect(frame(6.07).thread.draw).toBe(0);
    const late = frame(6.9);
    expect(late.thread.draw).toBeGreaterThan(0.7);
    expect(late.thread.draw).toBeLessThan(0.8);
    expect(late.thread.grey).toBe(1);
    expect(late.thread.late).toBe(1);
    expect(late.anchors.alert.a).toBe(1);
    expect(late.anchors.outside.a).toBe(1);
  });

  it("is continuous: a small scroll step never throws the camera or a core across the stage", () => {
    for (const aspect of [16 / 9, 390 / 700]) {
      let before = frame(0, aspect);
      for (let u = 0.004; u <= END; u += 0.004) {
        const now = frame(u, aspect);
        expect(distance(now.cam.p, before.cam.p), `camera at ${u.toFixed(3)}`).toBeLessThan(0.8);
        // the cores are moved from the title to the station only while they are dark
        if (now.cyan.power > 0.05 && before.cyan.power > 0.05) expect(distance(now.cyan.p, before.cyan.p), `cyan at ${u.toFixed(3)}`).toBeLessThan(0.35);
        if (now.orange.power > 0.05 && before.orange.power > 0.05) expect(distance(now.orange.p, before.orange.p), `orange at ${u.toFixed(3)}`).toBeLessThan(0.35);
        before = now;
      }
    }
  });

  it("is a pure function: the same inputs give the same frame, so scrubbing back works", () => {
    expect(direct(3.61, 1, 12.5, 1.6)).toEqual(direct(3.61, 1, 12.5, 1.6));
  });

  it("keeps the heartbeat under three flashes a second", () => {
    let peaks = 0;
    let rising = false;
    for (let t = 0; t < 10; t += 0.005) {
      const up = heartbeat(t + 0.005) > heartbeat(t);
      if (rising && !up) peaks++;
      rising = up;
    }
    expect(peaks / 10).toBeLessThanOrEqual(3);
  });

  it("centres the subject for the title and the close, and moves it aside in between", () => {
    expect(subjectPoint(0, 16 / 9).x).toBe(0.5);
    expect(subjectPoint(4, 16 / 9).x).toBeGreaterThan(0.6);
    expect(subjectPoint(9, 16 / 9).x).toBe(0.5);
    expect(subjectPoint(4, 390 / 700).x).toBe(0.5);
    expect(subjectPoint(4, 390 / 700).y).toBeLessThan(0.4);
  });
});
