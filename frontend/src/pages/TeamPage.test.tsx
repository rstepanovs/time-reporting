import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchCurrentUser } from "@/auth/api";
import {
  testAdmin,
  testReadyBillingPeriod,
  testTeamMonthOverview,
  testManager,
  testEmployee,
} from "@/test/fixtures";
import { renderApp } from "@/test/renderApp";
import {
  getTeamMonthOverview,
  reopenProjectBillingPeriod,
  sendProjectMonthToBilling,
} from "@/timesheets/api";

vi.mock("@/auth/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/auth/api")>()),
  fetchCurrentUser: vi.fn(),
}));

vi.mock("@/timesheets/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/timesheets/api")>()),
  getTeamMonthOverview: vi.fn(),
  sendProjectMonthToBilling: vi.fn(),
  reopenProjectBillingPeriod: vi.fn(),
}));

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(getTeamMonthOverview).mockResolvedValue(testTeamMonthOverview);
});

describe("TeamPage", () => {
  it("is not reachable by a plain employee", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testEmployee);
    renderApp("/team");

    await screen.findByRole("heading", { name: "Page not found" });
  });

  it("lists each managed project with its members' weeks", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testManager);
    renderApp("/team");

    await screen.findByText("Website Revamp", { exact: false });
    expect(screen.getByText("Platform Migration", { exact: false })).toBeTruthy();
    expect(screen.getAllByText(testEmployee.name).length).toBeGreaterThan(0);
  });

  it("navigates between months", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testManager);
    renderApp("/team");
    await screen.findByText("Website Revamp", { exact: false });

    vi.mocked(getTeamMonthOverview).mockClear();
    fireEvent.click(screen.getByRole("button", { name: "← Previous" }));

    await waitFor(() => {
      expect(getTeamMonthOverview).toHaveBeenCalledWith(
        expect.objectContaining({ year: 2026, month: 8 }),
      );
    });
  });

  it("lets a manager send a ready project's month to billing", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testManager);
    vi.mocked(sendProjectMonthToBilling).mockResolvedValue(testReadyBillingPeriod);
    renderApp("/team");
    await screen.findByText("Platform Migration", { exact: false });

    fireEvent.click(screen.getByRole("button", { name: "Send to billing" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Send" }));

    await waitFor(() => {
      expect(sendProjectMonthToBilling).toHaveBeenCalledWith(
        { projectId: testReadyBillingPeriod.project_id, year: 2026, month: 9 },
        expect.anything(),
      );
    });
  });

  it("offers reopening a sent period only to an admin", async () => {
    const sentOverview = {
      ...testTeamMonthOverview,
      projects: testTeamMonthOverview.projects.map((project, index) =>
        index === 1
          ? {
              ...project,
              billing: {
                ...project.billing,
                status: "sent" as const,
                sent_at: "2026-08-05T09:00:00Z",
                sent_by: { id: testManager.id, name: testManager.name, email: testManager.email },
              },
            }
          : project,
      ),
    };
    vi.mocked(getTeamMonthOverview).mockResolvedValue(sentOverview);

    vi.mocked(fetchCurrentUser).mockResolvedValue(testManager);
    renderApp("/team");
    await screen.findByText("Platform Migration", { exact: false });
    expect(screen.queryByRole("button", { name: "Reopen" })).toBeNull();

    vi.mocked(fetchCurrentUser).mockResolvedValue(testAdmin);
    renderApp("/team");
    await screen.findByText("Platform Migration", { exact: false });
    expect(await screen.findByRole("button", { name: "Reopen" })).toBeTruthy();
  });

  it("lets an admin reopen a sent period", async () => {
    const sentOverview = {
      ...testTeamMonthOverview,
      projects: testTeamMonthOverview.projects.map((project, index) =>
        index === 1
          ? {
              ...project,
              billing: {
                ...project.billing,
                status: "sent" as const,
                sent_at: "2026-08-05T09:00:00Z",
                sent_by: { id: testAdmin.id, name: testAdmin.name, email: testAdmin.email },
              },
            }
          : project,
      ),
    };
    vi.mocked(getTeamMonthOverview).mockResolvedValue(sentOverview);
    vi.mocked(reopenProjectBillingPeriod).mockResolvedValue();
    vi.mocked(fetchCurrentUser).mockResolvedValue(testAdmin);
    renderApp("/team");
    await screen.findByText("Platform Migration", { exact: false });

    fireEvent.click(screen.getByRole("button", { name: "Reopen" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Reopen" }));

    await waitFor(() => {
      expect(reopenProjectBillingPeriod).toHaveBeenCalledWith(
        {
          projectId: testReadyBillingPeriod.project_id,
          periodStart: testReadyBillingPeriod.period_start,
        },
        expect.anything(),
      );
    });
  });
});
