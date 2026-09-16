import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchCurrentUser } from "@/auth/api";
import {
  testAccountant,
  testAdmin,
  testAdminOnly,
  testMonthTimeSummary,
  testMonthTimeSummaryPrevious,
  testReadyBillingPeriod,
  testTeamMonthOverview,
  testTimesheetOption,
  testManager,
  testWeeklyHours,
  testEmployee,
} from "@/test/fixtures";
import { renderApp } from "@/test/renderApp";
import {
  getMonthTimeSummary,
  getTeamMonthOverview,
  getWeeklyHours,
  listTimesheetOptions,
  sendProjectMonthToBilling,
} from "@/timesheets/api";

vi.mock("@/auth/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/auth/api")>()),
  fetchCurrentUser: vi.fn(),
}));

vi.mock("@/timesheets/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/timesheets/api")>()),
  getMonthTimeSummary: vi.fn(),
  getWeeklyHours: vi.fn(),
  listTimesheetOptions: vi.fn(),
  getTeamMonthOverview: vi.fn(),
  sendProjectMonthToBilling: vi.fn(),
}));

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(fetchCurrentUser).mockResolvedValue(testEmployee);
  vi.mocked(getMonthTimeSummary).mockImplementation(async ({ month }) => {
    if (month === 9) return testMonthTimeSummary;
    if (month === 8) return testMonthTimeSummaryPrevious;
    throw new Error(`unexpected month in test: ${month}`);
  });
  vi.mocked(getWeeklyHours).mockResolvedValue(testWeeklyHours);
  vi.mocked(listTimesheetOptions).mockResolvedValue([testTimesheetOption]);
  vi.mocked(getTeamMonthOverview).mockResolvedValue(testTeamMonthOverview);
});

