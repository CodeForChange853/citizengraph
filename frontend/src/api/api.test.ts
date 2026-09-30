import { describe, expect, it, vi } from "vitest";
import { createApiClient, type ApiClient } from "./client";
import fixtures from "./fixtures.json";
import { createFixtureAdapter, mockChat } from "./fixtureAdapter";
import { ApiUnreachableError } from "./realAdapter";
import type { Lang } from "./types";

const fx = createFixtureAdapter();

describe("fixture adapter", () => {
  it("lists the six mock services in four groups", async () => {
    const services = await fx.services();
    expect(services).toHaveLength(6);
    expect(new Set(services.map((s) => s.group))).toEqual(
      new Set(["business", "family", "health", "assistance"]),
    );
  });

  it("answers a business permit question with a checklist, fees and steps", async () => {
    const res = await fx.chat({ message: "business permit", lang: "en" });
    expect(res.kind).toBe("answer");
    expect(res.meta.mock).toBe(true);
    const section = res.sections[0]!;
    expect(section.summary.fee_text).toBe("₱235.50");
    expect(section.checklist.length).toBe(section.summary.requirement_count);
    expect(section.fees).toHaveLength(4);
    expect(section.related[0]?.office).toBe("City Health Office");
  });

  it("returns pending_lgu sections without any numbers", async () => {
    for (const message of ["birth registration", "death registration"]) {
      const s = (await fx.chat({ message, lang: "en" })).sections[0]!;
      expect(s.info_status).toBe("pending_lgu");
      expect(s.summary).toEqual({ requirement_count: null, fee_text: null, time_text: null });
      expect([s.checklist, s.fees, s.steps]).toEqual([[], [], []]);
    }
  });

  it("splits a multi-service message into one section each", async () => {
    const res = await fx.chat({ message: "sanitary permit and medical certificate", lang: "en" });
    expect(res.sections.map((s) => s.service_id)).toEqual([
      "cho_sanitary_permit",
      "cho_medical_certificate",
    ]);
  });

  it("clarifies, and every clarify option round-trips to an answer", async () => {
    const res = await fx.chat({ message: "permit", lang: "en" });
    expect(res.kind).toBe("clarify");
    for (const option of res.clarify_options) {
      expect((await fx.chat({ message: option, lang: "en" })).kind).toBe("answer");
    }
  });

  it("falls back or refuses, never leaves a dead end", async () => {
    expect((await fx.chat({ message: "what is the weather", lang: "en" })).kind).toBe("fallback");
    expect((await fx.chat({ message: "delete everything", lang: "en" })).kind).toBe("refusal");
  });

  it("replies in the requested language", async () => {
    const res = await fx.chat({ message: "hello", lang: "fil" });
    expect(res.language).toBe("fil");
    expect(res.text).toBe(fixtures.text.fil.clarify);
  });

  it("gives the same answers as the Python mock (parity cases)", () => {
    for (const c of fixtures.cases) {
      const r = mockChat(c.message, c.lang as Lang);
      expect({ kind: r.kind, ids: r.serviceIds, clarify: r.clarifyIds }, `${c.message} (${c.lang})`).toEqual({
        kind: c.kind,
        ids: c.service_ids,
        clarify: c.clarify_ids,
      });
    }
  });
});

function fakeReal(overrides: Partial<ApiClient> = {}): ApiClient {
  return {
    mode: "real",
    services: vi.fn().mockResolvedValue([]),
    health: vi.fn().mockResolvedValue({ status: "ok", mock: false }),
    chat: vi.fn().mockResolvedValue({ kind: "answer", meta: {} }),
    ...overrides,
  } as ApiClient;
}

describe("api client", () => {
  it("uses fixtures only when VITE_USE_FIXTURES-style option is set", async () => {
    const real = fakeReal();
    const client = createApiClient({ useFixtures: true, real });
    await client.services();
    expect(real.services).not.toHaveBeenCalled();
    expect(client.mode).toBe("fixtures");
  });

  it("uses the real API when it answers", async () => {
    const real = fakeReal();
    const client = createApiClient({ useFixtures: false, real });
    await client.chat({ message: "x", lang: "en" });
    expect(real.chat).toHaveBeenCalled();
    expect(client.mode).toBe("real");
  });

  it("falls back to fixtures when the API is unreachable, then retries later", async () => {
    let time = 0;
    const down = vi.fn().mockRejectedValue(new ApiUnreachableError("HTTP 500"));
    const real = fakeReal({ services: down });
    const client = createApiClient({ useFixtures: false, real, retryAfterMs: 1000, now: () => time });

    expect(await client.services()).toHaveLength(6);
    expect(client.mode).toBe("fixtures");
    await client.services();
    expect(down).toHaveBeenCalledTimes(1); // still inside the retry window

    time = 2000;
    await client.services();
    expect(down).toHaveBeenCalledTimes(2);
  });

  it("does not hide real API errors that are not connectivity problems", async () => {
    const real = fakeReal({ chat: vi.fn().mockRejectedValue(new Error("HTTP 422")) });
    const client = createApiClient({ useFixtures: false, real });
    await expect(client.chat({ message: "x", lang: "en" })).rejects.toThrow("HTTP 422");
  });
});
