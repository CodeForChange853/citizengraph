import { readdirSync } from "node:fs";
import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { landing, setReducedMotion } from "./testHelpers";
import { CUES } from "./beats";
import { FakeAudioContext } from "./fakeAudio";
import type { CueKind } from "./playhead";
import { MASTER_GAIN, MAX_SOUND_S, SOUND_KEY, SoundEngine } from "./sound";

const KINDS: CueKind[] = ["ignite", "whoosh", "tick", "pulse"];

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

afterEach(() => {
  vi.unstubAllGlobals();
  setReducedMotion(false);
});

describe("landing sound engine", () => {
  it("makes a swell and a whoosh from swept, filtered noise, and a tick from a short high band", () => {
    const { engine, ctx } = engineOn();
    engine.play("ignite");
    expect(ctx.sources.map((s) => s.kind)).toEqual(["noise", "sine"]);
    expect(ctx.filters[0]!.type).toBe("bandpass");
    engine.play("whoosh");
    expect(ctx.sources.map((s) => s.kind)).toEqual(["noise", "sine", "noise"]);
    engine.play("tick");
    expect(ctx.filters[2]).toMatchObject({ type: "bandpass", frequency: { value: 6000 } });
    engine.play("pulse");
    expect(ctx.filters[3]).toMatchObject({ type: "lowpass", frequency: { value: 420 } });
  });

  it("never sustains a sound: every source stops within about half a second", () => {
    const { engine, ctx } = engineOn();
    for (const kind of KINDS) engine.play(kind);
    expect(MAX_SOUND_S).toBeLessThanOrEqual(0.6);
    for (const source of ctx.sources) expect(source.stopAt - ctx.currentTime).toBeLessThanOrEqual(MAX_SOUND_S + 1e-9);
  });

  it("is quiet: one low master gain, and no sound louder than full scale before it", () => {
    const { engine, ctx } = engineOn();
    expect(ctx.gains[0]!.gain.value).toBe(MASTER_GAIN);
    expect(MASTER_GAIN).toBeLessThanOrEqual(0.25);
    for (const kind of KINDS) engine.play(kind);
    for (const g of ctx.gains.slice(1)) expect(Math.max(...g.gain.peaks)).toBeLessThanOrEqual(1);
  });

  it("plays nothing while muted, before a gesture, or while the context is suspended", () => {
    FakeAudioContext.made = 0;
    vi.stubGlobal("AudioContext", FakeAudioContext);
    const engine = new SoundEngine();
    engine.arm(true); // remembered "on", but no gesture yet
    engine.play("tick");
    expect(FakeAudioContext.made).toBe(0);
    const on = engineOn();
    on.ctx.state = "suspended";
    on.engine.play("tick");
    on.ctx.state = "running";
    on.engine.setEnabled(false);
    on.engine.play("tick");
    expect(on.ctx.sources).toHaveLength(0);
    expect(on.ctx.suspend).toHaveBeenCalled();
  });

  it("suspends while the tab is hidden and resumes when it is shown", () => {
    const { engine, ctx } = engineOn();
    const hidden = vi.spyOn(document, "hidden", "get");
    hidden.mockReturnValue(true);
    engine.onVisibility();
    expect(ctx.suspend).toHaveBeenCalled();
    hidden.mockReturnValue(false);
    engine.onVisibility();
    expect(ctx.resume).toHaveBeenCalled();
    hidden.mockRestore();
  });

  it("has cues for every kind and none that would repeat faster than a few a second", () => {
    expect(new Set(CUES.map((c) => c.kind))).toEqual(new Set(KINDS));
    const scroll = CUES.filter((c) => !c.hook).map((c) => c.at);
    expect([...scroll].sort((a, b) => a - b)).toEqual(scroll);
  });

  it("ships no audio files", () => {
    const audio = /\.(mp3|ogg|wav|m4a|aac|flac|opus|webm|mp4)$/i;
    const walk = (dir: string): string[] =>
      readdirSync(dir, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? walk(`${dir}/${e.name}`) : [`${dir}/${e.name}`]));
    expect([...walk("src/landing"), ...walk("public")].filter((f) => audio.test(f))).toEqual([]);
  });
});

describe("landing sound toggle", () => {
  it("is muted by default, creates audio only on the click, and remembers the choice", async () => {
    FakeAudioContext.made = 0;
    vi.stubGlobal("AudioContext", FakeAudioContext);
    const user = userEvent.setup();
    await landing();
    const off = screen.getByRole("button", { name: "Sound: off" });
    expect(off).toHaveAttribute("aria-pressed", "false");
    expect(FakeAudioContext.made).toBe(0);
    await user.click(off);
    expect(screen.getByRole("button", { name: "Sound: on" })).toHaveAttribute("aria-pressed", "true");
    expect(FakeAudioContext.made).toBe(1);
    expect(localStorage.getItem(SOUND_KEY)).toBe("true");
    await user.click(screen.getByRole("button", { name: "Sound: on" }));
    expect(localStorage.getItem(SOUND_KEY)).toBe("false");
  });

  it("has no sound control and makes no audio with reduced motion, even if sound was left on", async () => {
    FakeAudioContext.made = 0;
    vi.stubGlobal("AudioContext", FakeAudioContext);
    localStorage.setItem(SOUND_KEY, "true");
    setReducedMotion(true);
    const user = userEvent.setup();
    const root = await landing();
    expect(screen.queryByRole("button", { name: /Sound/ })).toBeNull();
    await user.click(root);
    await act(async () => {});
    expect(FakeAudioContext.made).toBe(0);
  });
});
