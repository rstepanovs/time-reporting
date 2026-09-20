import { screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchCurrentUser } from "@/auth/api";
import { listCustomers } from "@/customers/api";
import { listProjects } from "@/projects/api";
import { listBillingPeriods, reopenProjectBillingPeriod } from "@/timesheets/api";
import { testAdmin, testBillingPeriodListItem, testBillingPeriodPage, testCustomer } from "@/test/fixtures";
import { renderApp } from "@/test/renderApp";

vi.mock("@/auth/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/auth/api")>()),
  fetchCurrentUser: vi.fn(),
}));

vi.mock("@/timesheets/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/timesheets/api")>()),
  listBillingPeriods: vi.fn(),
  reopenProjectBillingPeriod: vi.fn(),
}));

vi.mock("@/customers/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/customers/api")>()),
  listCustomers: vi.fn(),
}));

vi.mock("@/projects/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/projects/api")>()),
  listProjects: vi.fn(),
}));

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(fetchCurrentUser).mockResolvedValue(testAdmin);
  vi.mocked(listBillingPeriods).mockResolvedValue(testBillingPeriodPage);
  vi.mocked(listCustomers).mockResolvedValue({
    items: [testCustomer],
    total: 1,
    limit: 100,
    offset: 0,
  });
  vi.mocked(listProjects).mockResolvedValue({ items: [], total: 0, limit: 100, offset: 0 });
});

describe("AdminBillingPage", () => {
  it("renders the sent billing periods", async () => {
    renderApp("/admin/billing");

    const nameCell = await screen.findByText(testBillingPeriodListItem.project_name);
    const row = nameCell.closest("tr")!;
    expect(within(row).getByText(testBillingPeriodListItem.customer_name)).toBeTruthy();
    expect(within(row).getByText(testBillingPeriodListItem.sent_by_name)).toBeTruthy();
  });

  it("links each row to its CSV export", async () => {
    renderApp("/admin/billing");

    const nameCell = await screen.findByText(testBillingPeriodListItem.project_name);
    const row = nameCell.closest("tr")!;
    const link = within(row).getByRole("link", { name: "CSV" });
    expect(link.getAttribute("href")).toBe(
      `/api/v1/timesheets/billing-periods/${testBillingPeriodListItem.project_id}` +
        `/${testBillingPeriodListItem.period_start}/export.csv`,
    );
  });

  it("shows an empty state when there are no periods", async () => {
    vi.mocked(listBillingPeriods).mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 });

    renderApp("/admin/billing");

    await screen.findByText("No billing periods found.");
  });

  it("shows an Invoiced badge and hides Reopen for an invoiced period", async () => {
    vi.mocked(listBillingPeriods).mockResolvedValue({
      ...testBillingPeriodPage,
      items: [{ ...testBillingPeriodListItem, invoice_id: "inv-1" }],
    });

    renderApp("/admin/billing");

    const nameCell = await screen.findByText(testBillingPeriodListItem.project_name);
    const row = nameCell.closest("tr")!;
    expect(within(row).getByText("Invoiced")).toBeTruthy();
    expect(within(row).queryByRole("button", { name: "Reopen…" })).toBeNull();
  });

  it("reopens a billing period from its row", async () => {
    vi.mocked(reopenProjectBillingPeriod).mockResolvedValue(undefined);
    renderApp("/admin/billing");
    await screen.findByText(testBillingPeriodListItem.project_name);

    screen.getByRole("button", { name: "Reopen…" }).click();
    await screen.findByRole("dialog");

    screen.getByRole("button", { name: "Reopen" }).click();

    await waitFor(() =>
      expect(reopenProjectBillingPeriod).toHaveBeenCalledWith(
        {
          projectId: testBillingPeriodListItem.project_id,
          periodStart: testBillingPeriodListItem.period_start,
        },
        expect.anything(),
      ),
    );
    await screen.findByText("Period reopened");
  });
});
