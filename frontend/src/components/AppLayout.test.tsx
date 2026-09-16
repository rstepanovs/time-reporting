import { screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchCurrentUser } from "@/auth/api";
import { testAdmin, testAdminOnly, testManager, testEmployee } from "@/test/fixtures";
import { renderApp } from "@/test/renderApp";

vi.mock("@/auth/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/auth/api")>()),
  fetchCurrentUser: vi.fn(),
}));

beforeEach(() => {
  vi.resetAllMocks();
});

describe("navigation", () => {
  it("shows links to Dashboard and Projects", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testManager);
    renderApp("/");

    await screen.findByRole("heading", { name: "Time Reporting" });

    expect(screen.getByRole("link", { name: "Dashboard" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Projects" })).toBeTruthy();
  });

  it("shows the Administration menu for an admin", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testAdmin);
    renderApp("/");

    await screen.findByRole("heading", { name: "Time Reporting" });

    expect(within(screen.getByRole("navigation")).getByText("Administration")).toBeTruthy();
  });

  it("hides the Administration menu for a project manager and a plain employee", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testManager);
    renderApp("/");
    await screen.findByRole("heading", { name: "Time Reporting" });
    expect(within(screen.getByRole("navigation")).queryByText("Administration")).toBeNull();

    vi.mocked(fetchCurrentUser).mockResolvedValue(testEmployee);
    renderApp("/");
    await screen.findByRole("heading", { name: "Time Reporting" });
    expect(within(screen.getByRole("navigation")).queryByText("Administration")).toBeNull();
  });

  it("shows Approvals to a project manager and an admin", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testManager); // a project manager
    renderApp("/");
    await screen.findByRole("heading", { name: "Time Reporting" });
    expect(screen.getByRole("link", { name: "Approvals" })).toBeTruthy();
  });

  it("hides Approvals from a plain employee", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testEmployee);
    renderApp("/");
    await screen.findByRole("heading", { name: "Time Reporting" });
    expect(screen.queryByRole("link", { name: "Approvals" })).toBeNull();
  });

  it("shows Team, right after Approvals, to a project manager and an admin", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testManager); // a project manager
    renderApp("/");
    await screen.findByRole("heading", { name: "Time Reporting" });
    const links = screen.getAllByRole("link").map((link) => link.textContent);
    expect(links.indexOf("Team")).toBe(links.indexOf("Approvals") + 1);
  });

  it("hides Team from a plain employee", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testEmployee);
    renderApp("/");
    await screen.findByRole("heading", { name: "Time Reporting" });
    expect(screen.queryByRole("link", { name: "Team" })).toBeNull();
  });

  it("shows Administration but hides Approvals/Team to a user holding only admin", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testAdminOnly);
    renderApp("/");
    await screen.findByRole("heading", { name: "Time Reporting" });

    expect(within(screen.getByRole("navigation")).getByText("Administration")).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Approvals" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Team" })).toBeNull();
  });
});