describe("DashboardPage", () => {
  it("shows the quick action links", async () => {
    renderApp("/");

    const reportTime = await screen.findByRole("link", { name: "Report time" });
    expect(reportTime.getAttribute("href")).toBe("/timesheet");

    const previousWeek = screen.getByRole("link", { name: "Previous week" });
    // Today is 2026-09-15 (Tue); the previous ISO week starts 2026-09-07.
    expect(previousWeek.getAttribute("href")).toBe("/timesheet?week=2026-09-07");
  });

  it("shows this month and last month's time, with fill rate and expenses per currency", async () => {
    renderApp("/");

    // 46 / 56 h expected to date -> 82%; wait on this (not just the card's title, which renders
    // before the query resolves) so the assertions below don't race the mocked fetch.
    await screen.findByText("46 / 56 h (82%)");
    expect(screen.getByText("120 EUR")).toBeTruthy();

    // 172 / 168 h expected to date -> 102%.
    expect(await screen.findByText("172 / 168 h (102%)")).toBeTruthy();
    expect(screen.getAllByText("—")).toHaveLength(1);
  });

  it("highlights the current month card but not the previous one", async () => {
    renderApp("/");
    await screen.findByText("46 / 56 h (82%)");

    const current = screen.getByRole("heading", { level: 4, name: "September 2026" });
    const previous = screen.getByRole("heading", { level: 4, name: "August 2026" });

    expect(current.closest('[data-highlighted="true"]')).toBeTruthy();
    expect(previous.closest('[data-highlighted="true"]')).toBeNull();
  });

  it("links each month card to its details on /hours", async () => {
    renderApp("/");

    // Wait for both month cards to finish loading (findAllByRole would resolve as soon as the
    // first "Details →" link appears, racing the second card's own fetch).
    await screen.findByText("46 / 56 h (82%)");
    await screen.findByText("172 / 168 h (102%)");

    const links = screen.getAllByRole("link", { name: "Details →" });
    expect(links.map((link) => link.getAttribute("href"))).toEqual([
      "/hours?month=2026-09",
      "/hours?month=2026-08",
    ]);
  });

  it("renders the weekly hours chart card", async () => {
    renderApp("/");
    // recharts needs a real layout to draw anything meaningful in jsdom; just check the card
    // that hosts it renders with the right title and footer link. Both this card and Hours per
    // project share the "My hours →" label and the same underlying query, so wait for both
    // footers (not just the first) before scoping down to this one.
    await waitFor(() => {
      expect(screen.getAllByRole("link", { name: "My hours →" })).toHaveLength(2);
    });

    const heading = screen.getByRole("heading", { level: 4, name: "Hours per week" });
    const card = heading.closest(".mantine-Paper-root") as HTMLElement;
    const link = within(card).getByRole("link", { name: "My hours →" });
    expect(link.getAttribute("href")).toBe("/hours");
  });

  it("lists hours per project for the last 6 weeks", async () => {
    renderApp("/");

    // "Website Revamp" also appears in the My projects card below, so scope to the table (the
    // only one on this page).
    const table = await screen.findByRole("table");
    const row = within(table).getByText(/Website Revamp/).closest("tr");
    expect(row).toBeTruthy();
    const cells = within(row as HTMLElement).getAllByRole("cell");
    expect(cells[1].textContent).toBe("172");
    expect(cells[2].textContent).toBe("2");
  });

  it("lists the signed-in user's projects, linking to each", async () => {
    renderApp("/");

    const link = await screen.findByRole("link", { name: /Website Revamp/ });
    expect(link.getAttribute("href")).toBe(`/projects/${testTimesheetOption.project.id}`);
  });

  it("shows only the My time section to a plain employee", async () => {
    renderApp("/");

    await screen.findByRole("heading", { name: "My time" });
    expect(screen.queryByRole("heading", { name: "My team" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Billing" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Administration" })).toBeNull();
  });

  it("shows the team section and a scope toggle to a manager", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testManager);
    renderApp("/");

    await screen.findByRole("heading", { name: "My team" });
    expect(await screen.findByText("Awaiting approval")).toBeTruthy();
    expect(screen.getByText("Not submitted")).toBeTruthy();
    expect(await screen.findByRole("radio", { name: "My projects" })).toBeTruthy();
    expect(screen.getByRole("radio", { name: "All" })).toBeTruthy();
  });

  it("shows an Administration section, but not My team, to an admin who isn't also a manager", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testAdminOnly);
    renderApp("/");

    // "Administration" is both the section heading (h3) and its single card's title (h4).
    await screen.findByRole("heading", { name: "Administration", level: 3 });
    expect(screen.queryByRole("heading", { name: "My team" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Billing" })).toBeNull();
    const usersLink = screen.getByRole("link", { name: "Users" });
    expect(usersLink.getAttribute("href")).toBe("/admin/users");
    expect(screen.getByRole("link", { name: "System status" }).getAttribute("href")).toBe(
      "/admin/status",
    );
  });

  it("shows a Billing placeholder to an accountant", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testAccountant);
    renderApp("/");

    await screen.findByRole("heading", { name: "Billing" });
    expect(screen.queryByRole("heading", { name: "My team" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Administration", level: 3 })).toBeNull();
  });

  it("shows both My team and Administration to an admin who is also a manager", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testAdmin);
    renderApp("/");

    await screen.findByRole("heading", { name: "My team" });
    expect(screen.getByRole("heading", { name: "Administration", level: 3 })).toBeTruthy();
    // "My team" already has a "Billing" card (ProjectBillingCard); only the Billing *section*
    // (h3) is gated by the accountant level.
    expect(screen.queryByRole("heading", { name: "Billing", level: 3 })).toBeNull();
  });

  it("lets a manager send a ready project's month to billing", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testManager);
    vi.mocked(sendProjectMonthToBilling).mockResolvedValue(testReadyBillingPeriod);
    renderApp("/");
    await screen.findByRole("heading", { name: "My team" });

    fireEvent.click(await screen.findByRole("button", { name: "Send →" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Send" }));

    await waitFor(() => {
      expect(sendProjectMonthToBilling).toHaveBeenCalledWith(
        { projectId: testReadyBillingPeriod.project_id, year: 2026, month: 9 },
        expect.anything(),
      );
    });
  });
});
