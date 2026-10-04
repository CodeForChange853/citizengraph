import { readFileSync } from "node:fs";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { AppRoutes } from "../App";
import i18n, { LANG_KEY, setLanguage } from "../i18n";
import { LANDING_FIL_ENABLED } from "../landing/copy";
import landingEn from "../landing/i18n/en.json";
import landingFil from "../landing/i18n/fil.json";
import { SCENES } from "../landing/scenes";
import { landing, setReducedMotion } from "../landing/testHelpers";
import { renderApp } from "../test/utils";

beforeEach(() => setReducedMotion(false));

describe("landing route", () => {
  it("opens at /welcome outside the app shell, with the prototype label and the call to action to /", async () => {
    await landing();
    expect(screen.queryByRole("navigation", { name: "Main menu" })).not.toBeInTheDocument();
    expect(screen.getAllByText("Thesis prototype, not an official government app").length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /Start asking/ })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "For reviewers" })).toHaveAttribute("href", "/help");
  });

  it("still shows the home screen inside the shell at /", async () => {
    renderApp(<AppRoutes />);
    expect(await screen.findByLabelText("What do you need to do?")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Main menu" })).toBeInTheDocument();
    expect(document.querySelector(".lp")).toBeNull();
  });

  it("tells the story as nine labelled sections in order, with one h1", async () => {
    const root = await landing();
    const sections = [...root.querySelectorAll<HTMLElement>("section[data-scene]")];
    expect(sections.map((s) => s.dataset.scene)).toEqual(SCENES.map((s) => s.id));
    for (const section of sections) expect(document.getElementById(section.getAttribute("aria-labelledby")!)).not.toBeNull();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Two cores. One answer.");
  });
});

describe("landing language lock", () => {
  it("has no Filipino copy: the stub is empty and the review list has no landing strings", () => {
    expect(landingFil).toEqual({});
    expect(Object.keys(landingEn.scenes)).toHaveLength(SCENES.length);
    expect(readFileSync("NEEDS-NATIVE-REVIEW.md", "utf8")).not.toMatch(/landing\./);
    expect(LANDING_FIL_ENABLED).toBe(false);
  });

  it("stays in English when the app is in Filipino, and leaves the app's stored language alone", async () => {
    await setLanguage("fil");
    const user = userEvent.setup();
    const root = await landing();
    expect(root).toHaveAttribute("lang", "en");
    expect(screen.getByRole("link", { name: /Start asking/ })).toBeInTheDocument();
    expect(screen.getByText("Sample data")).toBeInTheDocument(); // the app's own tag, in English here
    const fil = screen.getByRole("button", { name: "Filipino" });
    expect(fil).toHaveAttribute("aria-disabled", "true");
    await user.click(fil);
    expect(screen.getByRole("link", { name: /Start asking/ })).toBeInTheDocument();
    expect(i18n.language).toBe("fil");
    expect(localStorage.getItem(LANG_KEY)).toBe("fil");
  });

  it("marks the Taglish sample question for native review", () => {
    expect(readFileSync("src/landing/SceneText.tsx", "utf8")).toMatch(/NEEDS-NATIVE-REVIEW.*\r?\nexport const SAMPLE_QUESTION/);
  });
});
