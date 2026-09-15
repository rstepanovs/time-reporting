import { fireEvent, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchCurrentUser } from "@/auth/api";
import { getMonthCalendar, getYearHours } from "@/timesheets/api";
import {
  testMonthCalendar,
  testMonthHoursCurrent,
  testMonthHoursPast,
  testWorker,
  testYearHours,
} from "@/test/fixtures";
import { renderApp } from "@/test/renderApp";

vi.mock("@/auth/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/auth/api")>()),
  fetchCurrentUser: vi.fn(),
}));

vi.mock("@/timesheets/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/timesheets/api")>()),
  getMonthCalendar: vi.fn(),
  getYearHours: vi.fn(),
}));

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(fetchCurrentUser).mockResolvedValue(testWorker);
  vi.mocked(getMonthCalendar).mockResolvedValue(testMonthCalendar);
  vi.mocked(getYearHours).mockResolvedValue(testYearHours);
});

describe("DashboardPage", () => {
  it("links to this week's timesheet", async () => {
    renderApp("/");

    const link = await screen.findByRole("link", { name: "Open this week's timesheet" });
    expect(link.getAttribute("href")).toBe("/timesheet");
  });

  it("requests the current month and year for the signed-in user", async () => {
    renderApp("/");

    await screen.findByText("September 2026");
    expect(getMonthCalendar).toHaveBeenCalledWith({ year: 2026, month: 9, userId: testWorker.id });
    expect(getYearHours).toHaveBeenCalledWith({ year: 2026, userId: testWorker.id });
  });

  it("marks each day's kind and status, and links the week number to its timesheet", async () => {
    renderApp("/");
    await screen.findByText("September 2026");

    const table = screen.getAllByRole("table")[0];
    const holidayCell = within(table).getByText("16").closest("td");
    expect(holidayCell?.getAttribute("data-kind")).toBe("company_day_off");

    // Sep 7 is a fully-booked past working day (8 of 8 expected hours).
    const bookedDayCell = within(table).getByText("7").closest("td");
    expect(bookedDayCell?.getAttribute("data-status")).toBe("complete");

    const weekLink = within(table).getByRole("link", { name: "37" });
    expect(weekLink.getAttribute("href")).toBe("/timesheet?week=2026-09-07");
  });

  it("shows the week and month totals", async () => {
    renderApp("/");
    await screen.findByText("September 2026");

    expect(screen.getByText("6 / 32 h")).toBeTruthy();
    expect(screen.getByText(/46 h booked/)).toBeTruthy();
  });

  it("hides the Other column when no month has other-preset hours", async () => {
    renderApp("/");
    await screen.findByRole("heading", { level: 3, name: "2026" });

    expect(screen.queryByText("Other")).toBeNull();
  });

  it("expands a month into its per-project breakdown", async () => {
    renderApp("/");
    await screen.findByText("September");

    expect(screen.queryByText(/Website Revamp/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Expand September" }));

    expect(await screen.findByText(/Website Revamp/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Collapse September" }));
    expect(screen.queryByText(/Website Revamp/)).toBeNull();
  });

  it("badges the current month as in progress and shows a delta for a past month", async () => {
    renderApp("/");
    await screen.findByText("September");

    expect(screen.getByText("In progress")).toBeTruthy();
    // August: total 172.00 vs expected-to-date 168.00 -> +4.
    expect(screen.getByText("+4")).toBeTruthy();
  });
});

// Keep the fixtures' shape honest: MonthRows reads is_current/month off testMonthHoursCurrent and
// testMonthHoursPast directly, so a future edit to one without the other would silently break the
// "badges the current month" assertion above.
describe("fixtures", () => {
  it("agree on which month is current", () => {
    expect(testMonthHoursCurrent.is_current).toBe(true);
    expect(testMonthHoursPast.is_current).toBe(false);
  });
});
