import { readdirSync } from "node:fs";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FakeAudioContext } from "./fakeAudio";
import { MASTER_GAIN, MAX_SOUND_S, SoundEngine } from "./sound";
import type { CueKind } from "./timeline";

function engineOn() {
  const made: FakeAudioContext[] = [];
  vi.stubGlobal(
    "AudioContext",
    class extends FakeAudioContext {
      constructor() {
        super();
        made.push(this);
      }
    },
  );
  const engine = new SoundEngine();
  engine.setEnabled(true);
  return { engine, ctx: made[0]! };
}

afterEach(() => vi.unstubAllGlobals());

describe("landing sound engine", () => {
  it("makes key clicks from filtered noise, a little different for every key", () => {
    const { engine, ctx } = engineOn();
    for (let i = 0; i < 12; i++) engine.play("key");
    expect(ctx.sources.every((s) => s.kind === "noise")).toBe(true);
    expect(ctx.sources).toHaveLength(12);
    const pitches = ctx.filters.map((f) => f.frequency.value);
    expect(new Set(pitches.map((p) => Math.round(p))).size).toBeGreaterThan(8);
    expect(Math.min(...pitches)).toBeGreaterThanOrEqual(3200);
    expect(Math.max(...pitches)).toBeLessThanOrEqual(5200);
    expect(ctx.filters.every((f) => f.type === "bandpass")).toBe(true);
    const peaks = ctx.gains.slice(1).map((g) => Math.max(...g.gain.peaks));
    expect(new Set(peaks.map((p) => p.toFixed(3))).size).toBeGreaterThan(8); // gain varies per key
  });

  it("gives Enter a low thunk and the guardrail check a soft high tick", () => {
    const { engine, ctx } = engineOn();
    engine.play("enter");
    expect(ctx.filters[0]).toMatchObject({ type: "lowpass", frequency: { value: 900 } });
    engine.play("tick");
    expect(ctx.filters[1]).toMatchObject({ type: "bandpass", frequency: { value: 6000 } });
    engine.play("blip");
    expect(ctx.sources.map((s) => s.kind)).toEqual(["noise", "sine", "noise", "sine", "sine"]);
  });

  it("never holds a tone: every source is stopped within a tenth of a second", () => {
    const { engine, ctx } = engineOn();
    for (const kind of ["key", "enter", "tick", "blip"] as CueKind[]) engine.play(kind);
    for (const source of ctx.sources) expect(source.stopAt - ctx.currentTime).toBeLessThanOrEqual(MAX_SOUND_S + 1e-9);
  });

  it("is quiet: one low master gain, and no sound louder than full scale before it", () => {
    const { engine, ctx } = engineOn();
    expect(ctx.gains[0]!.gain.value).toBe(MASTER_GAIN);
    expect(MASTER_GAIN).toBeLessThanOrEqual(0.25);
    for (const kind of ["key", "enter", "tick", "blip"] as CueKind[]) engine.play(kind);
    for (const g of ctx.gains.slice(1)) expect(Math.max(...g.gain.peaks)).toBeLessThanOrEqual(1);
  });

  it("plays nothing while muted, before a gesture, or while the context is suspended", () => {
    FakeAudioContext.made = 0;
    vi.stubGlobal("AudioContext", FakeAudioContext);
    const engine = new SoundEngine();
    engine.arm(true); // remembered "on", but no gesture yet
    engine.play("key");
    expect(FakeAudioContext.made).toBe(0);
    const on = engineOn();
    on.ctx.state = "suspended";
    on.engine.play("key");
    on.ctx.state = "running";
    on.engine.setEnabled(false);
    on.engine.play("key");
    expect(on.ctx.sources).toHaveLength(0);
    expect(on.ctx.suspend).toHaveBeenCalled();
  });

  it("ships no audio files", () => {
    const audio = /\.(mp3|ogg|wav|m4a|aac|flac|opus|webm|mp4)$/i;
    const walk = (dir: string): string[] =>
      readdirSync(dir, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? walk(`${dir}/${e.name}`) : [`${dir}/${e.name}`]));
    expect([...walk("src/landing"), ...walk("public")].filter((f) => audio.test(f))).toEqual([]);
  });
});
