import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getAccountantPackageStatus } from "@/accounting/api";
import { fetchCurrentUser } from "@/auth/api";
import { testAccountant, testAccountantPackageStatus } from "@/test/fixtures";
import { renderApp } from "@/test/renderApp";

vi.mock("@/auth/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/auth/api")>()),
  fetchCurrentUser: vi.fn(),
}));

vi.mock("@/accounting/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/accounting/api")>()),
  getAccountantPackageStatus: vi.fn(),
}));

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(fetchCurrentUser).mockResolvedValue(testAccountant);
  vi.mocked(getAccountantPackageStatus).mockResolvedValue(testAccountantPackageStatus);
});

describe("AccountingPage purchases", () => {
  it("shows the purchases total and the warnings for the inbox and unlinked card receipts", async () => {
    vi.mocked(getAccountantPackageStatus).mockResolvedValue({
      ...testAccountantPackageStatus,
      purchase_count: 4,
      purchase_total_base: "260.00",
      purchase_total_provisional: true,
      purchase_unconverted_count: 1,
      inbox_document_count: 2,
      unlinked_card_receipt_count: 1,
    });
    renderApp("/accounting?month=2026-09");

    await screen.findByText("Documents in the purchases inbox");
    expect(screen.getByText(/2 scanned or emailed documents are still unsorted/)).toBeTruthy();
    expect(screen.getByText("Card receipts without a card invoice")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Open the inbox" }).getAttribute("href")).toBe(
      "/purchases?tab=inbox",
    );
    expect(screen.getByText(/3 expense lines, 4 purchases/)).toBeTruthy();
    expect(screen.getByText(/~260 SEK/)).toBeTruthy();
    expect(screen.getByText(/provisional until the bills are paid/)).toBeTruthy();
    expect(screen.getByText(/1 without a SEK amount yet, not included/)).toBeTruthy();
  });

  it("shows none of it for a month without purchases", async () => {
    renderApp("/accounting?month=2026-09");

    await screen.findByText(/2 invoices, 3 expense lines/);
    expect(screen.queryByText("Documents in the purchases inbox")).toBeNull();
    expect(screen.queryByText(/Purchases total/)).toBeNull();
  });
});

describe("AccountingPage", () => {
  it("shows the month's status and a download link", async () => {
    renderApp("/accounting?month=2026-09");

    await waitFor(() => {
      expect(getAccountantPackageStatus).toHaveBeenCalledWith(2026, 9);
    });
    await screen.findByText(/2 invoices, 3 expense lines/);
    expect(screen.getByText("EUR")).toBeTruthy();
    expect(screen.getByText("1250")).toBeTruthy();
    expect(screen.getByText("42.5")).toBeTruthy();

    const link = screen.getByRole("link", { name: "Download ZIP" });
    expect(link.getAttribute("href")).toBe("/api/v1/accounting/packages/2026/9.zip");
    expect(link.hasAttribute("download")).toBe(true);
  });

  it("navigates to the previous and next month", async () => {
    renderApp("/accounting?month=2026-09");
    await waitFor(() => {
      expect(getAccountantPackageStatus).toHaveBeenCalledWith(2026, 9);
    });

    fireEvent.click(screen.getByRole("button", { name: "← Previous" }));
    await waitFor(() => {
      expect(getAccountantPackageStatus).toHaveBeenCalledWith(2026, 8);
    });

    fireEvent.click(screen.getByRole("button", { name: "Next →" }));
    fireEvent.click(screen.getByRole("button", { name: "Next →" }));
    await waitFor(() => {
      expect(getAccountantPackageStatus).toHaveBeenCalledWith(2026, 10);
    });
  });

  it("shows warnings for drafts, unapproved reports and uninvoiced periods", async () => {
    vi.mocked(getAccountantPackageStatus).mockResolvedValue({
      ...testAccountantPackageStatus,
      draft_invoice_count: 1,
      unapproved_expense_report_count: 2,
      uninvoiced_sent_period_count: 1,
    });
    renderApp("/accounting?month=2026-09");

    await screen.findByText(/1 draft invoice this month/);
    expect(screen.getByText(/2 expense reports this month/)).toBeTruthy();
    expect(screen.getByText(/1 sent billing period this month/)).toBeTruthy();
  });

  it("shows nothing-this-month when there are no totals", async () => {
    vi.mocked(getAccountantPackageStatus).mockResolvedValue({
      ...testAccountantPackageStatus,
      totals: [],
    });
    renderApp("/accounting?month=2026-09");

    await screen.findByText("Nothing this month.");
  });
});
