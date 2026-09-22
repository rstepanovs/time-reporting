import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { listAuditEvents } from "@/audit/api";
import { fetchCurrentUser } from "@/auth/api";
import { testAdmin, testAuditEvent, testAuditEventPage } from "@/test/fixtures";
import { renderApp } from "@/test/renderApp";
import { searchUserDirectory } from "@/users/api";

vi.mock("@/auth/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/auth/api")>()),
  fetchCurrentUser: vi.fn(),
}));

vi.mock("@/audit/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/audit/api")>()),
  listAuditEvents: vi.fn(),
}));

vi.mock("@/users/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/users/api")>()),
  searchUserDirectory: vi.fn(),
}));

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(fetchCurrentUser).mockResolvedValue(testAdmin);
  vi.mocked(listAuditEvents).mockResolvedValue(testAuditEventPage);
  vi.mocked(searchUserDirectory).mockResolvedValue([]);
});

describe("AdminAuditPage", () => {
  it("renders audit events", async () => {
    renderApp("/admin/audit");

    const summaryCell = await screen.findByText(testAuditEvent.summary);
    const row = summaryCell.closest("tr")!;
    expect(within(row).getByText(testAuditEvent.actor_name!)).toBeTruthy();
    expect(within(row).getByText("Billing period reopened")).toBeTruthy();
  });

  it("shows an empty state when there are no events", async () => {
    vi.mocked(listAuditEvents).mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 });

    renderApp("/admin/audit");

    await screen.findByText("No audit events found.");
  });

  it("expands a row to show its details", async () => {
    renderApp("/admin/audit");
    await screen.findByText(testAuditEvent.summary);

    expect(screen.queryByText(/"project_name"/)).toBeNull();
    screen.getByRole("button", { name: "Expand details" }).click();

    await screen.findByText(/"project_name"/);
  });

  it("re-queries with the action filter", async () => {
    renderApp("/admin/audit");
    await screen.findByText(testAuditEvent.summary);

    fireEvent.click(screen.getByRole("combobox", { name: "Action" }));
    (await screen.findByText("User created")).click();

    await waitFor(() =>
      expect(listAuditEvents).toHaveBeenLastCalledWith(
        expect.objectContaining({ action: "user.created" }),
      ),
    );
  });
});
