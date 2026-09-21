import { api } from "@/api/client";
import { ApiError } from "@/api/errors";
import type { components } from "@/api/schema";

export type InvoiceStatus = components["schemas"]["InvoiceStatus"];
export type InvoiceCustomer = components["schemas"]["InvoiceCustomerResponse"];
export type InvoiceLine = components["schemas"]["InvoiceLineResponse"];
export type InvoiceLineChange = components["schemas"]["InvoiceLineChangeRequest"];
export type InvoicePeriod = components["schemas"]["InvoicePeriodResponse"];
export type Invoice = components["schemas"]["InvoiceResponse"];
export type InvoiceSummary = components["schemas"]["InvoiceSummaryResponse"];
export type InvoicePage = components["schemas"]["InvoicePageResponse"];
export type InvoiceablePeriod = components["schemas"]["InvoiceablePeriodResponse"];
export type InvoiceableCustomer = components["schemas"]["InvoiceableCustomerResponse"];
export type ClearableInvoiceField = components["schemas"]["ClearableInvoiceField"];
export type CurrencyTotal = components["schemas"]["CurrencyTotalResponse"];
export type InvoicingSummary = components["schemas"]["InvoicingSummaryResponse"];

/** A rule was violated creating/updating/issuing an invoice, or it doesn't exist (400/404), or the
 * caller lost the `accountant` level mid-session (403, body-less). The backend's message, or a
 * generic one for the last case. */
export class InvoiceRuleError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "InvoiceRuleError";
  }
}

/** The invoice's status doesn't allow this action (409) — e.g. editing/deleting/issuing a
 * non-draft, or paying/voiding from the wrong status. The backend's message. */
export class InvoiceConflictError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "InvoiceConflictError";
  }
}

async function invoiceAwareError(response: Response): Promise<Error> {
  if (response.status === 409) {
    const body = (await response.clone().json().catch(() => null)) as { detail?: string } | null;
    return new InvoiceConflictError(body?.detail ?? "This invoice's status has changed");
  }
  if (response.status === 400 || response.status === 404 || response.status === 403) {
    const body = (await response.clone().json().catch(() => null)) as { detail?: string } | null;
    return new InvoiceRuleError(body?.detail ?? "This action is not allowed");
  }
  return new ApiError(response);
}

/** Every sent, uninvoiced, non-internal billing period, grouped by customer — the "To invoice"
 * tab's source. A customer with no such period is absent from the result. */
export async function listInvoiceablePeriods(): Promise<InvoiceableCustomer[]> {
  const { data, response } = await api.GET("/api/v1/invoices/invoiceable-periods");
  if (!data) throw await invoiceAwareError(response);
  return data;
}

/** The dashboard "Billing" section's data — one aggregate call rather than paging through every
 * invoice/period itself. */
export async function getInvoicingSummary(): Promise<InvoicingSummary> {
  const { data, response } = await api.GET("/api/v1/invoices/summary");
  if (!data) throw await invoiceAwareError(response);
  return data;
}

export async function listInvoices(params: {
  customerId?: string;
  status?: InvoiceStatus;
  dateFrom?: string;
  dateTo?: string;
  limit: number;
  offset: number;
}): Promise<InvoicePage> {
  const { data, response } = await api.GET("/api/v1/invoices", {
    params: {
      query: {
        customer_id: params.customerId,
        status: params.status,
        date_from: params.dateFrom,
        date_to: params.dateTo,
        limit: params.limit,
        offset: params.offset,
      },
    },
  });
  if (!data) throw await invoiceAwareError(response);
  return data;
}

/** Build a draft invoice for one customer from a set of its invoiceable periods. */
export async function createInvoiceDraft(params: {
  customerId: string;
  periods: { projectId: string; periodStart: string }[];
}): Promise<Invoice> {
  const { data, response } = await api.POST("/api/v1/invoices", {
    body: {
      customer_id: params.customerId,
      periods: params.periods.map((period) => ({
        project_id: period.projectId,
        period_start: period.periodStart,
      })),
    },
  });
  if (!data) throw await invoiceAwareError(response);
  return data;
}

export async function getInvoice(invoiceId: string): Promise<Invoice> {
  const { data, response } = await api.GET("/api/v1/invoices/{invoice_id}", {
    params: { path: { invoice_id: invoiceId } },
  });
  if (!data) throw await invoiceAwareError(response);
  return data;
}

/** Apply header field changes and a batch of line changes/deletes in one call. A field left
 * `undefined` is not changed; name it in `clearFields` instead to reset it to `null`. */
export async function updateInvoiceDraft(
  invoiceId: string,
  body: {
    invoiceDate?: string;
    dueDate?: string;
    vatRate?: string;
    vatNote?: string;
    yourReference?: string;
    notes?: string;
    lines?: InvoiceLineChange[];
    deleteLineIds?: string[];
    clearFields?: ClearableInvoiceField[];
  },
): Promise<Invoice> {
  const { data, response } = await api.PUT("/api/v1/invoices/{invoice_id}", {
    params: { path: { invoice_id: invoiceId } },
    body: {
      invoice_date: body.invoiceDate,
      due_date: body.dueDate,
      vat_rate: body.vatRate,
      vat_note: body.vatNote,
      your_reference: body.yourReference,
      notes: body.notes,
      lines: body.lines ?? [],
      delete_line_ids: body.deleteLineIds ?? [],
      clear_fields: body.clearFields ?? [],
    },
  });
  if (!data) throw await invoiceAwareError(response);
  return data;
}

/** Delete a draft invoice entirely, freeing every billing period it covered. */
export async function deleteInvoiceDraft(invoiceId: string): Promise<void> {
  const { response } = await api.DELETE("/api/v1/invoices/{invoice_id}", {
    params: { path: { invoice_id: invoiceId } },
  });
  if (!response.ok) throw await invoiceAwareError(response);
}

/** Move a draft to issued: allocates its number, snapshots the seller/buyer and renders/stores
 * its PDF. */
export async function issueInvoice(invoiceId: string): Promise<Invoice> {
  const { data, response } = await api.POST("/api/v1/invoices/{invoice_id}/issue", {
    params: { path: { invoice_id: invoiceId } },
  });
  if (!data) throw await invoiceAwareError(response);
  return data;
}

export async function markInvoicePaid(params: {
  invoiceId: string;
  paidOn: string;
}): Promise<Invoice> {
  const { data, response } = await api.POST("/api/v1/invoices/{invoice_id}/pay", {
    params: { path: { invoice_id: params.invoiceId } },
    body: { paid_on: params.paidOn },
  });
  if (!data) throw await invoiceAwareError(response);
  return data;
}

/** Void an issued or paid invoice, freeing every billing period it covered. The number and PDF
 * are kept as a record. */
export async function voidInvoice(params: {
  invoiceId: string;
  reason: string;
}): Promise<Invoice> {
  const { data, response } = await api.POST("/api/v1/invoices/{invoice_id}/void", {
    params: { path: { invoice_id: params.invoiceId } },
    body: { reason: params.reason },
  });
  if (!data) throw await invoiceAwareError(response);
  return data;
}

/** Relative URL for the invoice's PDF — a stored render once issued, a fresh "UTKAST/DRAFT"
 * preview for a draft. Used directly as an `<a href download>`/`target="_blank"`, never fetched
 * through `api` — following `attachmentDownloadUrl`. */
export function invoicePdfUrl(invoiceId: string): string {
  return `/api/v1/invoices/${encodeURIComponent(invoiceId)}/pdf`;
}
