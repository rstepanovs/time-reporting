import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchCurrentUser } from "@/auth/api";
import { listProjectBillingItems, listProjects } from "@/projects/api";
import {
  getCardInvoice,
  getPurchaseDocument,
  getPurchasesSummary,
  getRebillSuggestion,
  linkCardReceipts,
  listUnlinkedCardReceipts,
  rebillPurchase,
  unlinkCardReceipt,
  updateCardReceiptAmount,
} from "@/purchases/api";
import {
  testAccountant,
  testBillingItem,
  testCardInvoice,
  testCardReceipt,
  testCustomBillingItem,
  testProject,
  testPurchaseReceipt,
  testPurchasesSummary,
} from "@/test/fixtures";
import { renderApp } from "@/test/renderApp";

vi.mock("@/auth/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/auth/api")>()),
  fetchCurrentUser: vi.fn(),
}));

vi.mock("@/projects/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/projects/api")>()),
  listProjects: vi.fn(),
  listProjectBillingItems: vi.fn(),
}));

vi.mock("@/purchases/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/purchases/api")>()),
  getPurchaseDocument: vi.fn(),
  getPurchasesSummary: vi.fn(),
  getCardInvoice: vi.fn(),
  listUnlinkedCardReceipts: vi.fn(),
  linkCardReceipts: vi.fn(),
  unlinkCardReceipt: vi.fn(),
  updateCardReceiptAmount: vi.fn(),
  getRebillSuggestion: vi.fn(),
  rebillPurchase: vi.fn(),
}));

const cardInvoiceView = {
  invoice: testCardInvoice,
  receipts: [testCardReceipt],
  receipts_total_base: "112.50",
  difference_base: "187.50",
};

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(fetchCurrentUser).mockResolvedValue(testAccountant);
  vi.mocked(getPurchasesSummary).mockResolvedValue(testPurchasesSummary);
});

