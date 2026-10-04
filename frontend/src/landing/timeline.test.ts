import { describe, expect, it } from "vitest";
import { CUES, cypherChars, DEMO_CYPHER, DEMO_QUESTION, guardTicks, OFFICES, SERVICE_TOTAL, typedChars } from "./demo";
import { storyTime } from "./playback";
import { beat, BEATS, INTRO_END, Timeline, TIMELINE_END, type CueKind } from "./timeline";

describe("timeline controller", () => {
  it("lays the eight beats end to end", () => {
    expect(BEATS.map((b) => b.id)).toEqual(["ask", "contours", "offices", "query", "trail", "answer", "sla", "local"]);
    for (let i = 1; i < BEATS.length; i++) expect(BEATS[i]!.start).toBe(BEATS[i - 1]!.start + BEATS[i - 1]!.dur);
    expect(INTRO_END).toBe(beat("query").start + beat("query").dur);
  });

  it("does not move until it is played, and the intro stops at the end of beat 4", () => {
    const tl = new Timeline(CUES);
    tl.advance(500);
    expect(tl.time).toBe(0);
    tl.play();
    tl.advance(INTRO_END + 5000);
    expect(tl.time).toBe(INTRO_END);
    expect(tl.playing).toBe(false);
    expect(tl.progress("query")).toBe(1);
    expect(tl.progress("trail")).toBe(0);
  });

  it("fires sound cues only while playing, each one once, never on a seek or a skip", () => {
    const heard: CueKind[] = [];
    const tl = new Timeline(CUES);
    tl.onCue((kind) => heard.push(kind));
    tl.seek(INTRO_END);
    tl.seek(0);
    expect(heard).toEqual([]);
    tl.play();
    for (let t = 0; t < INTRO_END; t += 16) tl.advance(16);
    expect(heard.filter((k) => k === "key")).toHaveLength(DEMO_QUESTION.replaceAll(" ", "").length);
    expect(heard.filter((k) => k === "enter")).toHaveLength(1);
    expect(heard.filter((k) => k === "tick")).toHaveLength(4);
    expect(heard.filter((k) => k === "blip")).toHaveLength(OFFICES.length);

    const skipped: CueKind[] = [];
    const other = new Timeline(CUES);
    other.onCue((kind) => skipped.push(kind));
    other.play();
    other.skipIntro();
    expect(other.introDone).toBe(true);
    expect(skipped).toEqual([]);
  });

  it("can be seeked anywhere and paused", () => {
    const tl = new Timeline();
    tl.seek(beat("sla").start + 500);
    expect(tl.progress("sla")).toBe(0.5);
    expect(tl.progress("answer")).toBe(1);
    expect(tl.progress("local")).toBe(0);
    tl.seek(TIMELINE_END + 999);
    expect(tl.time).toBe(TIMELINE_END);
    tl.replay();
    tl.advance(100);
    tl.pause();
    tl.advance(100);
    expect(tl.time).toBe(100);
  });

  it("notifies subscribers and lets them unsubscribe", () => {
    const tl = new Timeline();
    let calls = 0;
    const off = tl.subscribe(() => calls++);
    tl.seek(10);
    off();
    tl.seek(20);
    expect(calls).toBe(1);
  });
});

describe("scroll story", () => {
  const vh = 800;
  const below = [1, 2, 3].map((i) => ({ top: vh * (1.9 + i), height: 700 }));

  it("holds at the end of the intro at the top of the page", () => {
    expect(storyTime({ vh, wrapTop: 0, wrapHeight: 1520, stageHeight: 800, sections: below })).toBe(INTRO_END);
  });

  it("draws beat 5 while the pinned stage is scrolled through", () => {
    const half = storyTime({ vh, wrapTop: -360, wrapHeight: 1520, stageHeight: 800, sections: below });
    expect(half).toBe(beat("trail").start + 0.5 * beat("trail").dur);
    const done = storyTime({ vh, wrapTop: -720, wrapHeight: 1520, stageHeight: 800, sections: below });
    expect(done).toBe(beat("answer").start);
  });

  it("runs each later beat as its section rises into view, and reaches the end at the bottom", () => {
    const sections = [
      { top: -900, height: 700 },
      { top: -200, height: 700 },
      { top: 500, height: 700 },
    ];
    const t = storyTime({ vh, wrapTop: -3000, wrapHeight: 1520, stageHeight: 800, sections });
    expect(t).toBeGreaterThan(beat("local").start);
    expect(t).toBeLessThan(TIMELINE_END);
    sections[2] = { top: 60, height: 700 };
    expect(storyTime({ vh, wrapTop: -3440, wrapHeight: 1520, stageHeight: 800, sections })).toBe(TIMELINE_END);
  });

  it("finishes the last beat at the bottom of the page even when the last section is short", () => {
    const sections = [
      { top: -700, height: 400 },
      { top: -300, height: 400 },
      { top: 700, height: 200 },
    ];
    const layout = { vh, wrapTop: -3000, wrapHeight: 1520, stageHeight: 800, sections };
    expect(storyTime(layout)).toBeLessThan(TIMELINE_END);
    expect(storyTime({ ...layout, atBottom: true })).toBe(TIMELINE_END);
  });

  it("ignores sections that have no size yet", () => {
    const empty = [0, 0, 0].map(() => ({ top: 0, height: 0 }));
    expect(storyTime({ vh, wrapTop: 0, wrapHeight: 0, stageHeight: 0, sections: empty })).toBe(INTRO_END);
  });
});

describe("demo script", () => {
  it("types the whole question inside beat 1 and the whole query and all ticks inside beat 4", () => {
    expect(typedChars(0)).toBe(0);
    expect(typedChars(beat("ask").dur)).toBe(DEMO_QUESTION.length);
    expect(cypherChars(0)).toBe(0);
    expect(cypherChars(beat("query").dur)).toBe(DEMO_CYPHER.length);
    expect(guardTicks(beat("query").dur)).toBe(4);
    expect(Math.max(...CUES.map((c) => c.at))).toBeLessThan(INTRO_END);
  });

  it("never clicks more than a key at a time faster than typing speed", () => {
    const keys = CUES.filter((c) => c.kind === "key").map((c) => c.at);
    for (let i = 1; i < keys.length; i++) expect(keys[i]! - keys[i - 1]!).toBeGreaterThanOrEqual(40);
  });

  it("counts 40 services in four offices", () => {
    expect(OFFICES).toHaveLength(4);
    expect(SERVICE_TOTAL).toBe(40);
  });
});
