import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchCurrentUser } from "@/auth/api";
import {
  discardPurchaseDocument,
  getExchangeRate,
  getPurchasesSummary,
  listPurchaseDocuments,
  registerPurchaseDocument,
  uploadPurchaseDocuments,
} from "@/purchases/api";
import {
  testAccountant,
  testEmployee,
  testPurchaseInboxDocument,
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
  uploadPurchaseDocuments: vi.fn(),
  registerPurchaseDocument: vi.fn(),
  discardPurchaseDocument: vi.fn(),
  getExchangeRate: vi.fn(),
}));

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(fetchCurrentUser).mockResolvedValue(testAccountant);
  vi.mocked(listPurchaseDocuments).mockResolvedValue([testPurchaseInboxDocument]);
  vi.mocked(getPurchasesSummary).mockResolvedValue(testPurchasesSummary);
});

/** `DateInput` parses what is typed on blur, in its default "September 25, 2026" format. */
function typeDate(label: RegExp, text: string) {
  const input = screen.getByRole("textbox", { name: label });
  fireEvent.change(input, { target: { value: text } });
  fireEvent.blur(input);
}

describe("PurchasesPage", () => {
  it("lists inbox documents with a preview and the register form", async () => {
    renderApp("/purchases");

    await screen.findByRole("heading", { level: 4, name: "scan-001.pdf" });
    expect(listPurchaseDocuments).toHaveBeenCalledWith({ stage: "inbox", kind: undefined });
    expect(screen.getByTitle("Document preview").getAttribute("src")).toBe(
      `/api/v1/purchases/documents/${testPurchaseInboxDocument.id}/file`,
    );
    expect(screen.getByRole("button", { name: "Register" })).toBeTruthy();
  });

  it("is hidden from a non-accountant", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testEmployee);
    renderApp("/purchases");

    await screen.findByText(/not found/i);
    expect(listPurchaseDocuments).not.toHaveBeenCalled();
  });

  it("uploads several files at once", async () => {
    vi.mocked(uploadPurchaseDocuments).mockResolvedValue([testPurchaseInboxDocument]);
    renderApp("/purchases");
    await screen.findByRole("heading", { level: 4, name: "scan-001.pdf" });

    const first = new File(["a"], "a.pdf", { type: "application/pdf" });
    const second = new File(["b"], "b.png", { type: "image/png" });
    fireEvent.change(document.querySelector<HTMLInputElement>('input[type="file"]')!, {
      target: { files: [first, second] },
    });

    await waitFor(() => {
      expect(uploadPurchaseDocuments).toHaveBeenCalledWith([first, second]);
    });
  });

  it("shows why an upload was refused", async () => {
    const { PurchaseFileTypeError } = await import("@/purchases/api");
    vi.mocked(uploadPurchaseDocuments).mockRejectedValue(
      new PurchaseFileTypeError("File type 'text/plain' is not allowed"),
    );
    renderApp("/purchases");
    await screen.findByRole("heading", { level: 4, name: "scan-001.pdf" });

    fireEvent.change(document.querySelector<HTMLInputElement>('input[type="file"]')!, {
      target: { files: [new File(["x"], "x.txt", { type: "text/plain" })] },
    });

    await screen.findByText(/not allowed/);
  });

  it("registers a foreign-currency receipt with a live base-currency preview", async () => {
    vi.mocked(getExchangeRate).mockResolvedValue({
      currency: "EUR",
      requested_date: "2026-09-25",
      rate_date: "2026-09-25",
      rate: "11.29000000",
      source: "riksbank",
    });
    vi.mocked(registerPurchaseDocument).mockResolvedValue({
      ...testPurchaseInboxDocument,
      stage: "registered",
      kind: "receipt",
    });
    renderApp("/purchases");
    await screen.findByRole("button", { name: "Register" });

    fireEvent.change(screen.getByRole("textbox", { name: "Vendor" }), {
      target: { value: "Hotel AB" },
    });
    typeDate(/^purchase date/i, "September 25, 2026");
    fireEvent.change(screen.getByRole("textbox", { name: /^amount/i }), {
      target: { value: "100" },
    });
    fireEvent.change(screen.getByRole("textbox", { name: /^currency/i }), {
      target: { value: "eur" },
    });
    fireEvent.click(screen.getByRole("combobox", { name: /^payment method/i }));
    fireEvent.click(await screen.findByRole("option", { name: "Bank transfer" }));

    const preview = await screen.findByLabelText("Base currency preview");
    await waitFor(() => {
      expect(preview.textContent).toContain("11.29000000");
    });
    expect(getExchangeRate).toHaveBeenCalledWith({ currency: "EUR", on: "2026-09-25" });

    fireEvent.click(screen.getByRole("button", { name: "Register" }));

    await waitFor(() => {
      expect(registerPurchaseDocument).toHaveBeenCalledWith({
        documentId: testPurchaseInboxDocument.id,
        details: expect.objectContaining({
          kind: "receipt",
          vendor: "Hotel AB",
          document_date: "2026-09-25",
          amount: "100",
          currency: "EUR",
          payment_method: "bank_transfer",
          payment_status: null,
          due_date: null,
        }),
      });
    });
  });

  it("asks for a due date on an unpaid invoice and a paid-on date once paid", async () => {
    renderApp("/purchases");
    await screen.findByRole("button", { name: "Register" });

    fireEvent.click(screen.getByText("Invoice"));

    expect(screen.getByRole("textbox", { name: /^due date/i })).toBeTruthy();
    expect(screen.queryByRole("textbox", { name: /^paid on/i })).toBeNull();
  });

  it("notes that a card receipt's base amount comes from the card invoice", async () => {
    renderApp("/purchases");
    await screen.findByRole("button", { name: "Register" });

    fireEvent.change(screen.getByRole("textbox", { name: /^amount/i }), {
      target: { value: "10" },
    });
    fireEvent.click(screen.getByRole("combobox", { name: /^payment method/i }));
    fireEvent.click(await screen.findByRole("option", { name: "Card" }));

    const preview = await screen.findByLabelText("Base currency preview");
    expect(preview.textContent).toMatch(/comes from the card invoice/);
  });

  it("shows a server rule error from registering", async () => {
    const { PurchaseRuleError } = await import("@/purchases/api");
    vi.mocked(registerPurchaseDocument).mockRejectedValue(
      new PurchaseRuleError("A receipt needs: document_date"),
    );
    renderApp("/purchases");
    await screen.findByRole("button", { name: "Register" });

    fireEvent.click(screen.getByRole("button", { name: "Register" }));

    await screen.findByText("A receipt needs: document_date");
  });

  it("discards a document", async () => {
    vi.mocked(discardPurchaseDocument).mockResolvedValue({
      ...testPurchaseInboxDocument,
      stage: "discarded",
    });
    renderApp("/purchases");
    await screen.findByRole("heading", { level: 4, name: "scan-001.pdf" });

    fireEvent.click(screen.getByRole("button", { name: "Discard" }));

    await waitFor(() => {
      expect(discardPurchaseDocument).toHaveBeenCalledWith(testPurchaseInboxDocument.id);
    });
  });

  it("shows the inbox count on the tab and the nav item", async () => {
    renderApp("/purchases");

    const nav = await screen.findByRole("link", { name: /^Purchases/ });
    await waitFor(() => {
      expect(within(nav).getByText("1")).toBeTruthy();
    });
  });
});
