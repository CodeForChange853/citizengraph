import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { AppRoutes } from "../App";
import { createFixtureAdapter } from "../api/fixtureAdapter";
import { renderApp } from "../test/utils";

const row = (name: string) => screen.queryByRole("button", { name: new RegExp(`^${name}(?![a-z])`) });
const getRow = (name: string) => row(name)!;

async function home() {
  renderApp(<AppRoutes />);
  await screen.findByText("Business Permit");
}

describe("home screen", () => {
  it("asks 'What do you need to do?' first and lists services with an information scent line", async () => {
    await home();
    expect(screen.getByLabelText("What do you need to do?")).toBeInTheDocument();
    const row = getRow("Sanitary Permit");
    expect(row).toHaveTextContent("1 requirement · fee not listed · about 3 days, 10 minutes");
    expect(row).toHaveTextContent("City Health Office");
  });

  it("shows pending services without numbers", async () => {
    await home();
    for (const name of ["Death Registration", "Birth Registration", "Business Permit"]) {
      const row = getRow(name);
      expect(row).toHaveTextContent("Being checked with the office");
      expect(row).not.toHaveTextContent(/\d/);
    }
  });

  it("does not turn a missing fee into 'free'", async () => {
    await home();
    const row = getRow("Referrals");
    expect(row).toHaveTextContent("5 requirements · fee not listed · about 1 week, 1 hour, 40 minutes");
  });

  it("groups services by life event and filters with topic chips", async () => {
    const user = userEvent.setup();
    await home();
    expect(screen.getByRole("heading", { name: "Health", level: 3 })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Family records" }));
    expect(getRow("Birth Registration")).toBeInTheDocument();
    expect(row("Business Permit")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Family records" }));
    expect(getRow("Business Permit")).toBeInTheDocument();
  });

  it("offices are secondary chips that filter too", async () => {
    const user = userEvent.setup();
    await home();
    const offices = screen.getByRole("heading", { name: "Or choose an office" }).closest("section")!;
    await user.click(within(offices).getByRole("button", { name: "City Health Office" }));
    expect(getRow("Sanitary Permit")).toBeInTheDocument();
    expect(row("Referrals")).not.toBeInTheDocument();
  });

  it("sends the question to the chat screen", async () => {
    const user = userEvent.setup();
    await home();
    await user.type(screen.getByLabelText("What do you need to do?"), "business permit{Enter}");
    expect(await screen.findByRole("heading", { name: "Ask", level: 1 })).toBeInTheDocument();
  });

  it("tapping a service row opens it in chat", async () => {
    const user = userEvent.setup();
    await home();
    await user.click(getRow("Sanitary Permit"));
    expect(await screen.findByRole("heading", { name: "Ask", level: 1 })).toBeInTheDocument();
  });

  it("marks the sample data and reads in Filipino when toggled", async () => {
    const user = userEvent.setup();
    await home();
    expect(screen.getByText("Sample data")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Filipino" }));
    expect(screen.getByLabelText("Ano ang kailangan mong gawin?")).toBeInTheDocument();
    expect(screen.getByText("Prototype para sa thesis, hindi opisyal na app ng gobyerno")).toBeInTheDocument();
  });

  it("keeps the prototype label and a three-item bottom nav on screen", async () => {
    await home();
    expect(screen.getByText("Thesis prototype, not an official government app")).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Main menu" });
    expect(within(nav).getAllByRole("link").map((a) => a.textContent)).toEqual(["Ask", "Saved", "Help"]);
    expect(within(nav).getByRole("link", { name: "Ask" })).toHaveAttribute("aria-current", "page");
  });

  it("sets the prototype label in the 16 px body size, not the small caption size", async () => {
    await home();
    const label = screen.getByText("Thesis prototype, not an official government app");
    expect(label).toHaveClass("text-body");
    expect(label).not.toHaveClass("text-caption");
  });

  it("shows an error card with a retry button when services cannot load", async () => {
    const user = userEvent.setup();
    let fail = true;
    const base = createFixtureAdapter();
    const client = {
      ...base,
      services: async () => {
        if (fail) throw new Error("down");
        return base.services();
      },
    };
    renderApp(<AppRoutes />, { client });
    expect(await screen.findByRole("alert")).toHaveTextContent("We could not load the services.");
    fail = false;
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Business Permit")).toBeInTheDocument();
  });
});
