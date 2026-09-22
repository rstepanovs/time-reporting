import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchCurrentUser } from "@/auth/api";
import { listSubmittedExpenseReports } from "@/expenses/api";
import { listSubmittedTimesheetWeeks } from "@/timesheets/api";
import {
  testExpenseReportSummary,
  testTimesheetWeekSummary,
  testManager,
  testEmployee,
} from "@/test/fixtures";
import { renderApp } from "@/test/renderApp";

vi.mock("@/auth/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/auth/api")>()),
  fetchCurrentUser: vi.fn(),
}));

vi.mock("@/timesheets/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/timesheets/api")>()),
  listSubmittedTimesheetWeeks: vi.fn(),
}));

vi.mock("@/expenses/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/expenses/api")>()),
  listSubmittedExpenseReports: vi.fn(),
}));

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(listSubmittedExpenseReports).mockResolvedValue([]);
});

describe("ApprovalsPage", () => {
  it("lists submitted weeks for a project manager", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testManager); // a project manager
    vi.mocked(listSubmittedTimesheetWeeks).mockResolvedValue([testTimesheetWeekSummary]);
    renderApp("/approvals");

    await screen.findByText(testEmployee.name);
    expect(screen.getByText(testEmployee.email)).toBeTruthy();
    expect(screen.getByText("40 h")).toBeTruthy();
    expect(
      screen.getByRole("link", { name: /Sep/ }).getAttribute("href"),
    ).toBe(`/timesheet?week=${testTimesheetWeekSummary.week_start}&user=${testEmployee.id}`);
  });

  it("shows an empty state when nothing is waiting for review", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testManager);
    vi.mocked(listSubmittedTimesheetWeeks).mockResolvedValue([]);
    renderApp("/approvals");

    await screen.findByText("No timesheets are waiting for review.");
  });

  it("is not reachable by a plain employee", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testEmployee);
    renderApp("/approvals");

    await screen.findByRole("heading", { name: "Page not found" });
  });

  it("shows the scope toggle to a manager, requesting the matching submissions", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testManager);
    vi.mocked(listSubmittedTimesheetWeeks).mockResolvedValue([]);
    renderApp("/approvals");
    await screen.findByRole("radio", { name: "My projects" });

    await waitFor(() => {
      expect(listSubmittedTimesheetWeeks).toHaveBeenCalledWith({ scope: "mine" });
    });

    fireEvent.click(screen.getByRole("radio", { name: "All" }));

    await waitFor(() => {
      expect(listSubmittedTimesheetWeeks).toHaveBeenCalledWith({ scope: "all" });
    });
  });

  it("lists submitted expense reports on the Expenses tab, linking to the report", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testManager);
    vi.mocked(listSubmittedTimesheetWeeks).mockResolvedValue([]);
    vi.mocked(listSubmittedExpenseReports).mockResolvedValue([testExpenseReportSummary]);
    renderApp("/approvals");
    await screen.findByRole("tab", { name: "Expenses" });

    fireEvent.click(screen.getByRole("tab", { name: "Expenses" }));

    await screen.findByText(testExpenseReportSummary.user.name);
    const link = screen.getByRole("link", {
      name: new RegExp(testExpenseReportSummary.project.name),
    });
    expect(link.getAttribute("href")).toBe(`/expenses/${testExpenseReportSummary.id}`);
  });

  it("shows an empty state on the Expenses tab when nothing is waiting for review", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testManager);
    vi.mocked(listSubmittedTimesheetWeeks).mockResolvedValue([]);
    vi.mocked(listSubmittedExpenseReports).mockResolvedValue([]);
    renderApp("/approvals?tab=expenses");

    await screen.findByText("No expense reports are waiting for review.");
  });

  it("passes the scope toggle to the Expenses tab too", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testManager);
    vi.mocked(listSubmittedTimesheetWeeks).mockResolvedValue([]);
    renderApp("/approvals?tab=expenses");
    await screen.findByRole("radio", { name: "My projects" });

    await waitFor(() => {
      expect(listSubmittedExpenseReports).toHaveBeenCalledWith({ scope: "mine" });
    });

    fireEvent.click(screen.getByRole("radio", { name: "All" }));

    await waitFor(() => {
      expect(listSubmittedExpenseReports).toHaveBeenCalledWith({ scope: "all" });
    });
  });
});
