// Sound for the intro: three tiny synthesized blips (key click, enter, guardrail tick). No audio files.
// Rules: muted unless the visitor turned it on (the choice is remembered), nothing is created before
// a user gesture, it stops while the tab is hidden, and it never plays with reduced motion.
import { useEffect, useState } from "react";
import { readJson, writeJson } from "../lib/storage";
import type { CueKind, Timeline } from "./timeline";

export const SOUND_KEY = "cg.landing.sound";

type AudioCtor = typeof AudioContext;

function audioCtor(): AudioCtor | undefined {
  const w = window as Window & { AudioContext?: AudioCtor; webkitAudioContext?: AudioCtor };
  return w.AudioContext ?? w.webkitAudioContext;
}

function blip(ctx: AudioContext, type: OscillatorType, from: number, to: number, seconds: number, peak: number) {
  const now = ctx.currentTime;
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = type;
  osc.frequency.setValueAtTime(from, now);
  if (to !== from) osc.frequency.exponentialRampToValueAtTime(to, now + seconds);
  gain.gain.setValueAtTime(0.0001, now);
  gain.gain.exponentialRampToValueAtTime(peak, now + 0.004);
  gain.gain.exponentialRampToValueAtTime(0.0001, now + seconds);
  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.start(now);
  osc.stop(now + seconds + 0.02);
}

export class SoundEngine {
  private ctx: AudioContext | null = null;
  private keys = 0;
  enabled = false;

  /** Call only from a user gesture (a click, tap or key press): creates or resumes the audio context. */
  unlock = (): void => {
    if (!this.enabled || document.hidden) return;
    const Ctor = audioCtor();
    if (!Ctor) return;
    try {
      this.ctx ??= new Ctor();
      if (this.ctx.state === "suspended") void this.ctx.resume();
    } catch {
      this.ctx = null; // no audio on this device: stay silent
    }
  };

  /** Stop while the tab is hidden; carry on when it is shown again. */
  onVisibility = (): void => {
    if (!this.ctx) return;
    if (document.hidden) void this.ctx.suspend();
    else if (this.enabled) void this.ctx.resume();
  };

  /** Set the remembered choice without touching audio: no context exists until a gesture. */
  arm(on: boolean): void {
    this.enabled = on;
  }

  setEnabled(on: boolean): void {
    this.enabled = on;
    if (on) this.unlock();
    else if (this.ctx) void this.ctx.suspend();
  }

  play = (kind: CueKind): void => {
    const ctx = this.ctx;
    if (!this.enabled || !ctx || ctx.state !== "running" || document.hidden) return;
    if (kind === "key") blip(ctx, "square", 1500 + ((this.keys++ * 137) % 400), 900, 0.03, 0.03);
    else if (kind === "enter") blip(ctx, "triangle", 330, 190, 0.11, 0.07);
    else blip(ctx, "sine", 1320, 1760, 0.08, 0.05);
  };

  close(): void {
    void this.ctx?.close();
    this.ctx = null;
  }
}

/** The sound toggle's state. `available` is false with reduced motion: then there is no sound at all. */
export function useSound(timeline: Timeline, reduced: boolean) {
  const [enabled, setEnabled] = useState(() => readJson<unknown>(SOUND_KEY, false) === true);
  const [engine] = useState(() => new SoundEngine());

  useEffect(() => {
    if (reduced) return;
    engine.arm(enabled);
    const offCue = timeline.onCue(engine.play);
    // A remembered "on" still waits for the first gesture on this visit.
    window.addEventListener("pointerdown", engine.unlock);
    window.addEventListener("keydown", engine.unlock);
    document.addEventListener("visibilitychange", engine.onVisibility);
    return () => {
      offCue();
      window.removeEventListener("pointerdown", engine.unlock);
      window.removeEventListener("keydown", engine.unlock);
      document.removeEventListener("visibilitychange", engine.onVisibility);
      engine.arm(false);
    };
  }, [engine, enabled, reduced, timeline]);

  useEffect(() => () => engine.close(), [engine]);

  function toggle() {
    const next = !enabled;
    writeJson(SOUND_KEY, next);
    setEnabled(next);
    engine.setEnabled(next); // inside the click, so the browser allows audio to start
  }

  return { available: !reduced, enabled: enabled && !reduced, toggle };
}
