// Sound for the intro: a terminal, and nothing else. Every sound is synthesized with Web Audio from a
// short noise buffer and a few very short sine blips (docs/landing_motion_spec.md, section 5). There are
// no audio files, no music and no held tones: the longest sound is under a tenth of a second.
// Rules: muted unless the visitor turned it on (the choice is remembered), nothing is created before
// a user gesture, it stops while the tab is hidden, and it never plays with reduced motion.
import { useEffect, useState } from "react";
import { readJson, writeJson } from "../lib/storage";
import type { CueKind, Timeline } from "./timeline";

export const SOUND_KEY = "cg.landing.sound";
/** Everything is quiet: this is the ceiling for the sum of all sounds. */
export const MASTER_GAIN = 0.22;
/** No sound lasts longer than this (seconds). */
export const MAX_SOUND_S = 0.1;

type AudioCtor = typeof AudioContext;

function audioCtor(): AudioCtor | undefined {
  const w = window as Window & { AudioContext?: AudioCtor; webkitAudioContext?: AudioCtor };
  return w.AudioContext ?? w.webkitAudioContext;
}

/** A small deterministic generator: per-key variation without Math.random, so tests are stable. */
function vary(n: number): number {
  const x = Math.sin(n * 12.9898) * 43758.5453;
  return x - Math.floor(x);
}

export class SoundEngine {
  private ctx: AudioContext | null = null;
  private out: GainNode | null = null;
  private noise: AudioBuffer | null = null;
  private count = 0;
  enabled = false;

  /** Call only from a user gesture (a click, tap or key press): creates or resumes the audio context. */
  unlock = (): void => {
    if (!this.enabled || document.hidden) return;
    const Ctor = audioCtor();
    if (!Ctor) return;
    try {
      if (!this.ctx) {
        const ctx = new Ctor();
        const out = ctx.createGain();
        out.gain.value = MASTER_GAIN;
        out.connect(ctx.destination);
        // a quarter of a second of white noise, made once; every click plays a slice of it
        const length = Math.floor(ctx.sampleRate * 0.25);
        const noise = ctx.createBuffer(1, length, ctx.sampleRate);
        const data = noise.getChannelData(0);
        for (let i = 0; i < length; i++) data[i] = vary(i + 1) * 2 - 1;
        this.ctx = ctx;
        this.out = out;
        this.noise = noise;
      }
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

  /** A burst of filtered noise: the body of every click. */
  private burst(type: BiquadFilterType, frequency: number, q: number, decay: number, peak: number): void {
    const { ctx, out, noise } = this;
    if (!ctx || !out || !noise) return;
    const now = ctx.currentTime;
    const source = ctx.createBufferSource();
    source.buffer = noise;
    const filter = ctx.createBiquadFilter();
    filter.type = type;
    filter.frequency.value = frequency;
    filter.Q.value = q;
    const gain = ctx.createGain();
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(peak, now + 0.001);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + decay);
    source.connect(filter);
    filter.connect(gain);
    gain.connect(out);
    source.start(now, vary(this.count + 0.5) * 0.12);
    source.stop(now + Math.min(MAX_SOUND_S, decay + 0.01));
  }

  /** A very short sine: the pitch of a tick or the weight of the Enter key. Never held. */
  private blip(from: number, to: number, seconds: number, peak: number): void {
    const { ctx, out } = this;
    if (!ctx || !out) return;
    const now = ctx.currentTime;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.setValueAtTime(from, now);
    if (to !== from) osc.frequency.exponentialRampToValueAtTime(to, now + seconds);
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(peak, now + 0.003);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + seconds);
    osc.connect(gain);
    gain.connect(out);
    osc.start(now);
    osc.stop(now + Math.min(MAX_SOUND_S, seconds + 0.01));
  }

  play = (kind: CueKind): void => {
    const ctx = this.ctx;
    if (!this.enabled || !ctx || ctx.state !== "running" || document.hidden) return;
    const n = this.count++;
    if (kind === "key") {
      // each key a little different in pitch, length and loudness
      this.burst("bandpass", 3200 + vary(n) * 2000, 1.4, 0.022 + vary(n + 0.3) * 0.012, 0.55 + vary(n + 0.7) * 0.3);
    } else if (kind === "enter") {
      this.burst("lowpass", 900, 0.7, 0.09, 0.9);
      this.blip(150, 60, 0.08, 0.6);
    } else if (kind === "tick") {
      this.burst("bandpass", 6000, 6, 0.018, 0.6);
      this.blip(2100, 2100, 0.03, 0.2);
    } else {
      this.blip(1400, 1400, 0.022, 0.12);
    }
  };

  close(): void {
    void this.ctx?.close();
    this.ctx = null;
    this.out = null;
    this.noise = null;
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
