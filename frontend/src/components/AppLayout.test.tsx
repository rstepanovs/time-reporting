import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchCurrentUser } from "@/auth/api";
import { testAdmin, testUser, testWorker } from "@/test/fixtures";
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
    vi.mocked(fetchCurrentUser).mockResolvedValue(testUser);
    renderApp("/");

    await screen.findByRole("heading", { name: "Time Reporting" });

    expect(screen.getByRole("link", { name: "Dashboard" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Projects" })).toBeTruthy();
  });

  it("shows the Administration menu for an admin", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testAdmin);
    renderApp("/");

    await screen.findByRole("heading", { name: "Time Reporting" });

    expect(screen.getByText("Administration")).toBeTruthy();
  });

  it("hides the Administration menu for a project manager and a worker", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testUser);
    renderApp("/");
    await screen.findByRole("heading", { name: "Time Reporting" });
    expect(screen.queryByText("Administration")).toBeNull();

    vi.mocked(fetchCurrentUser).mockResolvedValue(testWorker);
    renderApp("/");
    await screen.findByRole("heading", { name: "Time Reporting" });
    expect(screen.queryByText("Administration")).toBeNull();
  });

  it("shows Approvals to a project manager and an admin", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testUser); // a project manager
    renderApp("/");
    await screen.findByRole("heading", { name: "Time Reporting" });
    expect(screen.getByRole("link", { name: "Approvals" })).toBeTruthy();
  });

  it("hides Approvals from a worker", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testWorker);
    renderApp("/");
    await screen.findByRole("heading", { name: "Time Reporting" });
    expect(screen.queryByRole("link", { name: "Approvals" })).toBeNull();
  });

  it("shows Team, right after Approvals, to a project manager and an admin", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testUser); // a project manager
    renderApp("/");
    await screen.findByRole("heading", { name: "Time Reporting" });
    const links = screen.getAllByRole("link").map((link) => link.textContent);
    expect(links.indexOf("Team")).toBe(links.indexOf("Approvals") + 1);
  });

  it("hides Team from a worker", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testWorker);
    renderApp("/");
    await screen.findByRole("heading", { name: "Time Reporting" });
    expect(screen.queryByRole("link", { name: "Team" })).toBeNull();
  });
});
