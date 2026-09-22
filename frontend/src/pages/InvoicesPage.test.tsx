import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchCurrentUser } from "@/auth/api";
import { listCustomers } from "@/customers/api";
import { createInvoiceDraft, listInvoiceablePeriods, listInvoices } from "@/invoices/api";
import {
  testAccountant,
  testCustomer,
  testInvoiceablePeriod,
  testInvoiceableCustomer,
  testInvoicePage,
  testInvoiceSummary,
} from "@/test/fixtures";
import { renderApp } from "@/test/renderApp";

vi.mock("@/auth/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/auth/api")>()),
  fetchCurrentUser: vi.fn(),
}));

vi.mock("@/customers/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/customers/api")>()),
  listCustomers: vi.fn(),
}));

vi.mock("@/invoices/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/invoices/api")>()),
  listInvoiceablePeriods: vi.fn(),
  listInvoices: vi.fn(),
  createInvoiceDraft: vi.fn(),
}));

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(fetchCurrentUser).mockResolvedValue(testAccountant);
  vi.mocked(listCustomers).mockResolvedValue({
    items: [testCustomer],
    total: 1,
    limit: 100,
    offset: 0,
  });
  vi.mocked(listInvoiceablePeriods).mockResolvedValue([testInvoiceableCustomer]);
  vi.mocked(listInvoices).mockResolvedValue(testInvoicePage);
});

describe("InvoicesPage", () => {
  it("lists invoiceable periods grouped by customer on the default tab", async () => {
    renderApp("/invoices");

    await screen.findByText(testInvoiceableCustomer.customer_name);
    expect(screen.getByText(testInvoiceablePeriod.project_name)).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Create invoice" }).hasAttribute("disabled"),
    ).toBe(false);
  });

  it("creates an invoice from the selected periods and navigates to the draft", async () => {
    const createdInvoice = { ...testInvoiceSummary, id: "f2b2b2b2-2222-2222-2222-222222222222" };
    vi.mocked(createInvoiceDraft).mockResolvedValue({
      ...createdInvoice,
      locale: "sv",
      vat_rate: null,
      vat_note: null,
      your_reference: null,
      notes: null,
      subtotal: "1250.00",
      vat_amount: "0.00",
      issued_at: null,
      paid_on: null,
      voided_at: null,
      void_reason: null,
      lines: [],
      periods: [],
      created_at: "2026-10-02T09:00:00Z",
      updated_at: "2026-10-02T09:00:00Z",
      customer: {
        id: testCustomer.id,
        name: testCustomer.name,
        currency: testCustomer.currency,
      },
    });
    const { router } = renderApp("/invoices");
    await screen.findByText(testInvoiceableCustomer.customer_name);

    fireEvent.click(screen.getByRole("button", { name: "Create invoice" }));

    await waitFor(() => {
      expect(createInvoiceDraft).toHaveBeenCalledWith(
        {
          customerId: testInvoiceableCustomer.customer_id,
          periods: [
            {
              projectId: testInvoiceablePeriod.project_id,
              periodStart: testInvoiceablePeriod.period_start,
            },
          ],
        },
        expect.anything(),
      );
    });
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(`/invoices/${createdInvoice.id}`);
    });
  });

  it("does not invoice an unchecked period", async () => {
    renderApp("/invoices");
    await screen.findByText(testInvoiceableCustomer.customer_name);

    fireEvent.click(
      screen.getByRole("checkbox", {
        name: `${testInvoiceablePeriod.project_name} September 2026`,
      }),
    );
    expect(
      screen.getByRole("button", { name: "Create invoice" }).hasAttribute("disabled"),
    ).toBe(true);
  });

  it("lists invoices on the Invoices tab and filters by status", async () => {
    renderApp("/invoices?tab=invoices");

    const numberCell = await screen.findByText(testInvoiceSummary.number!);
    const row = numberCell.closest("tr")!;
    expect(within(row).getByText(testInvoiceSummary.customer_name)).toBeTruthy();

    fireEvent.click(screen.getByRole("combobox", { name: "Status" }));
    fireEvent.click(await screen.findByRole("option", { name: "Paid" }));

    await waitFor(() => {
      expect(listInvoices).toHaveBeenCalledWith(
        expect.objectContaining({ status: "paid", offset: 0 }),
      );
    });
  });

  it("filters invoices by customer", async () => {
    renderApp("/invoices?tab=invoices");
    await screen.findByText(testInvoiceSummary.number!);

    fireEvent.click(screen.getByRole("combobox", { name: "Customer" }));
    fireEvent.click(await screen.findByRole("option", { name: testCustomer.name }));

    await waitFor(() => {
      expect(listInvoices).toHaveBeenCalledWith(
        expect.objectContaining({ customerId: testCustomer.id, offset: 0 }),
      );
    });
  });
});
