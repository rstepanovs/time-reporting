# accounting module

No tables of its own — assembles the monthly handoff package an external accountant receives,
purely by reading other modules' data through the bus. Depends on `invoices.contracts`
(`ListInvoicesForMonth`, `ListInvoices`, `ListInvoiceablePeriods`), `expenses.contracts`
(`ListMonthExpenseLines`, `CountMonthReportsNotApproved`, `GetAttachmentPath`) and
`company.contracts` (`GetCompanySettings`, for the `summary.pdf` header). Nothing depends on
`accounting`, so it registers last in `modules/registry.py`, after `invoices`.

`content.py` holds plain, module-private dataclasses (`PackageContent`, `InvoiceRow`,
`ExpenseRow`, `ReceiptFile`) — the shape `rendering.py`/`spreadsheet.py` need, assembled once by
`AccountingService._build_content` and handed to both renderers plus the ZIP writer, so the
receipt-numbering/grouping logic that produces it exists in exactly one place.

## New reads added elsewhere for this module

- `invoices.ListInvoicesForMonth(year, month)` → `tuple[InvoiceWithPdfDTO, ...]` — every
  **non-draft** invoice (`issued`/`paid`/`void`) whose `invoice_date` falls in the month, each
  paired with the PDF bytes stored on it at `IssueInvoice` time (`invoices.InvoiceRepository
  .list_for_month_non_draft`). A draft has no stored PDF and isn't part of the handoff.
- `expenses.ListMonthExpenseLines(year, month)` → `tuple[ExpenseMonthReportDTO, ...]` — every
  **approved** report (any project, internal ones included — unlike this module's other batch
  queries) whose `period_start` is in the month, each with its own `user`/`project` (so
  `is_internal` and `project.customer.currency` travel with it), its lines (each carrying the
  ids of its own linked attachments) and the report's own attachments not linked to any one line
  (`unlinked_attachment_ids`).
- `expenses.CountMonthReportsNotApproved(year, month)` — a lean count (not full rows) of reports
  in the month that are *not* `APPROVED`, for the "not yet approved" warning — kept separate from
  `ListMonthExpenseLines` rather than folded into it, so that query stays exactly what its name
  says: approved reports only.

## `GetAccountantPackageStatus(year, month)`

What `BuildAccountantPackage` would produce right now, plus three warnings — read before
downloading anything:

- `invoice_count`/`expense_line_count` — exactly what the ZIP would contain.
- `totals`: `AccountantPackageTotalDTO(currency, invoiced_total, expense_total)` per currency that
  has *any* activity that month — a currency with nothing happening drops out entirely rather
  than showing an all-zero row. `invoiced_total` sums only `issued`/`paid` invoices — a `void` one
  is still counted in `invoice_count` (and still listed, with its status, in `summary.pdf`/
  `summary.xlsx` — a record the number was used and cancelled) but contributes nothing to the
  total. `expense_total` sums every approved line's `amount`, `is_internal` or not — the
  accountant needs the true spend either way, `summary.pdf` just prints it under a different
  heading. The two are never summed together, even when they share a currency.
- `draft_invoice_count` — `invoices.ListInvoices(status=DRAFT, date_from=.., date_to=..,
  limit=1, offset=0)`'s `.total` (only the count is used, so `limit=1` avoids paging every draft).
- `unapproved_expense_report_count` — `expenses.CountMonthReportsNotApproved`.
- `uninvoiced_sent_period_count` — `invoices.ListInvoiceablePeriods()`'s periods filtered (in this
  service, not a new backend query) to those whose `period_start` falls in the month — deliberate
  reuse of an existing, unfiltered-by-month query rather than adding a `timesheets` dependency
  this module doesn't otherwise need.

## `BuildAccountantPackage(year, month, actor_id)`

A **query** (nothing persisted), like `invoices.GetInvoicePdf`'s draft preview — built fresh on
every call. `actor_id` is the caller (an accountant), passed through to every
`expenses.GetAttachmentPath` read; the router's `AccountantDep` already grants read access to
every attachment (`expenses.service._has_read_access` treats `ACCOUNTANT` the same as `MANAGER`),
but the query still needs a viewer.

