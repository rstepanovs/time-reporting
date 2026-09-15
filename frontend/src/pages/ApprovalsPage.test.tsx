import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchCurrentUser } from "@/auth/api";
import { listSubmittedTimesheetWeeks } from "@/timesheets/api";
import { testTimesheetWeekSummary, testUser, testWorker } from "@/test/fixtures";
import { renderApp } from "@/test/renderApp";

vi.mock("@/auth/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/auth/api")>()),
  fetchCurrentUser: vi.fn(),
}));

vi.mock("@/timesheets/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/timesheets/api")>()),
  listSubmittedTimesheetWeeks: vi.fn(),
}));

beforeEach(() => {
  vi.resetAllMocks();
});

describe("ApprovalsPage", () => {
  it("lists submitted weeks for a project manager", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testUser); // a project manager
    vi.mocked(listSubmittedTimesheetWeeks).mockResolvedValue([testTimesheetWeekSummary]);
    renderApp("/approvals");

    await screen.findByText(testWorker.name);
    expect(screen.getByText(testWorker.email)).toBeTruthy();
    expect(screen.getByText("40 h")).toBeTruthy();
    expect(
      screen.getByRole("link", { name: /Sep/ }).getAttribute("href"),
    ).toBe(`/timesheet?week=${testTimesheetWeekSummary.week_start}&user=${testWorker.id}`);
  });

  it("shows an empty state when nothing is waiting for review", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testUser);
    vi.mocked(listSubmittedTimesheetWeeks).mockResolvedValue([]);
    renderApp("/approvals");

    await screen.findByText("No timesheets are waiting for review.");
  });

  it("is not reachable by a worker", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testWorker);
    renderApp("/approvals");

    await screen.findByRole("heading", { name: "Page not found" });
  });
});
