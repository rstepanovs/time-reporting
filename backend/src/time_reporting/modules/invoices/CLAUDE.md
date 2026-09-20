# invoices module

Owns three tables: `invoices`, `invoice_lines`, `invoice_billing_periods`. Depends on
`timesheets.contracts` (billing periods and their export rows), `customers.contracts` (VAT/locale/
currency/reference), `projects.contracts` (billing items, for rates and markup),
`company.contracts` (the default invoice locale, `AllocateInvoiceNumber`, `GetCompanyLogo` — see
"Issuing" below) and `audit.contracts`; nothing depends on `invoices` except `admin`
(`CountInvoices`, for a customer's removal impact) — see `timesheets/CLAUDE.md`'s "Billing handoff
and locking" for the other side of the link (`ProjectBillingPeriod.invoice_id`,
`MarkBillingPeriodsInvoiced`/`ClearBillingPeriodsInvoiced`). Registered after `expenses`, before
`admin`, in `modules/registry.py`.

`faktura-printer` (`faktura-printer @ git+https://github.com/rstepanovs/faktura-printer@v0.3.0` in
`backend/pyproject.toml`, `tool.hatch.metadata.allow-direct-references = true` alongside it since
it's a direct git reference, not from an index) renders the PDF. `invoices/rendering.py` is the
only file in the whole app importing it — see "Issuing" below.

## Drafting

- `CreateInvoiceDraft(customer_id, periods, invoice_date, actor_id)` — `periods` is a tuple of
  `timesheets.contracts.BillingPeriodRef` (`project_id` + `period_start`), the same natural key
  `ListBillingPeriods`/`MarkBillingPeriodsInvoiced` use since a billing period has no id of its
  own. `invoice_date` is supplied by the router (`date.today()`), like
  `timesheets.GetTeamMonthOverview.today`, so tests can pin it.
  1. Raises `InvoiceNoPeriodsError` for an empty `periods`, `InvoiceCustomerNotFoundError` for an
     unknown customer.
  2. For every period: `InvoicePeriodNotEligibleError` (400, carries a `reason` string) if its
     project isn't `customer_id`'s, is internal (`projects.ProjectDTO.is_internal` — in practice
     unreachable, since an internal project can never be sent to billing at all, see
     `ProjectIsInternalError`), isn't sent (`timesheets.GetBillingPeriodExportRows` raises
     `BillingPeriodNotFoundError`, caught and translated) or is already invoiced (caught the same
     way from `MarkBillingPeriodsInvoiced`'s own `BillingPeriodAlreadyInvoicedError`, at step 4 —
     the whole command is one transaction, so a late rejection there still leaves nothing
     committed).
  3. Builds lines via `_generate_lines` (`service.py`), from every period's
     `GetBillingPeriodExportRows` rows plus `projects.GetProjectBillingItemsByIds` for rates and
     markup:
     - one `InvoiceLineKind.TIME` line per (project, billing item) **within each period** —
       `hour`/`day` rows summed, `unit_price = unit_rate`, `unit` is the item's own unit
       (`"hour"`/`"day"`). A summed item with no `unit_rate` blocks the whole draft
       (`BillingItemRateMissingError`, listing every such `"<project> — <item>"`, collected across
       all periods before raising — nothing is created even for the periods that did have every
       rate);
     - one `InvoiceLineKind.EXPENSE` line per `amount`-unit row (never aggregated — each keeps its
       own vendor/date/description), `unit_price = quantity × (1 + markup_percent / 100)`
       (`markup_percent=None` behaves as `0`), `quantity=1`, `unit="pcs"`, description built from
       the expense date, vendor and text.
     - Every line's `amount = quantity × unit_price`, quantized to 0.01 (`ROUND_HALF_UP` — see
       `_quantize`).
  4. Takes `currency`, `vat_rate`, `vat_note`, `your_reference` from the customer as-is;
     `locale` is the customer's `invoice_locale` or, if unset, `company.GetCompanySettings()
     .default_invoice_locale`; `due_date = invoice_date + customer.payment_terms_days` days.
     `subtotal` is the sum of every line's `amount`; `vat_amount = subtotal × vat_rate / 100`
     (quantized, `0` when `vat_rate` is `None`); `total = subtotal + vat_amount`.
  5. Persists the `Invoice`, its `InvoiceLine`s (in generation order, `position` 1-based) and one
     `InvoiceBillingPeriod` row per period (the invoices-side record of the same link —
     `ProjectBillingPeriod.invoice_id` has no FK of its own to it, see below), then executes the
     nested `timesheets.MarkBillingPeriodsInvoiced(periods, invoice_id)`, then a
     `RecordAuditEvent(invoice.created)`.
- `GetInvoice(invoice_id)` (raises `InvoiceNotFoundError`) and `ListInvoices(customer_id, status,
  date_from, date_to, limit, offset)` (newest `invoice_date` first) read the full/summary shape
  respectively; `InvoiceSummaryDTO` flattens in the customer name (`GetCustomersByIds`) rather than
  the full DTO, matching `timesheets.BillingPeriodListItemDTO`'s own precedent.
- `ListInvoiceablePeriods()` groups every sent, uninvoiced period by customer —
  `timesheets.ListBillingPeriods(invoiced=False, limit=10_000, offset=0)`, resolved to each
  project's customer via `projects.GetProjectsByIds` and grouped — for the "new invoice" picker's
  default selection (every period of the chosen customer).
- `UpdateInvoiceDraft(invoice_id, actor_id, ...)` — header fields left `None` are unchanged;
  `vat_rate`/`vat_note`/`your_reference`/`notes` are nulled only via `clear_fields` (the
  `UpdateCustomer`/`UpdateProject` convention). `lines`/`delete_line_ids` behave like
  `expenses.SaveExpenseReportLines`: `line_id=None` creates a **manual** line
  (`InvoiceLineKind.MANUAL`, no `project_id`/`billing_item_id`); a given `line_id` updates that
  line's `description`/`quantity`/`unit`/`unit_price` (recomputing `amount`) without touching its
  `kind`/`project_id`/`billing_item_id` — editing a generated line's price doesn't turn it manual.
  A `line_id` in both `lines` and `delete_line_ids` ends up deleted. Every line's
  `InvoiceLineNotFoundError` is checked before any change is applied. `subtotal`/`vat_amount`/
  `total` are always recomputed from the resulting lines, never taken from the request. Raises
  `InvoiceNotFoundError` or `InvoiceNotDraftError` — only a `DRAFT` invoice is editable (an issued
  invoice is immutable, see "Issuing" below).
- `DeleteInvoiceDraft(invoice_id, actor_id)` — draft only (`InvoiceNotDraftError` otherwise, same
  as update); deletes the invoice (cascading its lines and period links) and executes the nested
  `timesheets.ClearBillingPeriodsInvoiced(invoice_id)`, freeing every period it covered, then a
  `RecordAuditEvent(invoice.deleted)`.
- `CountInvoices(customer_id)` — every invoice referencing the customer, any status; wired into
  `admin.GetCustomerRemovalImpact` as a new `RemovalBlockerKind.INVOICES` blocker (see
  `admin/CLAUDE.md`) — a customer with any invoice can never be permanently deleted, matching how a
  customer with any project already couldn't be.

## Issuing, paid, void

- `invoices/rendering.py` is the only file in the app importing `faktura_printer`. Its
  `render_invoice_pdf(dto, *, seller, buyer, draft)` maps an `InvoiceDTO` plus `seller`/`buyer`
  dicts to `faktura_printer.Invoice` and calls `render_pdf(..., untrusted=True, base_dir=<the
  system temp dir>)` via `asyncio.to_thread` (WeasyPrint is CPU-bound). `untrusted=True` is right
  even though the data is ours: seller/buyer/note fields are free text an admin typed in, and
  `base_dir` only exists to satisfy that mode's contract — nothing rendered here (a `data:` URI
  logo, otherwise plain text) ever resolves to a file on disk. `draft=True` sets `labels={"title":
  "UTKAST/DRAFT"}` and a placeholder `"DRAFT"` invoice number. `InvoiceInfo` (the nested
  `Invoice.invoice`) isn't part of faktura-printer's public API (see its README), so it's imported
  from `faktura_printer.models` directly rather than the package root.
- `seller`/`buyer` are plain dicts matching `Seller`/`Buyer` constructor kwargs, built by
  `service._build_seller_snapshot(company, logo)`/`_build_buyer_snapshot(customer)` — plus
  `late_interest`/`customer_number` respectively, popped back out in `rendering.py` since
  `faktura_printer` prints those two on `invoice`, not `seller`/`buyer`. The seller's `logo` is a
  `data:<content_type>;base64,...` URI built from `company.GetCompanyLogo()`, or `None`.
- `IssueInvoice(invoice_id, actor_id)` — draft → issued, one transaction:
  1. Raises `InvoiceNotFoundError`/`InvoiceNotDraftError` (only a draft can be issued),
     `InvoiceEmptyError` (no lines) or `CompanyProfileIncompleteError` (`company.legal_name`/
     `org_number` blank — `faktura_printer.Seller.name` needs at least one non-empty character,
     and an invoice with no registration number isn't usable) before anything is written.
  2. Allocates the number via the nested `company.AllocateInvoiceNumber` (gapless — see
     `company/CLAUDE.md`) and snapshots the seller/buyer as above into `Invoice.seller_snapshot`/
     `buyer_snapshot`, so a later edit to the company profile or customer never changes what an
     already-issued invoice printed.
  3. Renders (`draft=False`) and stores the PDF bytes plus their SHA-256
     (`Invoice.pdf`/`pdf_sha256` — `bytea`, like `company.CompanySettings.logo`, small enough that
     `pg_dump` already backs it up, no new Docker volume).
  4. Sets `issued_at`/`issued_by_id`, `status = ISSUED`, and records `RecordAuditEvent
     (invoice.issued)`.

  From here `UpdateInvoiceDraft`/`DeleteInvoiceDraft` both raise `InvoiceNotDraftError` — an issued
  invoice's header and lines are frozen for good; only `MarkInvoicePaid`/`VoidInvoice` still touch
  it.
- `GetInvoicePdf(invoice_id)` (a query — nothing is written for a draft preview) — for a `DRAFT`
  invoice, renders fresh on every call (`draft=True`, not stored, live company/customer data) so a
  preview always reflects the current company profile even before issuing; for anything else,
  returns the bytes stored at issue time unchanged, `filename=f"invoice-{invoice.number}.pdf"`.
  Raises `InvoiceNotFoundError`.
- `MarkInvoicePaid(invoice_id, actor_id, paid_on)` — issued → paid, `paid_on` supplied by the
  caller (a date the accountant picks), never computed here. Raises `InvoiceNotFoundError` or
  `InvoiceNotIssuedError`. Records `invoice.paid`.
- `VoidInvoice(invoice_id, actor_id, reason)` — issued or paid → void, freeing every period it
  covered (the nested `timesheets.ClearBillingPeriodsInvoiced(invoice_id)`, same as
  `DeleteInvoiceDraft`) so they can be re-invoiced. The number and PDF are kept as a record that
  the number was used and then cancelled — voiding never deletes anything. Raises
  `InvoiceNotFoundError` or `InvoiceNotVoidableError` (a draft has nothing to void — delete it
  instead; an already-void invoice can't be voided again). Records `invoice.voided`.

## HTTP API

`APIRouter(prefix="/invoices", tags=["invoices"])`, every route `AccountantDep`-only:
`GET /invoiceable-periods`, `GET /invoices` (filters as query params, `status` aliased from the
`InvoiceStatus` enum), `POST /invoices` (400 on any `InvoiceNoPeriodsError`/
`InvoicePeriodNotEligibleError`/`BillingItemRateMissingError`, 404 on
`InvoiceCustomerNotFoundError`), `GET /invoices/{id}`, `PUT /invoices/{id}` (404/409 as above),
`DELETE /invoices/{id}` (204), `POST /invoices/{id}/issue` (404/409/400 on
`InvoiceEmptyError`/`CompanyProfileIncompleteError`), `POST /invoices/{id}/pay`
(`{paid_on}`, 404/409), `POST /invoices/{id}/void` (`{reason}`, 404/409), `GET /invoices/{id}/pdf`
(404 — a raw `fastapi.Response(media_type="application/pdf")`, not a schema-typed route, with a
`Content-Disposition: attachment` filename). Error mapping follows `expenses/router.py`: the
service already translates every foreign module's exception into one of this module's own, so the
router only ever imports `invoices.contracts`/`invoices.schemas` (plus `auth.dependencies` and, for
building `CreateInvoiceDraft.periods`, `timesheets.contracts.BillingPeriodRef` — the one shared
value type, not an exception).
