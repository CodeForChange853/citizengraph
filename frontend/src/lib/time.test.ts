import { describe, expect, it } from "vitest";
import i18n from "../i18n";
import { localizeTime } from "./time";

const fil = i18n.getFixedT("fil");

describe("localizeTime (Filipino units)", () => {
  it.each([
    ["5 minutes", "5 minuto"],
    ["1 minute", "1 minuto"],
    ["2 hours", "2 oras"],
    ["1 hour", "1 oras"],
    ["3 days", "3 araw"],
    ["1 week", "1 linggo"],
    ["37 minutes", "37 minuto"],
    ["5 Minutes", "5 minuto"],
  ])("%s -> %s", (input, expected) => {
    expect(localizeTime(input, "fil", fil)).toBe(expected);
  });

  it("localizes ranges and keeps both numbers as given", () => {
    expect(localizeTime("5-10 minutes", "fil", fil)).toBe("5-10 minuto");
    expect(localizeTime("3-5 minutes", "fil", fil)).toBe("3-5 minuto");
    expect(localizeTime("2 – 3 minutes", "fil", fil)).toBe("2 – 3 minuto");
  });

  it("localizes lists and keeps the separators", () => {
    expect(localizeTime("3 days, 10 minutes", "fil", fil)).toBe("3 araw, 10 minuto");
    expect(localizeTime("1 week, 1 hour, 40 minutes", "fil", fil)).toBe("1 linggo, 1 oras, 40 minuto");
    expect(localizeTime("1-2 hours, 5 minutes", "fil", fil)).toBe("1-2 oras, 5 minuto");
  });

  it("keeps numbers exactly as given (no rounding, no padding changes)", () => {
    expect(localizeTime("1.5 hours", "fil", fil)).toBe("1.5 oras");
    expect(localizeTime("05 minutes", "fil", fil)).toBe("05 minuto");
    expect(localizeTime("10 minutes", "fil", fil)).not.toMatch(/ sampu|10\.0/);
  });

  it.each([
    "1 hour (Once a month)",
    "working days",
    "3 working days",
    "about 5 minutes",
    "3 days and 10 minutes",
    "5 fortnights",
    "5 minuto",
    "minutes",
    "",
    "Not stated",
  ])("leaves unknown text unchanged: %j", (input) => {
    expect(localizeTime(input, "fil", fil)).toBe(input);
  });

  it("never half translates a list that has one part it does not know", () => {
    expect(localizeTime("3 days, 10 minutes (estimate)", "fil", fil)).toBe("3 days, 10 minutes (estimate)");
    expect(localizeTime("3 days, varies", "fil", fil)).toBe("3 days, varies");
  });

  it("returns English as given", () => {
    expect(localizeTime("5-10 minutes", "en", i18n.getFixedT("en"))).toBe("5-10 minutes");
    expect(localizeTime("3 days, 10 minutes", "en", i18n.getFixedT("en"))).toBe("3 days, 10 minutes");
  });
});