1. Loads `ListInvoicesForMonth`/`ListMonthExpenseLines` (shared with `get_status`).
2. `_build_content` walks every report's lines in order, resolving each linked attachment via
   `GetAttachmentPath` and numbering it sequentially (`next_number`, starting at 1, **global
   across the whole package**, not per report or per line) — that number is both the "Receipt"
   column in `summary.pdf`/`summary.xlsx` and the `NNN` prefix of
   `receipts/<NNN>_<date>_<vendor-slug>_<amount><ext>`. A report's own attachments never linked to
   a line go to `receipts/<project>-<user>-<report id[:8]>/<original file name>` instead — not
   numbered, since nothing in the summary tables points at them by number. `_slug` (shared by both
   paths) keeps a filename readable while safe on any filesystem
   (`[^A-Za-z0-9._-]+` → `-`, trimmed, capped at 40 chars).
3. `rendering.render_summary_pdf(content, company=...)` — Jinja2 (autoescaping on) renders an
   inline template (no template file on disk — see below) to HTML, WeasyPrint prints it to PDF in
   a thread (`asyncio.to_thread`, CPU-bound — the same pattern `invoices.rendering
   .render_invoice_pdf` uses). Sections: company header, an Invoices table (number, date,
   customer, net, VAT, total, status), an Expenses table split into two groups by
   `project.is_internal` ("Rebilled to customers" / "Internal costs (never billed)"), then
   per-currency totals.
4. `spreadsheet.render_summary_xlsx(content)` — `openpyxl`, the same data as two flat sheets
   (`Invoices`, `Expenses`) rather than the PDF's grouped tables — a spreadsheet is for filtering/
   sorting, not reading top to bottom, so grouping there would only get in the way.
5. Writes a ZIP to a fresh `tempfile.mkstemp()` path (`summary.pdf`, `summary.xlsx`,
   `invoices/<number>.pdf` — `InvoiceWithPdfDTO.pdf`, straight from the database, never re-
   rendered — and every `ReceiptFile` from step 2) and returns its path plus a
   `accountant-package-<year>-<month>.zip` filename. The router streams it back via `FileResponse`
   and deletes the temp file with a `starlette.background.BackgroundTask` once sent — the file is
   never written anywhere another request could read it, and nothing about the ZIP is persisted.

`rendering.py`'s template is a Python string constant (`Environment().from_string(...)`), not a
file on disk — the small, single-purpose summary layout doesn't need Jinja2's template-file
loading machinery, and it sidesteps packaging a non-`.py` asset into the wheel (`faktura-printer`,
by contrast, ships its own templates as part of *its* package, not this one's).

`weasyprint` has no type stubs or `py.typed` marker; `[[tool.mypy.overrides]]` in the root
`pyproject.toml` ignores it for that one import, and `rendering.py` casts its one `Any`-typed
return (`HTML(...).write_pdf()`) back to `bytes` explicitly rather than suppressing the check
module-wide. `openpyxl` ships its own stubs via the `types-openpyxl` dev dependency, needing no
override. Both `jinja2` and `weasyprint` were already transitive dependencies of `faktura-printer`
(pinned at the same resolved versions) but are declared directly in `backend/pyproject.toml` too,
since this module imports them itself rather than through `faktura-printer`.

## HTTP API

`APIRouter(prefix="/accounting", tags=["accounting"])`, both routes `AccountantDep`-only, `year`/
`month` as `Path(ge=.., le=..)` (the `timesheets./team/{year}/{month}` precedent, not query
params): `GET /accounting/packages/{year}/{month}` (`GetAccountantPackageStatus`) and
`GET /accounting/packages/{year}/{month}.zip` (`BuildAccountantPackage`, streamed as a raw
`FileResponse` — no response schema, like `invoices.GetInvoicePdf`'s route). Neither route has a
domain error to map: any `year`/`month` combination is valid, even one with nothing in it (the
status DTO and the ZIP are just empty/mostly-empty in that case).
