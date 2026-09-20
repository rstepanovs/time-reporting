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

- `invoiceKeys.lists()` is a shared prefix over every `list(params)` variant, kept **separate**
  from `detail(invoiceId)` — `useIssueInvoice`/`useMarkInvoicePaid`/`useVoidInvoice` all write the
  mutated invoice straight into their own `detail(invoiceId)` cache entry via `setQueryData` and
  then invalidate only `lists()`, never the broader `all` prefix: invalidating `detail(invoiceId)`
  too, right after `setQueryData`, would trigger an immediate background refetch of that same
  active query that can race the `setQueryData` write and clobber it with a stale response (caught
  by `InvoicePage.test.tsx`'s issue-flow test). `useCreateInvoiceDraft`/`useDeleteInvoiceDraft`
  have no specific `detail` entry to preserve this way, so they invalidate the whole `all` prefix
  directly, alongside `invoiceablePeriods()` since creating/deleting/voiding an invoice changes
  which periods are still invoiceable (issuing/paying never frees one).

## Pages (`pages/InvoicesPage.tsx`)

- `/invoices?tab=to-invoice|invoices`, behind `RequireRole roles={["accountant"]}` — nav: the
  "Billing" group, shown only to an `accountant`, right after the top-level items
  (`components/AppLayout.tsx`).
- **To invoice** (default tab): one group per customer with invoiceable periods
  (`CustomerInvoiceableGroup`), a checkbox per period defaulting to checked (the default selection
  for a new draft is every one of them, matching `InvoiceableCustomerDTO`'s contract) and its own
  "Create invoice" button, so unchecking a period on one customer never affects another's
  selection or button. On success, navigates to `/invoices/:invoiceId`.
- **Invoices**: a paginated table (number, customer, date, due date, total with currency, status
  badge) with `Select` filters for customer and status, the `AdminBillingPage`/`AdminAuditPage`
  pagination pattern. "Overdue" is computed client-side (`status === "issued" && due_date <
  today`) and shown instead of the plain "Issued" badge — the backend has no separate status for
  it.

## Detail page (`pages/InvoicePage.tsx`, `InvoiceLinesTable.tsx`)

- `/invoices/:invoiceId`. The page's own header shows the customer, currency and a status badge
  (with the same client-side "Overdue" override as the list); for anything past `draft` it also
  shows the dates, reference, issued/paid/voided timestamps and notes as plain text — `draft`
  shows none of that there because `InvoiceLinesTable` renders the editable versions instead, to
  avoid showing the same field twice.
- `InvoiceLinesTable` is the single component for both states, switching on `invoice.status ===
  "draft"` (mirrors `ExpenseLinesTable` switching on `report.can_edit`) rather than two separate
  components, since a non-draft invoice needs the exact same columns read-only:
  - **Draft**: editable header (invoice date, due date, your reference, notes) plus a lines draft
    (edits keyed by line id, a temp-id-keyed list for not-yet-saved rows, deleted-id set) with an
    explicit Discard/Save — the `ExpenseLinesTable` pattern, but *one* `UpdateInvoiceDraft` call
    per Save carries both the header changes and the line batch, matching the backend's own
    combined command shape (`ExpenseLinesTable` has no header of its own to combine). Editing a
    generated (`time`/`expense`) line's description/quantity/unit/price is allowed and does not
    turn it into a `manual` line — only a brand-new row (no `line_id`) does. Clearing "Your
    reference"/"Notes" to empty sends the field's name in `clear_fields` rather than an empty
    string (the backend's `min_length=1` would reject that). "Issue…" sits next to Discard/Save,
    auto-saving first if dirty (the `ExpenseLinesTable` Submit-button pattern) before executing
    `IssueInvoice`; disabled while there are no lines or an in-progress edit is incomplete.
  - **Issued/paid/void**: the same table read-only, no header fields, no line actions. Totals
    (subtotal/VAT/total) are always the server's own values, never recomputed client-side, even
    mid-edit — a live per-line "Amount" preview (`quantity × unit_price`) is shown only in the
    editable row itself.
- Page-level actions (outside `InvoiceLinesTable`, since none need draft-dirty coordination):
  "Preview PDF" (draft, opens `invoicePdfUrl` in a new tab) / "Download PDF" (otherwise, `<a
  download>`), "Delete draft" (draft only, confirm modal), "Mark paid…" (`issued` only, a
  `DateInput` defaulting to today), "Void…" (`issued`/`paid`, a required reason `Textarea`). The
  "← Back to invoices" link guards `InvoiceLinesTable`'s dirty state the same way
  `ExpenseReportPage`'s does; browser/sidebar navigation away is not guarded, matching it too.
