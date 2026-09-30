import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AppRoutes } from "../App";
import { createFixtureAdapter } from "../api/fixtureAdapter";
import { CHAT_KEY } from "../lib/chatStore";
import { CHECKLIST_KEY } from "../lib/checklistStore";
import { renderApp } from "../test/utils";

function openChat(message?: string, client = createFixtureAdapter()) {
  return renderApp(<AppRoutes />, { route: "/chat", state: message ? { message } : undefined, client });
}

describe("answer card", () => {
  it("shows summary, checklist, fees, steps, where to go and the related route, in that order", async () => {
    openChat("business permit");
    const c = within(await screen.findByRole("article", { name: "Business Permit" }));
    const headings = c.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(headings).toEqual(["What to bring", "What it costs", "Steps", "Where to go", "You will also need"]);
    expect(c.getByText("14 requirements · ₱235.50 · about 37 minutes")).toBeInTheDocument();
    expect(c.getByText("0 of 14 ready")).toBeInTheDocument();
  });

  it("lists fees with a total that matches the fees", async () => {
    openChat("business permit");
    const c = within(await screen.findByRole("article", { name: "Business Permit" }));
    expect(c.getByText("Zoning")).toBeInTheDocument();
    expect(c.getAllByText("₱100.00")).toHaveLength(2);
    expect(c.getAllByText("₱235.50").length).toBeGreaterThan(0);
    expect(c.getByText("Total")).toBeInTheDocument();
  });

  it("shows each step with its time, and marks steps at another office", async () => {
    openChat("business permit");
    const c = within(await screen.findByRole("article", { name: "Business Permit" }));
    expect(c.getByText("Time: 5-10 minutes")).toBeInTheDocument();
    expect(c.getAllByText("Time not listed").length).toBe(2);
    expect(c.getByText("At another office")).toBeInTheDocument();
  });

  it("shows where to go as office chips and the cross-office route", async () => {
    openChat("business permit");
    const c = within(await screen.findByRole("article", { name: "Business Permit" }));
    const where = c.getByRole("heading", { name: "Where to go" }).closest("section")!;
    expect(within(where).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Business Permits & Licensing Office",
      "City Health Office",
    ]);
    const also = c.getByRole("heading", { name: "You will also need" }).closest("section")!;
    expect(also).toHaveTextContent("Go to City Health Office first");
    expect(also).toHaveTextContent("Sanitary Permit to Operate");
  });

  it("ticks are saved on the device and progress updates", async () => {
    const user = userEvent.setup();
    openChat("business permit");
    const c = within(await screen.findByRole("article", { name: "Business Permit" }));
    await user.click(c.getByRole("checkbox", { name: "City Solid Waste Certification" }));
    expect(c.getByText("1 of 14 ready")).toBeInTheDocument();
    expect(JSON.parse(localStorage.getItem(CHECKLIST_KEY)!).business_permit.ticked).toEqual([
      "City Solid Waste Certification",
    ]);
  });

  it("says fee not listed and the office lists nothing to bring, without inventing anything", async () => {
    openChat("sanitary permit");
    const c = within(await screen.findByRole("article", { name: "Sanitary Permit" }));
    expect(c.getByText(/does not list a fee/)).toBeInTheDocument();
    expect(c.getByText("1 requirement · fee not listed · about 3 days, 10 minutes")).toBeInTheDocument();
  });

  it("pending_lgu: calm banner, office only, no numbers", async () => {
    openChat("death registration");
    const article = await screen.findByRole("article", { name: "Death Registration (timely)" });
    const c = within(article);
    expect(c.getByRole("note")).toHaveTextContent(
      "This checklist is being verified with the office. Please confirm with them before you go.",
    );
    expect(article).not.toHaveTextContent(/₱|\d/);
    expect(c.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(c.getByText("Civil Registry Office")).toBeInTheDocument();
  });

  it("hides numbers for a pending service even if the API sends some", async () => {
    const base = createFixtureAdapter();
    const client = {
      ...base,
      chat: async (req: Parameters<typeof base.chat>[0]) => {
        const res = await base.chat(req);
        res.sections = res.sections.map((s) => ({
          ...s,
          summary: { requirement_count: 2, fee_text: "₱999.00", time_text: "5 minutes" },
          checklist: ["Leaked item"],
          fees: [{ label: "Leaked fee", amount_text: "₱999.00" }],
          steps: [{ order: 1, text: "Leaked step", time_text: "5 minutes", external: false }],
        }));
        return res;
      },
    };
    openChat("birth registration", client);
    const c = await screen.findByRole("article", { name: "Birth Registration (timely)" });
    expect(c).not.toHaveTextContent(/Leaked|₱|999/);
  });

  it("shows multi-service answers as separate cards and the sample data tag", async () => {
    openChat("business permit and medical certificate");
    expect(await screen.findByRole("article", { name: "Business Permit" })).toBeInTheDocument();
    expect(screen.getByRole("article", { name: "Medical Certificate (for employment)" })).toBeInTheDocument();
    expect(screen.getByText("Sample data")).toBeInTheDocument();
  });
});