describe("card invoice section", () => {
  beforeEach(() => {
    vi.mocked(getPurchaseDocument).mockResolvedValue(testCardInvoice);
    vi.mocked(getCardInvoice).mockResolvedValue(cardInvoiceView);
  });

  it("lists the linked receipts with their sum, the invoice total and the difference", async () => {
    renderApp(`/purchases/${testCardInvoice.id}`);

    await screen.findByText("Receipts on this card invoice");
    expect(screen.getByRole("link", { name: "Cafe" })).toBeTruthy();
    expect(screen.getByText(/Receipts total: 112,50 SEK/)).toBeTruthy();
    expect(screen.getByText(/Card invoice total: 300,00 SEK/)).toBeTruthy();
    expect(screen.getByText(/Difference: 187,50 SEK/)).toBeTruthy();
  });

  it("retypes a receipt's amount from the card invoice line", async () => {
    vi.mocked(updateCardReceiptAmount).mockResolvedValue(testCardReceipt);
    renderApp(`/purchases/${testCardInvoice.id}`);
    await screen.findByText("Receipts on this card invoice");

    expect(
      (screen.getByRole("button", { name: "Save amount of Cafe" }) as HTMLButtonElement).disabled,
    ).toBe(true);
    fireEvent.change(screen.getByRole("textbox", { name: "SEK amount of Cafe" }), {
      target: { value: "120" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save amount of Cafe" }));

    await waitFor(() => {
      expect(updateCardReceiptAmount).toHaveBeenCalledWith({
        receiptId: testCardReceipt.id,
        amountBase: "120",
      });
    });
  });

  it("unlinks a receipt", async () => {
    vi.mocked(unlinkCardReceipt).mockResolvedValue({ ...testCardReceipt, card_invoice_id: null });
    renderApp(`/purchases/${testCardInvoice.id}`);
    await screen.findByText("Receipts on this card invoice");

    fireEvent.click(screen.getByRole("button", { name: "Unlink Cafe" }));

    await waitFor(() => {
      expect(unlinkCardReceipt).toHaveBeenCalledWith(testCardReceipt.id);
    });
  });

  it("links picked receipts with their amounts from the invoice", async () => {
    const loose = { ...testCardReceipt, id: "a7a7a7a7-7777-4777-8777-777777777777", vendor: "Loose Shop", card_invoice_id: null, amount_base: null };
    vi.mocked(listUnlinkedCardReceipts).mockResolvedValue([loose]);
    vi.mocked(linkCardReceipts).mockResolvedValue(cardInvoiceView);
    renderApp(`/purchases/${testCardInvoice.id}`);
    await screen.findByText("Receipts on this card invoice");

    fireEvent.click(screen.getByRole("button", { name: "Add receipts…" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(await within(dialog).findByRole("checkbox", { name: "Select Loose Shop" }));
    const link = within(dialog).getByRole("button", { name: /^Link/ }) as HTMLButtonElement;
    expect(link.disabled).toBe(true); // no amount typed yet
    fireEvent.change(within(dialog).getByRole("textbox", { name: "SEK amount of Loose Shop" }), {
      target: { value: "45" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Link 1 receipt" }));

    await waitFor(() => {
      expect(linkCardReceipts).toHaveBeenCalledWith({
        cardInvoiceId: testCardInvoice.id,
        links: [{ receiptId: loose.id, amountBase: "45" }],
      });
    });
    expect(listUnlinkedCardReceipts).toHaveBeenCalledWith({
      dateFrom: "2026-07-31",
      dateTo: "2026-10-01",
    });
  });

  it("points a linked receipt back to its card invoice", async () => {
    vi.mocked(getPurchaseDocument).mockResolvedValue(testCardReceipt);
    renderApp(`/purchases/${testCardReceipt.id}`);

    const link = await screen.findByRole("link", { name: "open the card invoice" });
    expect(link.getAttribute("href")).toBe(`/purchases/${testCardInvoice.id}`);
  });
});

describe("rebilling", () => {
  beforeEach(() => {
    vi.mocked(getPurchaseDocument).mockResolvedValue(testPurchaseReceipt);
    vi.mocked(listProjects).mockResolvedValue({
      items: [testProject],
      total: 1,
      limit: 200,
      offset: 0,
    });
    vi.mocked(listProjectBillingItems).mockResolvedValue([testBillingItem, testCustomBillingItem]);
    vi.mocked(getRebillSuggestion).mockResolvedValue({
      amount: "100.00",
      currency: "EUR",
      expense_date: "2026-08-20",
      description: "Hotel AB",
    });
  });

  it("rebills with the suggested amount, only offering expense billing items", async () => {
    vi.mocked(rebillPurchase).mockResolvedValue({
      ...testPurchaseReceipt,
      rebilled_expense_line_id: "d4d4d4d4-4444-4444-8444-444444444444",
    });
    renderApp(`/purchases/${testPurchaseReceipt.id}`);
    fireEvent.click(await screen.findByRole("button", { name: "Rebill to project…" }));
    const dialog = await screen.findByRole("dialog");

    fireEvent.click(within(dialog).getByRole("combobox", { name: /^project/i }));
    fireEvent.click(await screen.findByRole("option", { name: /Website Revamp/ }));
    fireEvent.click(await within(dialog).findByRole("combobox", { name: /^billing item/i }));
    expect(screen.queryByRole("option", { name: "Normal working hours" })).toBeNull();
    fireEvent.click(await screen.findByRole("option", { name: "On-call standby" }));

    await waitFor(() => {
      expect(
        (within(dialog).getByRole("textbox", { name: /^amount \(EUR\)/i }) as HTMLInputElement)
          .value,
      ).toBe("100");
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Rebill" }));

    await waitFor(() => {
      expect(rebillPurchase).toHaveBeenCalledWith({
        documentId: testPurchaseReceipt.id,
        projectId: testProject.id,
        year: 2026,
        month: 8,
        billingItemId: testCustomBillingItem.id,
        description: "Hotel AB",
        amount: "100.00",
        expenseDate: "2026-08-20",
      });
    });
  });

  it("links a rebilled document to its expense report", async () => {
    vi.mocked(getPurchaseDocument).mockResolvedValue({
      ...testPurchaseReceipt,
      rebilled_expense_line_id: "d4d4d4d4-4444-4444-8444-444444444444",
      rebilled_expense_report_id: "e9e9e9e9-9999-4999-8999-999999999999",
    });
    renderApp(`/purchases/${testPurchaseReceipt.id}`);

    const link = await screen.findByRole("link", { name: "View the expense report" });
    expect(link.getAttribute("href")).toBe("/expenses/e9e9e9e9-9999-4999-8999-999999999999");
    expect(screen.queryByRole("button", { name: "Rebill to project…" })).toBeNull();
  });
});
