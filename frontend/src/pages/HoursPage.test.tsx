import { fireEvent, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchCurrentUser } from "@/auth/api";
import { getMonthCalendar, getYearHours } from "@/timesheets/api";
import { testMonthCalendar, testWorker, testYearHours } from "@/test/fixtures";
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

describe("HoursPage", () => {
  it("shows the requested month's calendar and its year table", async () => {
    renderApp("/hours?month=2026-09");

    await screen.findByRole("heading", { level: 3, name: "September 2026" });
    expect(getMonthCalendar).toHaveBeenCalledWith({
      year: 2026,
      month: 9,
      userId: testWorker.id,
    });
    expect(getYearHours).toHaveBeenCalledWith({ year: 2026, userId: testWorker.id });
    expect(screen.getByRole("heading", { level: 3, name: "2026" })).toBeTruthy();
  });

  it("defaults to the current month when no ?month is given", async () => {
    renderApp("/hours");

    await screen.findByRole("heading", { level: 3, name: "September 2026" });
  });

  it("navigates to the previous and next month", async () => {
    renderApp("/hours?month=2026-09");
    await screen.findByRole("heading", { level: 3, name: "September 2026" });

    fireEvent.click(screen.getByRole("button", { name: "← Previous" }));
    await screen.findByText("August 2026");
    expect(getMonthCalendar).toHaveBeenCalledWith({
      year: 2026,
      month: 8,
      userId: testWorker.id,
    });

    fireEvent.click(screen.getByRole("button", { name: "Next →" }));
    fireEvent.click(screen.getByRole("button", { name: "Next →" }));
    await screen.findByText("October 2026");
  });
});
