import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchCurrentUser } from "@/auth/api";
import {
  deleteInvoiceDraft,
  getInvoice,
  issueInvoice,
  markInvoicePaid,
  updateInvoiceDraft,
  voidInvoice,
} from "@/invoices/api";
import { testAccountant, testInvoiceDraft, testInvoiceIssued, testInvoiceLine } from "@/test/fixtures";
import { renderApp } from "@/test/renderApp";

vi.mock("@/auth/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/auth/api")>()),
  fetchCurrentUser: vi.fn(),
}));

vi.mock("@/invoices/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/invoices/api")>()),
  getInvoice: vi.fn(),
  updateInvoiceDraft: vi.fn(),
  deleteInvoiceDraft: vi.fn(),
  issueInvoice: vi.fn(),
  markInvoicePaid: vi.fn(),
  voidInvoice: vi.fn(),
}));

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(fetchCurrentUser).mockResolvedValue(testAccountant);
  vi.mocked(getInvoice).mockResolvedValue(testInvoiceDraft);
});

describe("InvoicePage", () => {
  it("renders a draft's header fields, lines and totals", async () => {
    renderApp(`/invoices/${testInvoiceDraft.id}`);

    await screen.findByDisplayValue(testInvoiceLine.description);
    expect(screen.getByDisplayValue(testInvoiceDraft.invoice_date)).toBeTruthy();
    expect(screen.getByDisplayValue(testInvoiceDraft.due_date)).toBeTruthy();
    expect(screen.getByText(`${testInvoiceDraft.total} ${testInvoiceDraft.currency}`)).toBeTruthy();
  });

  it("edits an existing line and saves", async () => {
    vi.mocked(updateInvoiceDraft).mockResolvedValue(testInvoiceDraft);
    renderApp(`/invoices/${testInvoiceDraft.id}`);
    await screen.findByDisplayValue(testInvoiceLine.description);

    fireEvent.change(screen.getByRole("textbox", { name: "Description" }), {
      target: { value: "Updated consulting" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(updateInvoiceDraft).toHaveBeenCalledWith(testInvoiceDraft.id, {
        invoiceDate: testInvoiceDraft.invoice_date,
        dueDate: testInvoiceDraft.due_date,
        yourReference: undefined,
        notes: undefined,
        lines: [
          {
            line_id: testInvoiceLine.id,
            description: "Updated consulting",
            quantity: testInvoiceLine.quantity,
            unit: testInvoiceLine.unit,
            unit_price: testInvoiceLine.unit_price,
          },
        ],
        deleteLineIds: [],
        clearFields: ["your_reference", "notes"],
      });
    });
  });

  it("adds a new manual line and saves", async () => {
    vi.mocked(updateInvoiceDraft).mockResolvedValue(testInvoiceDraft);
    renderApp(`/invoices/${testInvoiceDraft.id}`);
    await screen.findByDisplayValue(testInvoiceLine.description);

    fireEvent.click(screen.getByRole("button", { name: "Add line" }));
    const descriptionFields = screen.getAllByRole("textbox", { name: "Description" });
    fireEvent.change(descriptionFields[descriptionFields.length - 1], {
      target: { value: "Travel expenses" },
    });
    const quantityFields = screen.getAllByRole("textbox", { name: "Quantity" });
    fireEvent.change(quantityFields[quantityFields.length - 1], { target: { value: "1" } });
    const unitFields = screen.getAllByRole("textbox", { name: "Unit" });
    fireEvent.change(unitFields[unitFields.length - 1], { target: { value: "pcs" } });
    const priceFields = screen.getAllByRole("textbox", { name: "Unit price" });
    fireEvent.change(priceFields[priceFields.length - 1], { target: { value: "50" } });

    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(updateInvoiceDraft).toHaveBeenCalledWith(
        testInvoiceDraft.id,
        expect.objectContaining({
          lines: expect.arrayContaining([
            expect.objectContaining({
              line_id: null,
              description: "Travel expenses",
              quantity: "1",
              unit: "pcs",
              unit_price: "50",
            }),
          ]),
        }),
      );
    });
  });

  it("removes a line and saves", async () => {
    vi.mocked(updateInvoiceDraft).mockResolvedValue({ ...testInvoiceDraft, lines: [] });
    renderApp(`/invoices/${testInvoiceDraft.id}`);
    await screen.findByDisplayValue(testInvoiceLine.description);

    fireEvent.click(screen.getByRole("button", { name: `Delete line ${testInvoiceLine.description}` }));
    expect(screen.queryByDisplayValue(testInvoiceLine.description)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(updateInvoiceDraft).toHaveBeenCalledWith(
        testInvoiceDraft.id,
        expect.objectContaining({ lines: [], deleteLineIds: [testInvoiceLine.id] }),
      );
    });
  });

  it("issues the draft after confirmation, saving unsaved changes first", async () => {
    vi.mocked(updateInvoiceDraft).mockResolvedValue(testInvoiceDraft);
    vi.mocked(issueInvoice).mockResolvedValue({
      ...testInvoiceIssued,
      id: testInvoiceDraft.id,
    });
    renderApp(`/invoices/${testInvoiceDraft.id}`);
    await screen.findByDisplayValue(testInvoiceLine.description);

    fireEvent.change(screen.getByRole("textbox", { name: "Description" }), {
      target: { value: "Updated consulting" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Issue…" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Issue" }));

    await waitFor(() => {
      expect(updateInvoiceDraft).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(issueInvoice).toHaveBeenCalledWith(testInvoiceDraft.id);
    });
    await screen.findByText(testInvoiceIssued.number!);
    expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
  });

  it("deletes a draft", async () => {
    vi.mocked(deleteInvoiceDraft).mockResolvedValue(undefined);
    renderApp(`/invoices/${testInvoiceDraft.id}`);
    await screen.findByDisplayValue(testInvoiceLine.description);

    fireEvent.click(screen.getByRole("button", { name: "Delete draft" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete" }));

    await waitFor(() => {
      expect(deleteInvoiceDraft).toHaveBeenCalledWith(testInvoiceDraft.id, expect.anything());
    });
  });

  it("asks for confirmation before discarding unsaved changes when leaving", async () => {
    renderApp(`/invoices/${testInvoiceDraft.id}`);
    await screen.findByDisplayValue(testInvoiceLine.description);

    fireEvent.change(screen.getByRole("textbox", { name: "Description" }), {
      target: { value: "Changed" },
    });
    fireEvent.click(screen.getByRole("button", { name: "← Back to invoices" }));

    await screen.findByRole("heading", { name: "Discard unsaved changes?" });
  });

  it("renders an issued invoice read-only with a Download PDF link", async () => {
    vi.mocked(getInvoice).mockResolvedValue(testInvoiceIssued);
    renderApp(`/invoices/${testInvoiceIssued.id}`);

    await screen.findByText(testInvoiceLine.description);
    expect(screen.queryByRole("textbox", { name: "Description" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Issue…" })).toBeNull();
    expect(screen.getByRole("link", { name: "Download PDF" })).toBeTruthy();
  });

  it("marks an issued invoice paid", async () => {
    vi.mocked(getInvoice).mockResolvedValue(testInvoiceIssued);
    vi.mocked(markInvoicePaid).mockResolvedValue({ ...testInvoiceIssued, status: "paid" });
    renderApp(`/invoices/${testInvoiceIssued.id}`);
    await screen.findByText(testInvoiceLine.description);

    fireEvent.click(screen.getByRole("button", { name: "Mark paid…" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Mark paid" }));

    await waitFor(() => {
      expect(markInvoicePaid).toHaveBeenCalledWith(
        expect.objectContaining({ invoiceId: testInvoiceIssued.id }),
      );
    });
  });

  it("voids an issued invoice with a required reason", async () => {
    vi.mocked(getInvoice).mockResolvedValue(testInvoiceIssued);
    vi.mocked(voidInvoice).mockResolvedValue({
      ...testInvoiceIssued,
      status: "void",
      void_reason: "Wrong amount",
    });
    renderApp(`/invoices/${testInvoiceIssued.id}`);
    await screen.findByText(testInvoiceLine.description);

    fireEvent.click(screen.getByRole("button", { name: "Void…" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("button", { name: "Void" }).hasAttribute("disabled")).toBe(true);

    fireEvent.change(within(dialog).getByRole("textbox", { name: "Reason" }), {
      target: { value: "Wrong amount" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Void" }));

    await waitFor(() => {
      expect(voidInvoice).toHaveBeenCalledWith({
        invoiceId: testInvoiceIssued.id,
        reason: "Wrong amount",
      });
    });
  });
});
