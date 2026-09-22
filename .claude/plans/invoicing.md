# Plan: running a one-person company — self-approval, internal costs, invoices, accountant package

## Context

The app is built for a company with separate employees, managers and accountants. A one-person
company holds all of those roles in one account and today gets stuck at four points:

1. **Self-approval is forbidden.** `SelfReviewError` (timesheets) and `ExpenseSelfReviewError`
   (expenses) block everyone, admins included, from approving their own week or report. Billing
   readiness needs everything `approved`, so a solo user can never send a month to billing.
2. **Company costs have nowhere to go.** An expense report must belong to a project with `amount`
   billing items, meaning something rebilled to a customer. Software, hardware, phone and the
   accountant's own fee are company costs with receipts but no customer.
3. **No invoices.** The `accountant` level is only a flag. A sent billing period is a screen plus a
   CSV.
4. **No handoff to the external accountant.** Once a month the accountant needs every issued invoice
   and every receipt, in readable form.

The goal is to fix all four **without hardcoding a "solo mode"**. Each fix is a setting or a new
module that a larger company could also use, or simply leave switched off.

### Decisions confirmed with the user

1. **Self-approval is a company setting stored in the database** (`allow_self_review`, default
   off). An admin toggles it in the UI, and the change is audited.
2. **Company costs are internal projects**: `Project.is_internal`. They use the same expense
   reports, receipts and approval flow, but never reach billing or invoices.
3. **VAT is configured per customer, not hardcoded**: a rate (none = no VAT line) plus an optional
   note printed on the invoice, such as "Omvänd betalningsskyldighet / Reverse charge". A customer
   today is Swedish with 25 % moms; a future one may have none.
4. **The accountant package is one ZIP per calendar month**: a readable summary (PDF plus XLSX),
   the invoice PDFs and every receipt.
5. **Invoices are rendered by `faktura-printer`** (`../faktura-printer`,
   `github.com/rstepanovs/faktura-printer`), used as a library (`faktura_printer.render_pdf`). It
   prints amounts verbatim and never recalculates, so time-reporting computes every line, VAT and
   total itself.

### Design decisions (flag on review if wrong)

- **One invoice per customer, built from one or more sent billing periods.** The default selection
  is all of that customer's not-yet-invoiced sent periods of a month, so a customer with two
  projects gets one invoice. A single VAT rate per invoice follows from this, because the rate
  comes from the customer and faktura-printer supports only one rate anyway.
- **Invoice lines are generated, then editable while in draft:**
  - one hours/days line per (project, billing item, period): quantity is the sum,
    `unit_price = unit_rate`;
  - one line per approved expense line: `amount × (1 + markup_percent/100)`, with a description
    built from date, vendor and text;
  - free-form manual lines may be added.

  A billing item used in the period without a `unit_rate` blocks draft creation
  (`BillingItemRateMissingError`), which lists every such item.
- **Rounding:** each line amount is quantized to 0.01 (`ROUND_HALF_UP`), VAT is computed on the
  subtotal, and `total = subtotal + vat`.
- **Issuing is the point of no return.**
  - `IssueInvoice` allocates the next number from a gapless counter (a row lock inside
    `company`), snapshots seller and buyer into the invoice, renders the PDF and stores it.
  - An issued invoice is immutable and can only become `paid` or `void`. A void invoice keeps its
    number and releases its billing periods.
  - Credit notes are out of scope for now; see "Out of scope".
- **Invoice PDFs and the company logo are stored as `bytea` in Postgres.** Both are small (tens of
  KB), so `pg_dump` backs them up with no new volume and no change to `BackupService`.
- **Module dependencies stay acyclic.** Arrows point toward the module being read:
  - `company` → `audit`;
  - `timesheets`, `expenses` → `company` (to read `allow_self_review`);
  - `invoices` → `timesheets`, `customers`, `projects`, `company`, `audit`;
  - `accounting` (no tables) → `invoices`, `expenses`, `company`.

  A billing period learns that it is invoiced the same way expense reports learn that they are
  locked: `invoices` executes a nested `timesheets.MarkBillingPeriodsInvoiced`. `timesheets` never
  reads `invoices`.
- **An invoiced billing period cannot be reopened** (`BillingPeriodInvoicedError`, 409). The fix is
  to void the invoice, or delete it while it is still a draft.

## Execution protocol (read this first in every session)

