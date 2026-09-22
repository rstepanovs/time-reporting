import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchCurrentUser } from "@/auth/api";
import { createExpenseReport, listExpenseOptions, listMyExpenseReports } from "@/expenses/api";
import {
  testEmployee,
  testExpenseOption,
  testExpenseReport,
  testExpenseReportSummary,
} from "@/test/fixtures";
import { renderApp } from "@/test/renderApp";

vi.mock("@/auth/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/auth/api")>()),
  fetchCurrentUser: vi.fn(),
}));

vi.mock("@/expenses/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/expenses/api")>()),
  listMyExpenseReports: vi.fn(),
  listExpenseOptions: vi.fn(),
  createExpenseReport: vi.fn(),
}));

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(fetchCurrentUser).mockResolvedValue(testEmployee);
  vi.mocked(listMyExpenseReports).mockResolvedValue([testExpenseReportSummary]);
  vi.mocked(listExpenseOptions).mockResolvedValue([testExpenseOption]);
});

describe("ExpensesPage", () => {
  it("lists the month's reports", async () => {
    renderApp("/expenses?month=2026-09");

    await screen.findByText(testExpenseReportSummary.project.name);
    expect(listMyExpenseReports).toHaveBeenCalledWith({
      year: 2026,
      month: 9,
      userId: testEmployee.id,
    });
  });

  it("navigates to the previous and next month", async () => {
    renderApp("/expenses?month=2026-09");
    await screen.findByText("September 2026");

    fireEvent.click(screen.getByRole("button", { name: "← Previous" }));
    await waitFor(() => {
      expect(listMyExpenseReports).toHaveBeenCalledWith({
        year: 2026,
        month: 8,
        userId: testEmployee.id,
      });
    });
    await screen.findByText("August 2026");
  });

  it("creates a new report and navigates to it", async () => {
    // No existing report this month, so the new project isn't excluded from the picker.
    vi.mocked(listMyExpenseReports).mockResolvedValue([]);
    vi.mocked(createExpenseReport).mockResolvedValue(testExpenseReport);
    renderApp("/expenses?month=2026-09");
    await screen.findByText("No expense reports this month.");

    fireEvent.click(screen.getByRole("button", { name: "New report" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("combobox", { name: "Project" }));
    fireEvent.click(await screen.findByRole("option", { name: testExpenseOption.project.name }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Create" }));

    await waitFor(() => {
      expect(createExpenseReport).toHaveBeenCalledWith(
        { projectId: testExpenseOption.project.id, year: 2026, month: 9 },
        expect.anything(),
      );
    });
  });
});
