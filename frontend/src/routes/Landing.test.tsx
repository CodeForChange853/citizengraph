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

describe("landing navigation and fallbacks", () => {
  it("puts the skip link first in the tab order, pointing at the call to action", async () => {
    const user = userEvent.setup();
    await landing();
    await user.tab();
    expect(document.activeElement).toHaveTextContent("Skip to the app");
    expect(document.activeElement).toHaveAttribute("href", "#lp-cta");
    expect(document.getElementById("lp-cta")).toHaveAttribute("href", "/");
  });

  it("has a chapter link for every scene, each to a real anchor in the scroll track", async () => {
    await landing();
    const links = [...screen.getByRole("navigation", { name: "Chapters" }).querySelectorAll("a")];
    expect(links).toHaveLength(SCENES.length);
    for (const link of links) {
      const target = document.getElementById(link.getAttribute("href")!.slice(1));
      expect(target?.closest(".lp-track")).not.toBeNull();
      expect(link.getAttribute("aria-label")).toMatch(/^\d\. /);
    }
  });

  it("offers the film and stops it again from the same button", async () => {
    const user = userEvent.setup();
    const root = await landing();
    window.scrollTo = () => {};
    await user.click(screen.getByRole("button", { name: /Watch the film/ }));
    expect(root.dataset.filming).toBe("true");
    await user.click(screen.getByRole("button", { name: /Stop the film/ }));
    expect(root.dataset.filming).toBe("false");
  });

  it("falls back to still posters when WebGL is not there, and loads no 3D picture", async () => {
    const root = await landing(); // jsdom has no WebGL
    expect(root.dataset.gl).toBe("off");
    expect(root.querySelector("canvas")).toBeNull();
    const posters = [...root.querySelectorAll("svg[role=img]")];
    expect(posters).toHaveLength(SCENES.length);
    for (const poster of posters) expect(poster.getAttribute("aria-label")!.length).toBeGreaterThan(20);
  });

  it("with reduced motion shows nine still, readable sections: no pinned stage, film, chapter dots or canvas", async () => {
    setReducedMotion(true);
    const root = await landing();
    expect(root.dataset.motion).toBe("static");
    expect(root.querySelector("canvas")).toBeNull();
    expect(screen.queryByRole("button", { name: /film/ })).toBeNull();
    expect(screen.queryByRole("navigation", { name: "Chapters" })).toBeNull();
    const sections = [...root.querySelectorAll<HTMLElement>("section[data-scene]")];
    expect(sections).toHaveLength(SCENES.length);
    for (const section of sections) expect(section.dataset.active).toBe("true");
    // every headline word has landed and every checklist item is ticked
    expect(root.querySelectorAll('.lp-word:not([data-state="on"])')).toHaveLength(0);
    expect(root.querySelectorAll('.lp-row[data-on="true"]')).toHaveLength(4);
    expect(screen.getByText("Early heads-up, drafted for staff review")).toBeInTheDocument();
    expect(screen.getByText("Prototype feature")).toBeInTheDocument();
  });

  it("puts the sample card under the app's sample tag with neutral placeholders", async () => {
    const root = await landing();
    const card = root.querySelector<HTMLElement>(".lp-card")!;
    expect(card).toHaveTextContent("Sample data");
    expect(card.textContent).not.toMatch(/\d|₱/);
    expect(card.querySelectorAll(".lp-row")).toHaveLength(4);
  });
});

describe("landing frame loop", () => {
  it("keeps one frame callback pending at a time, however long the story runs", async () => {
    const pending: FrameRequestCallback[] = [];
    const realRaf = window.requestAnimationFrame;
    window.requestAnimationFrame = (fn) => pending.push(fn);
    try {
      await landing();
      let now = 1000;
      for (let frame = 0; frame < 120; frame++) {
        const batch = pending.splice(0);
        now += 16;
        for (const fn of batch) fn(now);
        expect(pending.length, `frame ${frame}`).toBeLessThanOrEqual(1);
      }
    } finally {
      window.requestAnimationFrame = realRaf;
    }
  });
});
