import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchCurrentUser } from "@/auth/api";
import {
  getPurchasesSummary,
  listPurchaseDocuments,
  markPurchasePaid,
  type PurchaseDocumentPage,
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
  listPurchaseDocuments: vi.fn(),
  getPurchasesSummary: vi.fn(),
  markPurchasePaid: vi.fn(),
}));

function page(items: PurchaseDocumentPage["items"], total = items.length): PurchaseDocumentPage {
  return { items, total, limit: 20, offset: 0 };
}

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(fetchCurrentUser).mockResolvedValue(testAccountant);
  vi.mocked(getPurchasesSummary).mockResolvedValue(testPurchasesSummary);
  vi.mocked(listPurchaseDocuments).mockResolvedValue(page([testPurchaseInvoice, testPurchaseReceipt]));
});

describe("Register tab", () => {
  it("lists registered documents, newest document date first, with amounts", async () => {
    renderApp("/purchases?tab=register");

    await screen.findByText("Hosting AB");
    expect(listPurchaseDocuments).toHaveBeenCalledWith(
      expect.objectContaining({ stage: "registered", sort: "document_date", limit: 20, offset: 0 }),
    );
    // The estimate is marked "~", the final paid amount is not.
    expect(screen.getByText(/~1\s?126,45 SEK/)).toBeTruthy();
    expect(screen.getByText(/1\s?129,00 SEK/)).toBeTruthy();
    expect(screen.getByText("Due 2026-09-01")).toBeTruthy();
    expect(screen.getByText("Paid 2026-09-25")).toBeTruthy();
  });

  it("filters by kind, payment state and search text", async () => {
    renderApp("/purchases?tab=register");
    await screen.findByText("Hosting AB");

    fireEvent.click(screen.getByRole("combobox", { name: "Kind" }));
    fireEvent.click(await screen.findByRole("option", { name: "Invoice" }));
    fireEvent.click(screen.getByRole("combobox", { name: "Payment" }));
    fireEvent.click(await screen.findByRole("option", { name: "Unpaid" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Search" }), {
      target: { value: "host" },
    });

    await waitFor(() => {
      expect(listPurchaseDocuments).toHaveBeenCalledWith(
        expect.objectContaining({
          kind: "invoice",
          paymentStatus: "unpaid",
          search: "host",
          offset: 0,
        }),
      );
    });
  });

  it("pages through the results", async () => {
    vi.mocked(listPurchaseDocuments).mockResolvedValue(page([testPurchaseInvoice], 45));
    renderApp("/purchases?tab=register");
    await screen.findByText("Hosting AB");

    fireEvent.click(screen.getByRole("button", { name: "2" }));

    await waitFor(() => {
      expect(listPurchaseDocuments).toHaveBeenCalledWith(
        expect.objectContaining({ limit: 20, offset: 20 }),
      );
    });
  });
});

describe("To pay tab", () => {
  beforeEach(() => {
    vi.mocked(listPurchaseDocuments).mockResolvedValue(page([testPurchaseInvoice]));
  });

  it("lists unpaid documents by due date and highlights overdue ones", async () => {
    renderApp("/purchases?tab=to-pay");

    await screen.findByText("Hosting AB");
    expect(listPurchaseDocuments).toHaveBeenCalledWith(
      expect.objectContaining({ stage: "registered", paymentStatus: "unpaid", sort: "due_date" }),
    );
    expect(screen.getByText("Overdue")).toBeTruthy(); // due 2026-09-01, long past
  });

  it("marks a document paid, with the amount the bank actually debited", async () => {
    vi.mocked(markPurchasePaid).mockResolvedValue({
      ...testPurchaseInvoice,
      payment_status: "paid",
    });
    renderApp("/purchases?tab=to-pay");
    await screen.findByText("Hosting AB");

    fireEvent.click(screen.getByRole("button", { name: "Paid…" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("combobox", { name: /^payment method/i }));
    fireEvent.click(await screen.findByRole("option", { name: "Bank transfer" }));
    fireEvent.change(within(dialog).getByRole("textbox", { name: /SEK amount debited/ }), {
      target: { value: "1140" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Mark paid" }));

    await waitFor(() => {
      expect(markPurchasePaid).toHaveBeenCalledWith({
        documentId: testPurchaseInvoice.id,
        paidOn: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
        paymentMethod: "bank_transfer",
        amountBase: "1140",
      });
    });
  });

  it("converts at the payment date's rate when no actual amount is given", async () => {
    vi.mocked(markPurchasePaid).mockResolvedValue(testPurchaseInvoice);
    renderApp("/purchases?tab=to-pay");
    await screen.findByText("Hosting AB");

    fireEvent.click(screen.getByRole("button", { name: "Paid…" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("combobox", { name: /^payment method/i }));
    fireEvent.click(await screen.findByRole("option", { name: "Direct debit" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Mark paid" }));

    await waitFor(() => {
      expect(markPurchasePaid).toHaveBeenCalledWith(
        expect.objectContaining({ paymentMethod: "direct_debit", amountBase: null }),
      );
    });
  });
});
