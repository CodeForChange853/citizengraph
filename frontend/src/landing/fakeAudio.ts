// Test helper only (never imported by the page).
import { vi } from "vitest";

/** A stand-in audio context that records every node it makes and when each source stops. */
export class FakeAudioContext {
  static made = 0;
  state = "running";
  currentTime = 10;
  sampleRate = 8000;
  destination = {};
  sources: { kind: "noise" | "sine"; stopAt: number }[] = [];
  filters: { type: string; frequency: { value: number; setValueAtTime: unknown; exponentialRampToValueAtTime: unknown }; Q: { value: number } }[] = [];
  gains: { gain: { value: number; peaks: number[] } }[] = [];
  constructor() {
    FakeAudioContext.made++;
  }
  resume = vi.fn(async () => {});
  suspend = vi.fn(async () => {});
  close = vi.fn(async () => {});
  createBuffer = (_channels: number, length: number) => ({ getChannelData: () => new Float32Array(length) });
  createBufferSource = () => {
    const record = { kind: "noise" as const, stopAt: Infinity };
    this.sources.push(record);
    return { buffer: null, loop: false, connect: vi.fn(), start: vi.fn(), stop: (at: number) => (record.stopAt = at) };
  };
  createOscillator = () => {
    const record = { kind: "sine" as const, stopAt: Infinity };
    this.sources.push(record);
    return {
      type: "sine",
      frequency: { setValueAtTime: vi.fn(), exponentialRampToValueAtTime: vi.fn() },
      connect: vi.fn(),
      start: vi.fn(),
      stop: (at: number) => (record.stopAt = at),
    };
  };
  createBiquadFilter = () => {
    const filter = { type: "", frequency: { value: 0, setValueAtTime: vi.fn(), exponentialRampToValueAtTime: vi.fn() }, Q: { value: 0 }, connect: vi.fn() };
    this.filters.push(filter);
    return filter;
  };
  createGain = () => {
    const peaks: number[] = [];
    const node = {
      gain: { value: 1, peaks, setValueAtTime: vi.fn(), exponentialRampToValueAtTime: (v: number) => peaks.push(v) },
      connect: vi.fn(),
    };
    this.gains.push(node);
    return node;
  };
}