describe("clarify and fallback flows", () => {
  it("clarify: tapping an option sends it and shows the answer", async () => {
    const user = userEvent.setup();
    openChat("permit");
    const options = await screen.findByRole("region", { name: "Which one do you need?" });
    await user.click(within(options).getByRole("button", { name: "Sanitary Permit" }));
    expect(await screen.findByRole("article", { name: "Sanitary Permit" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Which one do you need?" })).not.toBeInTheDocument();
  });

  it("fallback: never a dead end. A topic chip leads to services, then to an answer", async () => {
    const user = userEvent.setup();
    openChat("what is the weather");
    expect(await screen.findByText("I could not match that")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Health" }));
    const options = await screen.findByRole("region", { name: "Which one do you need?" });
    await user.click(within(options).getByRole("button", { name: "Medical Certificate (for employment)" }));
    expect(await screen.findByRole("article", { name: "Medical Certificate (for employment)" })).toBeInTheDocument();
  });

  it("refusal: says it can only look things up and offers topics", async () => {
    openChat("delete everything");
    expect(await screen.findByText("I can only look things up")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /Business|Family records|Health|Help and assistance/ })).toHaveLength(4);
  });

  it("follow-up questions keep the session", async () => {
    const user = userEvent.setup();
    const base = createFixtureAdapter();
    const chat = vi.fn(base.chat);
    openChat("business permit", { ...base, chat });
    await screen.findByRole("article", { name: "Business Permit" });
    await user.type(screen.getByLabelText("Your question"), "sanitary permit{Enter}");
    await screen.findByRole("article", { name: "Sanitary Permit" });
    const [first, second] = chat.mock.calls.map((c) => c[0]);
    expect(first?.session_id).toBeNull();
    expect(second?.session_id).toBeTruthy();
  });
});

describe("chat behaviour", () => {
  it("asks in the chosen language", async () => {
    const user = userEvent.setup();
    openChat();
    await user.click(screen.getByRole("button", { name: "Filipino" }));
    await user.type(screen.getByLabelText("Ang tanong mo"), "hello{Enter}");
    expect(await screen.findByRole("region", { name: "Alin ang kailangan mo?" })).toBeInTheDocument();
  });

  it("shows an error card and retries the same question", async () => {
    const user = userEvent.setup();
    const base = createFixtureAdapter();
    let fail = true;
    const client = {
      ...base,
      chat: async (req: Parameters<typeof base.chat>[0]) => {
        if (fail) throw new Error("down");
        return base.chat(req);
      },
    };
    openChat("business permit", client);
    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong. Please try again.");
    fail = false;
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("article", { name: "Business Permit" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("keeps the last answers on the device so they can be read offline", async () => {
    openChat("business permit");
    await screen.findByRole("article", { name: "Business Permit" });
    await waitFor(() => expect(localStorage.getItem(CHAT_KEY)).toContain("business_permit"));
    const saved = JSON.parse(localStorage.getItem(CHAT_KEY)!);
    expect(saved.turns.map((t: { role: string }) => t.role)).toEqual(["user", "assistant"]);
  });

  it("New question clears the conversation and returns to the ask box", async () => {
    const user = userEvent.setup();
    openChat("business permit");
    await screen.findByRole("article", { name: "Business Permit" });
    await user.click(screen.getByRole("button", { name: "New question" }));
    expect(await screen.findByLabelText("What do you need to do?")).toBeInTheDocument();
    expect(JSON.parse(localStorage.getItem(CHAT_KEY)!).turns).toEqual([]);
  });
});