Each task below is sized to fit in **one fresh session**. Run `/clear` between tasks and start with
"Read `.claude/plans/invoicing.md` and do T<n>". Each task lists:
- **Read first**: the `CLAUDE.md` files and source files to load before starting. Don't explore
  beyond them unless something is missing.
- **Deliverables** and **Tests**.
- **Done when**: the same gates as before, as applicable.
  - Backend: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest`.
  - Frontend (in `frontend/`): `npm run lint && npm run typecheck && npm test && npm run build`.
  - Every `CLAUDE.md` the task touches is updated in the same commit.

Work on branch `feature/invoicing`, cut from `feature/expenses` (not yet merged). Make one commit per
task, `T<n>: ...`, and commit this plan first. Pre-existing dev-DB pollution (`Globex` etc. from
`seed-demo`) makes a handful of unrelated tests fail. Compare against the failure list on the base
branch rather than chasing them.

Tasks are ordered by dependency. **Phase A (F1, T1–T5)** already makes the solo workflow usable up
to "sent to billing". **Phase B (T6–T11)** adds invoicing. **Phase C (T12–T14)** adds the
accountant package. **T15** closes out.

---

## Phase A — solo enablers

### F1 — faktura-printer: currency and buyer identifiers (in `../faktura-printer`)

Prerequisite for invoices outside SEK and for EU reverse charge. Done in the other repository, and
kept backward compatible.
- `InvoiceInfo.currency: str = ""` (ISO 4217). When set, amount labels print it (e.g.
  `"Moms EUR"`, `"Att betala EUR"`) instead of the locale's hardcoded `kr`. Empty keeps today's
  output.
- `Buyer.org_number`, `Buyer.vat_number` (optional, printed under the buyer's address). Reverse
  charge requires both parties' VAT numbers.
- Tests there. Bump to `0.3.0`, tag `v0.3.0`, push. time-reporting pins that tag.
- **Read first:** that repo's `README.md`, `src/faktura_printer/{models,renderer}.py`,
  `themes/invoice.html.j2`, `locales/*.json`.

### T1 — backend `company` module: company profile and settings

- `modules/company/`: `contracts, models, repository, service, handlers, module, schemas, router,
  CLAUDE.md`. Register it first in `modules/registry.py`, since nothing depends on it.
- `CompanySettings` is a singleton row: fixed PK plus a check constraint. The migration inserts it
  with placeholder values. Fields:
  - `legal_name`, `org_number`, `vat_number`;
  - address (`street`, `street2`, `postal_code`, `city`, `country` alpha-2), `email`, `phone`,
    `registered_office`;
  - `bankgiro`, `iban`, `bic`, `f_tax_approved`;
  - `default_invoice_locale` (`sv`/`en`), `late_interest` (text);
  - `invoice_number_prefix` (default `""`), `next_invoice_number` (int, default 1);
  - `allow_self_review` (bool, default false);
  - `logo` (`bytea`, nullable), `logo_content_type` (SVG, PNG or JPEG, at most 512 KB).
- Contracts:
  - `GetCompanySettings` → `CompanySettingsDTO` (logo presence only, not the bytes);
  - `UpdateCompanySettings(actor_id, ...)`, audited as `company.updated` with the changed field
    names in the details;
  - `SetCompanyLogo` / `ClearCompanyLogo`, `GetCompanyLogo` → bytes plus content type;
  - `AllocateInvoiceNumber` → `str`, nested-only: `SELECT ... FOR UPDATE`, returns
    `prefix + number` and increments. Gapless because it commits with the issuing transaction.
- HTTP:
  - `GET /company` (`require_roles(admin, accountant)`), `PUT /company` (`AdminDep`);
  - `PUT/DELETE /company/logo` (`AdminDep`, multipart), `GET /company/logo`.
- Tests:
  - read/update/audit;
  - logo type and size rules;
  - two allocations yield consecutive numbers;
  - an allocation rolled back with its transaction does not burn a number.
- **Read first:** root `CLAUDE.md`, `modules/audit/CLAUDE.md`, `modules/customers/*` (the closest
  simple CRUD module to copy from), `modules/expenses/router.py` (the multipart upload pattern).

### T2 — frontend `/admin/company`

- `frontend/src/company/{api.ts,hooks.ts,CLAUDE.md}`; `pages/admin/AdminCompanyPage.tsx`, with a
  nav entry "Company" in the Administration group and a shortcut in `AdminShortcutsCard`.
- The form has sections Company, Address, Bank, Invoicing (prefix, next number, locale, late
  interest) and Workflow (the `allow_self_review` switch, with a sentence explaining it). It also
  has a logo upload with preview and a remove button.
- `npm run gen:api` first. Tests: renders, saves, uploads a logo, toggles self-review.
- **Read first:** `frontend/src/test/CLAUDE.md`, `frontend/src/admin/CLAUDE.md`,
  `frontend/src/customers/*` (form patterns), `frontend/src/expenses/AttachmentsCard.tsx` (upload).

### T3 — self-approval behind `allow_self_review`

- `timesheets.service` (`approve`/`return`, `can_review` in `get_week`) and `expenses.service`
  (the same three places) read `company.GetCompanySettings`. When the setting is on, the owner may
  review their own week or report, provided they hold `manager`. The router's `ManagerDep` still
  applies. When it is off, behavior is unchanged.
- Expense approve/return audit details gain `"self_review": true` when the actor is the owner.
- Check that `ListSubmittedTimesheetWeeks` / `ListSubmittedExpenseReports` and `/approvals` don't
  filter out the viewer's own items. If they do, include own items only while the setting is on.
- Tests (both modules): refused when off, allowed when on, still refused for a non-manager owner,
  and `can_review` is reflected. Frontend: a manager sees Approve on their own week when the server
  says `can_review`. This probably needs no code change, only a test.
- **Read first:** `modules/timesheets/CLAUDE.md` (Workflow), `modules/expenses/CLAUDE.md`
  (Workflow), `modules/company/CLAUDE.md`, and the two services' approve/return/get functions.

### T4 — internal projects

- `Project.is_internal` (bool, default false, migration), on create/update/DTO/schemas and in the
  project form. An internal project still has a customer (typically a customer record for the
  company itself), so currency and every existing join keep working unchanged.
- `timesheets`:
  - `billing_readiness` and `GetTeamMonthOverview` mark an internal project `not_billable`
    instead of not-ready/ready;
  - `SendProjectMonthToBilling` raises `ProjectIsInternalError` (400);
  - hours on internal projects stay allowed.
- `expenses`: unchanged. Reports on internal projects follow the normal workflow and are never
  locked by billing.
- Frontend:
  - "Internal" checkbox in the project form and a badge in the lists;
  - `ProjectBillingCard` / `TeamPage` show "Internal — not billed" instead of a billing status or
    Send button.
- Tests: send refused, readiness shows `not_billable`, an expense report on an internal project
  works end to end.
- **Read first:** `modules/projects/CLAUDE.md`, `modules/timesheets/CLAUDE.md` (Team overview,
  Billing handoff), `frontend/src/projects/CLAUDE.md`, `frontend/src/timesheets/CLAUDE.md`
  (Manager views).

### T5 — customers: invoicing fields

- `Customer` gains:
  - `vat_rate` (`numeric(5,2)`, nullable; null means no VAT line), `vat_note` (text, nullable);
  - `invoice_locale` (nullable; falls back to the company default; validated against a constant
    `INVOICE_LOCALES = {"sv", "en"}` in `customers.contracts`, so `customers` never imports
    faktura-printer);
  - `customer_number` (varchar 50, nullable), `your_reference` (varchar 255, nullable).

  These are added to create, update, `clear_fields`, the DTO, schemas and the customer form
  (new "Invoicing" section).
- Tests: round-trip, validation (`0 ≤ vat_rate ≤ 100`, locale). Backend and frontend together, as
  the change is small.
- **Read first:** `modules/customers/CLAUDE.md` and its files, `frontend/src/customers/*`.

---

## Phase B — invoicing

### T6 — timesheets: hooks for invoicing

- `ProjectBillingPeriod.invoice_id` (uuid, nullable, **no FK yet**; T7's migration adds it with
  `ON DELETE SET NULL` once the `invoices` table exists).
- Nested-only commands:
  - `MarkBillingPeriodsInvoiced(periods, invoice_id)`: raises `BillingPeriodNotFoundError` or
    `BillingPeriodAlreadyInvoicedError`;
  - `ClearBillingPeriodsInvoiced(invoice_id)`.
- `ReopenProjectBillingPeriod` refuses an invoiced period (`BillingPeriodInvoicedError`, 409).
- `ListBillingPeriods` gains `invoiced: bool | None` plus `invoice_id` in its item. The route and
  the CSV export route widen from `AdminDep` to `require_roles(admin, accountant)`.
- `BillingPeriodExportRowDTO` gains `project_id` and `billing_item_id`, so invoices can aggregate
  from the same query.
- Frontend `/admin/billing` shows an "Invoiced" badge and hides "Reopen…" for invoiced rows.
- Tests: mark/clear, reopen refused, the filter, accountant access.
- **Read first:** `modules/timesheets/CLAUDE.md` (Billing handoff), `timesheets/billing.py`,
  `timesheets/contracts.py` (billing section), `frontend/src/admin/CLAUDE.md`.

### T7 — backend `invoices` module: drafts

- `modules/invoices/`, the full module layout plus `CLAUDE.md`, registered after `timesheets`.
  - `InvoiceStatus` enum (`draft`, `issued`, `paid`, `void`).
  - `invoices` table: `customer_id` FK `RESTRICT`, `number` unique nullable, `status`,
    `invoice_date`, `due_date`, `currency`, `locale`, `vat_rate`, `vat_note`, `your_reference`,
    `notes`, `subtotal`, `vat_amount`, `total`, `seller_snapshot` / `buyer_snapshot` (JSONB,
    filled at issue), `pdf` (bytea), `pdf_sha256`, `issued_at` / `issued_by_id`, `paid_on`,
    `voided_at` / `void_reason`, `TimestampMixin`.
  - `invoice_lines` table: `position`, `kind` (`time`, `expense`, `manual`), `description`,
    `quantity`, `unit`, `unit_price`, `amount`, and nullable `project_id` / `billing_item_id`.
  - `invoice_billing_periods` table: `invoice_id` CASCADE, `project_id`, `period_start`.
  - The migration also adds T6's FK.
- `CreateInvoiceDraft(customer_id, periods, actor_id)`:
  1. Checks that every period is sent, not internal, not invoiced, and belongs to the customer.
  2. Builds lines per "Design decisions" from `timesheets.GetBillingPeriodExportRows` plus
     `projects.GetProjectBillingItemsByIds` (for rates and markup).
  3. Takes currency, VAT, locale and reference from the customer, sets
     `due_date = invoice_date + payment_terms_days`, and computes totals.
  4. Executes the nested `MarkBillingPeriodsInvoiced`.
- `UpdateInvoiceDraft`: header fields plus a batch of line changes (create/update/delete, the same
  shape as `SaveExpenseReportLines`), recomputing totals. `DeleteInvoiceDraft` clears the marks.
- Queries:
  - `GetInvoice`, `ListInvoices` (customer, status, date range, paginated);
  - `ListInvoiceablePeriods`: sent, uninvoiced and not internal periods grouped by customer,
    computed from `timesheets.ListBillingPeriods(invoiced=False)`;
  - `CountInvoices(customer_id)` for `admin`'s removal impact, wired into the `admin` module.
- Audit: `invoice.created`, `invoice.deleted`.
- HTTP under `/invoices` (`AccountantDep`): list, get, `POST` (create), `PUT` (draft update),
  `DELETE` (draft), `GET /invoiceable-periods`.
- Tests:
  - line generation (hours aggregated per item, expense markup, rounding, VAT and no-VAT);
  - a missing rate is refused;
  - a double-invoiced period is refused;
  - deleting frees the periods;
  - the removal impact count.
- **Read first:** root `CLAUDE.md`, `modules/timesheets/CLAUDE.md` (Billing handoff),
  `modules/expenses/CLAUDE.md` (the batch-lines pattern), `modules/projects/contracts.py` (billing
  items), `modules/customers/contracts.py`, `modules/admin/CLAUDE.md`.

### T8 — backend `invoices`: issue, PDF, paid, void

- Dependency: `faktura-printer @ git+https://github.com/rstepanovs/faktura-printer@v0.3.0` in
  `backend/pyproject.toml` (py.typed, so mypy strict works), plus `uv lock`.
- `backend/Dockerfile`: `git` in the builder stage; `libpango-1.0-0 libpangoft2-1.0-0
  libharfbuzz-subset0 fonts-dejavu-core` in the runtime stage. CI installs the same apt packages.
  `docs/operations.md` notes both.
- `invoices/rendering.py` is the only file importing `faktura_printer`. It maps an invoice plus
  snapshots plus lines to `faktura_printer.Invoice`, and calls `render_pdf` via
  `asyncio.to_thread`, since WeasyPrint is CPU-bound.
  - The logo is passed as a `data:` URI.
  - `untrusted=True` with a scratch `base_dir`: the data is ours, but seller fields are free text.
  - A VAT-free invoice prints `vat_rate`/`vat_amount` as `0` plus `vat_note` in `notes`.
- `IssueInvoice(invoice_id, actor_id)`: draft → issued.
  1. Refuses an invoice without lines, or one missing company essentials such as `legal_name` and
     `org_number` (`CompanyProfileIncompleteError`).
  2. Allocates the number via `company.AllocateInvoiceNumber` and snapshots seller and buyer.
  3. Renders, stores `pdf` and its hash.
  4. Audits `invoice.issued`.

  All of this happens in one transaction.
- `GET /invoices/{id}/pdf` serves the stored PDF for issued invoices, and a fresh render marked
  "UTKAST/DRAFT" via `labels` for a draft (preview, not stored).
- `MarkInvoicePaid(paid_on)`: issued → paid. `VoidInvoice(reason)`: issued or paid → void; keeps
  the number and PDF and executes `ClearBillingPeriodsInvoiced`. Both are audited.
- Tests:
  - one real render smoke test (PDF magic bytes, text contains the number);
  - other tests monkeypatch the renderer;
  - numbering is consecutive across two issues;
  - an issued invoice cannot be edited or deleted;
  - voiding frees the periods;
  - the PDF route serves the stored bytes unchanged.
- **Read first:** `modules/invoices/CLAUDE.md`, `modules/company/CLAUDE.md`, faktura-printer
  `README.md` and `models.py`, `backend/Dockerfile`, `.github/workflows/*`, `docs/operations.md`.

### T9 — frontend invoices: API layer and list page

- `frontend/src/invoices/{api.ts,hooks.ts,CLAUDE.md}` (error classes as in `expenses/api.ts`,
  `invoicePdfUrl(id)` as a plain URL).
- `pages/InvoicesPage.tsx` (`/invoices`, `RequireRole roles={["accountant"]}`), tabs via
  `?tab=`:
  - **To invoice**: invoiceable periods grouped by customer, checkboxes, and "Create invoice" →
    navigates to the new draft;
  - **Invoices**: number, customer, date, due date, total with currency, and a status badge
    (overdue = issued and past `due_date`, computed client-side); filters for status and customer.
- Nav: a "Billing" group for `accountant` (Invoices; T14 adds Accountant package).
- Tests: both tabs render, create navigates, filters.
- **Read first:** `frontend/src/test/CLAUDE.md`, `frontend/src/expenses/CLAUDE.md`,
  `pages/CLAUDE.md`, `components/AppLayout.tsx`, `pages/ApprovalsPage.tsx` (tabs pattern).

### T10 — frontend invoice detail page

- `pages/InvoicePage.tsx` (`/invoices/:invoiceId`).
- **Draft**:
  - editable header (dates, reference, notes);
  - `invoices/InvoiceLinesTable.tsx` with a local draft, explicit Save and a dirty-state guard
    (the `ExpenseLinesTable` pattern);
  - server-computed totals, "Preview PDF", "Delete draft", and "Issue…" behind a confirm modal
    that auto-saves first.
- **Issued/paid/void**: read-only, "Download PDF", "Mark paid…" (date picker), and "Void…" (reason
  required).
- Tests: edit and save lines, issue flow, mark paid, void, read-only once issued.
- **Read first:** `frontend/src/invoices/CLAUDE.md`, `frontend/src/expenses/ExpenseLinesTable.tsx`,
  `pages/ExpenseReportPage.tsx`.

### T11 — dashboard Billing section

- Replace `AccountantPlaceholderCard` with `invoices/InvoicingCard.tsx`: periods to invoice, unpaid
  total per currency, and an overdue count, linking to `/invoices`.
- Backend: a small `GetInvoicingSummary` query if the list endpoints would otherwise need several
  round trips.
- Tests. **Read first:** `frontend/src/timesheets/CLAUDE.md` (Dashboard), `pages/DashboardPage.tsx`.

---

## Phase C — accountant package

### T12 — expenses: link a receipt to a line

The accountant reads "one receipt = one line". Today attachments hang off the report only.
- `ExpenseAttachment.line_id` (nullable FK to `expense_report_lines`, `SET NULL`, migration).
  Upload accepts an optional `line_id`, and `SetAttachmentLine(attachment_id, line_id | None)`
  follows the same editability and lock rules.
- `ExpenseLinesTable` / `AttachmentsCard` get a per-attachment line picker and a paperclip on lines
  that have a receipt.
- Tests: link, unlink, a foreign line refused, a locked report refused.
- **Read first:** `modules/expenses/CLAUDE.md` (Attachments), `frontend/src/expenses/CLAUDE.md`.

### T13 — backend `accounting` module: the monthly package

- `modules/accounting/` (no tables).
- New contracts it reads:
  - `invoices.ListInvoicesForMonth(year, month)`: issued, paid and void invoices by
    `invoice_date`, plus the PDF bytes;
  - `expenses.ListMonthExpenseLines(year, month)`: every line of every approved report whose
    period is that month, internal projects included, with the owner, project, `is_internal`,
    currency and linked attachment ids;
  - `expenses.GetAttachmentPath` (exists).
- `GetAccountantPackageStatus(year, month)`:
  - counts and totals per currency;
  - warnings: draft invoices dated in the month, expense reports of the month not yet approved,
    sent periods of the month not yet invoiced.
- `BuildAccountantPackage(year, month)` → path to a temporary ZIP (streamed, then deleted via a
  background task). Contents:
  - `summary.pdf`: company header, then invoices (number, date, customer, net, VAT, total, status),
    then expenses grouped as rebilled vs. internal costs (date, vendor, doc no., description,
    amount, receipt ref), then totals per currency. Rendered with Jinja2 plus WeasyPrint (declared
    as direct dependencies; both already arrive with faktura-printer);
  - `summary.xlsx`: the same data as the sheets Invoices and Expenses (`openpyxl`, a new
    dependency);
  - `invoices/<number>.pdf`;
  - `receipts/<NNN>_<date>_<vendor>_<amount><ext>`, where `NNN` matches the "Receipt" column.
    Report-level receipts not linked to a line go to `receipts/<report>/<file>`.
- HTTP (`AccountantDep`): `GET /accounting/packages/{year}/{month}` (status) and
  `GET /accounting/packages/{year}/{month}.zip`.
- Tests: file list, receipt naming and numbering, XLSX sheet contents, warnings, access.
- **Read first:** `modules/invoices/CLAUDE.md`, `modules/expenses/CLAUDE.md`,
  `modules/system/backup_service.py` (temporary file and streaming patterns).

### T14 — frontend `/accounting`

- `frontend/src/accounting/*`, `pages/AccountingPage.tsx` (`/accounting?month=`,
  `RequireRole accountant`, a nav entry "Accountant package" in the Billing group):
  - month navigator;
  - warnings as `Alert`s;
  - contents summary;
  - "Download ZIP" as a plain `<a href download>`.

  The dashboard `InvoicingCard` links here for last month.
- Tests. **Read first:** `frontend/src/test/CLAUDE.md`, `frontend/src/invoices/CLAUDE.md`,
  `pages/HoursPage.tsx` (month navigation).

### T15 — seed data and documentation sweep

- `seed.py`: demo company profile (only if still at placeholders), an internal project with a
  company-cost report, and one issued invoice for an already-sent demo period. Keep it idempotent.
- Root `CLAUDE.md` (project summary, modules, frontend areas, routes/nav, invoices no longer
  "missing"), `README.md`, `docs/operations.md` (Pango libs, faktura-printer pin, how to update
  it), and each touched module's or area's `CLAUDE.md`.
- End-to-end check in Docker as one user holding admin, manager and accountant:
  1. company profile plus self-review on;
  2. book a month;
  3. submit and approve own weeks and report;
  4. send to billing;
  5. create the invoice, then issue it;
  6. download the PDF;
  7. add an internal cost report with receipts;
  8. download the month's ZIP and open every file.

---

## Out of scope

- Credit notes (kreditfaktura). Void is a stopgap; Swedish bookkeeping practice expects a credit
  note for a sent invoice. This is the first follow-up.
- Several VAT rates on one invoice, per-line VAT, per-project VAT override.
- Sending invoices by e-mail, payment matching from bank files, reminders and late-interest
  invoices.
- Foreign-currency expenses, SIE export or direct integration with an accounting system.
- Handoff history ("which months were already sent to the accountant").
