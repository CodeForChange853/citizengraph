import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ChecklistCard } from "./ChecklistCard";
import { ClarifyButtons } from "./ClarifyButtons";
import { FallbackCard } from "./FallbackCard";
import { InfoScent } from "./InfoScent";
import { LanguageToggle } from "./LanguageToggle";
import { OfflineBanner } from "./OfflineBanner";
import { PendingBanner } from "./PendingBanner";
import { SampleDataTag } from "./SampleDataTag";
import i18n from "../i18n";
import { CHECKLIST_KEY } from "../lib/checklistStore";

const meta = {
  serviceId: "t1",
  name: "Test service",
  office: "Test office",
  items: ["Form", "ID", "Photo"],
};

describe("checklist", () => {
  it("counts ticked items and shows progress", async () => {
    const user = userEvent.setup();
    render(<ChecklistCard meta={meta} />);
    expect(screen.getByText("0 of 3 ready")).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: "Form" }));
    await user.click(screen.getByRole("checkbox", { name: "ID" }));
    expect(screen.getByText("2 of 3 ready")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "2");
    await user.click(screen.getByRole("checkbox", { name: "ID" }));
    expect(screen.getByText("1 of 3 ready")).toBeInTheDocument();
  });

  it("saves ticks on the device and restores them", async () => {
    const user = userEvent.setup();
    const first = render(<ChecklistCard meta={meta} />);
    await user.click(screen.getByRole("checkbox", { name: "Photo" }));
    const saved = JSON.parse(localStorage.getItem(CHECKLIST_KEY) ?? "{}");
    expect(saved.t1.ticked).toEqual(["Photo"]);
    first.unmount();

    render(<ChecklistCard meta={meta} />);
    expect(screen.getByRole("checkbox", { name: "Photo" })).toBeChecked();
    expect(screen.getByText("1 of 3 ready")).toBeInTheDocument();
  });

  it("lets the citizen keep a list without ticking anything", async () => {
    const user = userEvent.setup();
    render(<ChecklistCard meta={meta} />);
    await user.click(screen.getByRole("button", { name: /keep this list/i }));
    expect(JSON.parse(localStorage.getItem(CHECKLIST_KEY) ?? "{}").t1.items).toEqual(meta.items);
    expect(screen.getByText("Saved on this phone")).toBeInTheDocument();
  });

  it("says so when the office lists nothing to bring", () => {
    render(<ChecklistCard meta={{ ...meta, items: [] }} />);
    expect(screen.getByText(/lists no documents/i)).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });
});

describe("language toggle", () => {
  it("switches the screen language and remembers it", async () => {
    const user = userEvent.setup();
    render(
      <>
        <LanguageToggle />
        <PendingBanner />
      </>,
    );
    expect(screen.getByText("Being checked")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Filipino" }));
    expect(screen.getByText("Sinusuri pa")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Filipino" })).toHaveAttribute("aria-pressed", "true");
    expect(localStorage.getItem("cg.lang")).toBe("fil");
    expect(document.documentElement.lang).toBe("fil");
    await user.click(screen.getByRole("button", { name: "English" }));
    expect(i18n.language).toBe("en");
  });
});

describe("pending_lgu", () => {
  const numbers = { requirement_count: 9, fee_text: "₱235.50", time_text: "37 minutes" };

  it("hides every number, even if the API sent some", () => {
    const { container } = render(<InfoScent summary={numbers} status="pending_lgu" />);
    expect(container).toHaveTextContent("Being checked with the office");
    expect(container).not.toHaveTextContent(/₱|235|37|requirement/);
  });

  it("shows the information scent line for confirmed services", () => {
    const { container } = render(<InfoScent summary={numbers} status="confirmed" />);
    expect(container).toHaveTextContent("9 requirements · ₱235.50 · about 37 minutes");
  });

  it("does not turn a missing fee into 'free'", () => {
    const { container } = render(
      <InfoScent summary={{ ...numbers, fee_text: null }} status="confirmed" />,
    );
    expect(container).toHaveTextContent("fee not listed");
    expect(container).not.toHaveTextContent(/free/i);
  });

  it("shows the calm banner text", () => {
    render(<PendingBanner />);
    expect(
      screen.getByText(
        "This checklist is being verified with the office. Please confirm with them before you go.",
      ),
    ).toBeInTheDocument();
  });
});

describe("clarify flow", () => {
  it("sends the tapped option back", async () => {
    const user = userEvent.setup();
    const onPick = vi.fn();
    render(<ClarifyButtons options={["Business Permit", "Sanitary Permit"]} onPick={onPick} />);
    const group = screen.getByRole("region");
    await user.click(within(group).getByRole("button", { name: "Sanitary Permit" }));
    expect(onPick).toHaveBeenCalledWith("Sanitary Permit");
  });

  it("fallback card offers the four topics", async () => {
    const user = userEvent.setup();
    const onPickGroup = vi.fn();
    render(<FallbackCard onPickGroup={onPickGroup} />);
    expect(screen.getAllByRole("button")).toHaveLength(4);
    await user.click(screen.getByRole("button", { name: "Health" }));
    expect(onPickGroup).toHaveBeenCalledWith("health");
  });
});

describe("offline banner", () => {
  it("appears when the connection drops and goes away when it returns", () => {
    const online = vi.spyOn(navigator, "onLine", "get");
    online.mockReturnValue(true);
    render(<OfflineBanner />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();

    online.mockReturnValue(false);
    act(() => {
      window.dispatchEvent(new Event("offline"));
    });
    expect(screen.getByRole("status")).toHaveTextContent("You are offline");

    online.mockReturnValue(true);
    act(() => {
      window.dispatchEvent(new Event("online"));
    });
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    online.mockRestore();
  });
});

describe("sample data tag", () => {
  it("shows only when meta.mock is true", () => {
    const { rerender } = render(<SampleDataTag meta={{ mock: true }} />);
    expect(screen.getByText("Sample data")).toBeInTheDocument();
    rerender(<SampleDataTag meta={{}} />);
    expect(screen.queryByText("Sample data")).not.toBeInTheDocument();
  });
});
