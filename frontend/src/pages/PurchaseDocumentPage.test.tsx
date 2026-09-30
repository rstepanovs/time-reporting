import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchCurrentUser } from "@/auth/api";
import {
  getPurchaseDocument,
  getPurchasesSummary,
  markPurchaseUnpaid,
  returnPurchaseToInbox,
  updatePurchaseDocument,
} from "@/purchases/api";
import {
  testAccountant,
  testPurchaseInvoice,
  testPurchaseReceipt,
  testPurchasesSummary,
} from "@/test/fixtures";
import { renderApp } from "@/test/renderApp";

vi.mock("@/auth/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/auth/api")>()),
  fetchCurrentUser: vi.fn(),
}));

vi.mock("@/purchases/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/purchases/api")>()),
  getPurchaseDocument: vi.fn(),
  getPurchasesSummary: vi.fn(),
  updatePurchaseDocument: vi.fn(),
  markPurchaseUnpaid: vi.fn(),
  returnPurchaseToInbox: vi.fn(),
  listPurchaseDocuments: vi.fn().mockResolvedValue({ items: [], total: 0, limit: 200, offset: 0 }),
}));

beforeEach(() => {
  vi.mocked(fetchCurrentUser).mockResolvedValue(testAccountant);
  vi.mocked(getPurchasesSummary).mockResolvedValue(testPurchasesSummary);
  vi.mocked(getPurchaseDocument).mockResolvedValue(testPurchaseInvoice);
});

describe("PurchaseDocumentPage", () => {
  it("shows the document, its amounts and an edit form", async () => {
    renderApp(`/purchases/${testPurchaseInvoice.id}`);

    await screen.findByRole("heading", { level: 2, name: "Hosting AB" });
    expect(screen.getByText(/100,00 EUR · ~1\s?126,45 SEK/)).toBeTruthy();
    expect(screen.getByText(/rate 11.26450000 of 2026-08-20/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Save" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Paid…" })).toBeTruthy();
  });

  it("saves edits through the update endpoint", async () => {
    vi.mocked(updatePurchaseDocument).mockResolvedValue(testPurchaseInvoice);
    renderApp(`/purchases/${testPurchaseInvoice.id}`);
    await screen.findByRole("heading", { level: 2, name: "Hosting AB" });

    fireEvent.change(screen.getByRole("textbox", { name: "Vendor" }), {
      target: { value: "Hosting Nordic AB" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(updatePurchaseDocument).toHaveBeenCalledWith({
        documentId: testPurchaseInvoice.id,
        details: expect.objectContaining({
          kind: "invoice",
          vendor: "Hosting Nordic AB",
          amount: "100.00",
          currency: "EUR",
          due_date: "2026-09-01",
          payment_status: "unpaid",
        }),
        recomputeConversion: false,
      });
    });
  });

  it("marks a paid invoice unpaid", async () => {
    vi.mocked(getPurchaseDocument).mockResolvedValue({
      ...testPurchaseInvoice,
      payment_status: "paid",
      paid_on: "2026-09-25",
      payment_method: "bank_transfer",
    });
    vi.mocked(markPurchaseUnpaid).mockResolvedValue(testPurchaseInvoice);
    renderApp(`/purchases/${testPurchaseInvoice.id}`);
    await screen.findByRole("heading", { level: 2, name: "Hosting AB" });

    fireEvent.click(screen.getByRole("button", { name: "Mark unpaid" }));

    await waitFor(() => {
      expect(markPurchaseUnpaid).toHaveBeenCalledWith(testPurchaseInvoice.id);
    });
  });

  it("sends the document back to the inbox after a confirmation", async () => {
    vi.mocked(returnPurchaseToInbox).mockResolvedValue({
      ...testPurchaseInvoice,
      stage: "inbox",
      kind: null,
    });
    renderApp(`/purchases/${testPurchaseInvoice.id}`);
    await screen.findByRole("heading", { level: 2, name: "Hosting AB" });

    fireEvent.click(screen.getByRole("button", { name: "Back to inbox…" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Send back" }));

    await waitFor(() => {
      expect(returnPurchaseToInbox).toHaveBeenCalledWith(testPurchaseInvoice.id);
    });
  });

  it("freezes a rebilled document", async () => {
    vi.mocked(getPurchaseDocument).mockResolvedValue({
      ...testPurchaseReceipt,
      rebilled_expense_line_id: "d4d4d4d4-4444-4444-8444-444444444444",
    });
    renderApp(`/purchases/${testPurchaseReceipt.id}`);

    await screen.findByText(/has been rebilled to a project/);
    expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Back to inbox…" })).toBeNull();
  });

  it("shows a server conflict from Paid/Unpaid", async () => {
    const { PurchaseConflictError } = await import("@/purchases/api");
    vi.mocked(getPurchaseDocument).mockResolvedValue({
      ...testPurchaseInvoice,
      payment_status: "paid",
      paid_on: "2026-09-25",
      payment_method: "bank_transfer",
    });
    vi.mocked(markPurchaseUnpaid).mockRejectedValue(
      new PurchaseConflictError("The document is not paid"),
    );
    renderApp(`/purchases/${testPurchaseInvoice.id}`);
    await screen.findByRole("heading", { level: 2, name: "Hosting AB" });

    fireEvent.click(screen.getByRole("button", { name: "Mark unpaid" }));

    await screen.findByText("The document is not paid");
  });
});
