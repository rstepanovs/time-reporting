# frontend invoices/

Backend: `modules/invoices` (draft generation, issuing/PDF/paid/void are documented there).

## API layer (`api.ts`)

- `listInvoiceablePeriods()` — every sent, uninvoiced, non-internal billing period grouped by
  customer (the "To invoice" tab's source); `listInvoices({ customerId?, status?, dateFrom?,
  dateTo?, limit, offset })` — the paginated "Invoices" tab; `createInvoiceDraft({ customerId,
  periods })`, `getInvoice`, `updateInvoiceDraft` (header fields plus a batch of line
  changes/deletes, the `saveExpenseReportLines` shape), `deleteInvoiceDraft` (draft only),
  `issueInvoice`, `markInvoicePaid({ invoiceId, paidOn })`, `voidInvoice({ invoiceId, reason })`
  and `invoicePdfUrl(id)` (a plain relative URL for an `<a href download>`/new tab, never fetched
  through `api` — following `attachmentDownloadUrl`).
- Errors: `InvoiceRuleError` (400/404, or the backend's generic message for a body-less 403 — the
  caller lost the `accountant` level mid-session) and `InvoiceConflictError` (409 — the invoice's
  status doesn't allow the action, e.g. editing/deleting/issuing a non-draft or paying/voiding
  from the wrong status). Both carry the backend's `detail` as the message where present.

## Query keys and cache rules (`hooks.ts`)

- `invoiceKeys.all` is a shared prefix over the invoiceable-periods list, every invoice list
  variant and every single-invoice detail — `useCreateInvoiceDraft`/`useDeleteInvoiceDraft`/
  `useVoidInvoice` invalidate both `invoiceablePeriods()` and the whole `all` prefix, since
  creating, deleting or voiding an invoice changes which periods are still invoiceable.
  `useIssueInvoice`/`useMarkInvoicePaid` only invalidate `all` (issuing/paying never frees a
  period) and write the mutated invoice straight into its own `detail(invoiceId)` cache entry, as
  `useUpdateInvoiceDraft` also does.

## Pages (`pages/InvoicesPage.tsx`)

- `/invoices?tab=to-invoice|invoices`, behind `RequireRole roles={["accountant"]}` — nav: the
  "Billing" group, shown only to an `accountant`, right after the top-level items
  (`components/AppLayout.tsx`).
- **To invoice** (default tab): one group per customer with invoiceable periods
  (`CustomerInvoiceableGroup`), a checkbox per period defaulting to checked (the default selection
  for a new draft is every one of them, matching `InvoiceableCustomerDTO`'s contract) and its own
  "Create invoice" button, so unchecking a period on one customer never affects another's
  selection or button. On success, navigates to `/invoices/:invoiceId` (the draft page — see the
  plan's next task for the detail page itself).
- **Invoices**: a paginated table (number, customer, date, due date, total with currency, status
  badge) with `Select` filters for customer and status, the `AdminBillingPage`/`AdminAuditPage`
  pagination pattern. "Overdue" is computed client-side (`status === "issued" && due_date <
  today`) and shown instead of the plain "Issued" badge — the backend has no separate status for
  it.
