import { act, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { existsSync, readFileSync } from "node:fs";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppRoutes } from "../App";
import { CHECKLIST_KEY, reloadChecklists } from "../lib/checklistStore";
import { renderApp } from "../test/utils";
import manifestSource from "../../vite.config.ts?raw";

const ITEMS = ["Application Form", "Valid ID"];

function seedSaved(ticked: string[] = []) {
  localStorage.setItem(
    CHECKLIST_KEY,
    JSON.stringify({
      demo: { serviceId: "demo", name: "Demo Permit", office: "Demo Office", items: ITEMS, ticked, updatedAt: 1 },
    }),
  );
  reloadChecklists();
}

describe("saved lists", () => {
  it("explains itself when empty and offers a way to ask", async () => {
    const user = userEvent.setup();
    renderApp(<AppRoutes />, { route: "/saved" });
    expect(screen.getByText(/Nothing saved yet/)).toBeInTheDocument();
    expect(screen.getByText("Saved lists stay on this phone. There is no account.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Ask a question" }));
    expect(await screen.findByLabelText("What do you need to do?")).toBeInTheDocument();
  });

  it("shows saved lists with progress, restored from the device, without calling the API", async () => {
    seedSaved(["Valid ID"]);
    const base = (await import("../api/fixtureAdapter")).createFixtureAdapter();
    const client = { ...base, chat: vi.fn(), services: vi.fn(), health: vi.fn() };
    renderApp(<AppRoutes />, { route: "/saved", client });
    const card = within(screen.getByRole("article", { name: "Demo Permit" }));
    expect(card.getAllByText("1 of 2 ready").length).toBeGreaterThan(0);
    expect(card.getByRole("checkbox", { name: "Valid ID" })).toBeChecked();
    expect(client.chat).not.toHaveBeenCalled();
    expect(client.services).not.toHaveBeenCalled();
  });

  it("ticking here updates the saved copy", async () => {
    const user = userEvent.setup();
    seedSaved();
    renderApp(<AppRoutes />, { route: "/saved" });
    const card = within(screen.getByRole("article", { name: "Demo Permit" }));
    await user.click(card.getByRole("checkbox", { name: "Application Form" }));
    expect(card.getAllByText("1 of 2 ready").length).toBeGreaterThan(0);
    expect(JSON.parse(localStorage.getItem(CHECKLIST_KEY)!).demo.ticked).toEqual(["Application Form"]);
  });

  it("removing asks first, and Keep it cancels", async () => {
    const user = userEvent.setup();
    seedSaved();
    renderApp(<AppRoutes />, { route: "/saved" });
    await user.click(screen.getByRole("button", { name: "Remove" }));
    await user.click(screen.getByRole("button", { name: "Keep it" }));
    expect(screen.getByRole("article", { name: "Demo Permit" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Remove" }));
    await user.click(screen.getByRole("button", { name: "Yes, remove" }));
    expect(screen.queryByRole("article", { name: "Demo Permit" })).not.toBeInTheDocument();
    expect(JSON.parse(localStorage.getItem(CHECKLIST_KEY)!)).toEqual({});
    expect(screen.getByText(/Nothing saved yet/)).toBeInTheDocument();
  });

  it("a list ticked from an answer appears in Saved", async () => {
    const user = userEvent.setup();
    renderApp(<AppRoutes />, { route: "/chat", state: { message: "medical certificate" } });
    await screen.findByRole("article", { name: "Medical Certificate (for employment)" });
    // no documents listed, so there is nothing to tick; referrals has items
    await user.click(screen.getByRole("button", { name: "New question" }));
    await user.type(await screen.findByLabelText("What do you need to do?"), "referral{Enter}");
    const article = await screen.findByRole("article", { name: "Referrals" });
    await user.click(within(article).getByRole("checkbox", { name: "Medical Abstract" }));
    await user.click(screen.getByRole("link", { name: "Saved" }));
    expect(await screen.findByRole("article", { name: "Referrals" })).toHaveTextContent("1 of 5 ready");
  });
});

describe("help", () => {
  it("states it is a thesis prototype, needs no login and keeps saved lists on the phone", () => {
    renderApp(<AppRoutes />, { route: "/help" });
    expect(screen.getAllByText("Thesis prototype, not an official government app").length).toBeGreaterThan(0);
    expect(screen.getByText("There is no login and no account.")).toBeInTheDocument();
    expect(screen.getByText(/stay on this phone only/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "If a list says it is being checked" })).toBeInTheDocument();
  });

  it("changes theme and text size and remembers them", async () => {
    const user = userEvent.setup();
    renderApp(<AppRoutes />, { route: "/help" });
    const help = within(screen.getByRole("heading", { name: "Display and language" }).closest("section")!);
    await user.click(help.getByRole("button", { name: "Dark" }));
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    await user.click(help.getByRole("button", { name: "Large" }));
    expect(document.documentElement).toHaveAttribute("data-text-size", "large");
    expect(JSON.parse(localStorage.getItem("cg.settings.v1")!)).toEqual({ theme: "dark", textSize: "large" });
    await user.click(help.getByRole("button", { name: "Match my phone" }));
    expect(document.documentElement).not.toHaveAttribute("data-theme");
  });

  it("switches language from the help page", async () => {
    const user = userEvent.setup();
    renderApp(<AppRoutes />, { route: "/help" });
    await user.click(within(screen.getByRole("banner")).getByRole("button", { name: "Filipino" }));
    expect(screen.getByRole("heading", { name: "Tulong", level: 1 })).toBeInTheDocument();
  });
});

describe("offline", () => {
  let onLine: ReturnType<typeof vi.spyOn> | undefined;
  afterEach(() => onLine?.mockRestore());

  function goOffline() {
    onLine = vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    act(() => {
      window.dispatchEvent(new Event("offline"));
    });
  }

  it("shows the banner in every screen, and saved lists still open", async () => {
    seedSaved();
    renderApp(<AppRoutes />, { route: "/saved" });
    goOffline();
    expect(screen.getByRole("status")).toHaveTextContent("You are offline. Lists you saved still work.");
    expect(screen.getByRole("article", { name: "Demo Permit" })).toBeInTheDocument();
  });

  it("home cannot send a question while offline and says why", async () => {
    const user = userEvent.setup();
    renderApp(<AppRoutes />, { route: "/" });
    await screen.findByText("Business Permit");
    goOffline();
    expect(screen.getByRole("button", { name: "Ask" })).toBeDisabled();
    expect(screen.getByText(/You can still read your saved lists/)).toBeInTheDocument();
    await user.type(screen.getByLabelText("What do you need to do?"), "business permit{Enter}");
    expect(screen.queryByRole("heading", { name: "Ask", level: 1 })).not.toBeInTheDocument();
  });

  it("still loads the services when the phone starts offline", async () => {
    onLine = vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    renderApp(<AppRoutes />, { route: "/" });
    expect(await screen.findByText("Business Permit")).toBeInTheDocument();
  });

  it("the chat input is disabled while offline, and the last answers stay readable", async () => {
    renderApp(<AppRoutes />, { route: "/chat", state: { message: "business permit" } });
    await screen.findByRole("article", { name: "Business Permit" });
    goOffline();
    expect(screen.getByLabelText("Your question")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    expect(screen.getByRole("article", { name: "Business Permit" })).toBeInTheDocument();
  });
});

describe("PWA setup", () => {
  it("ships the icons the manifest points to", () => {
    for (const file of ["pwa-192x192.png", "pwa-512x512.png", "maskable-512x512.png", "apple-touch-icon.png", "icon.svg"]) {
      expect(existsSync(`public/${file}`), file).toBe(true);
      expect(manifestSource).toContain(file.replace("apple-touch-icon.png", "apple-touch-icon.png"));
    }
  });

  it("does not cache chat requests and keeps the app shell available offline", () => {
    expect(manifestSource).toContain('registerType: "autoUpdate"');
    expect(manifestSource).toContain('navigateFallback: "/index.html"');
    expect(manifestSource).toContain('"/api/services"');
    expect(manifestSource).not.toContain("/api/chat");
    expect(readFileSync("index.html", "utf8")).toContain("apple-touch-icon");
  });

  it("uses no government marks in the icon", () => {
    const svg = readFileSync("public/icon.svg", "utf8");
    expect(svg).toContain(">CG<");
    expect(svg).not.toMatch(/star|sun|flag|seal/i);
  });
});
