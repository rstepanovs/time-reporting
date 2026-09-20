# company module

Owns one table, `company_settings` — the running company's own profile and invoice-numbering
counter. There is always exactly one row (a singleton, `id` fixed to `SINGLETON_ID = 1`, enforced
by a check constraint); the migration inserts it with placeholder values. Nothing depends on
`company`, so it is registered first in `modules/registry.py`, and its own contract depends on
nothing beyond `audit.contracts` (`RecordAuditEvent`, for `UpdateCompanySettings`/
`SetCompanyLogo`/`ClearCompanyLogo`).

## Settings

- `CompanySettings`: legal identity (`legal_name`, `org_number`, `vat_number`), address (`street`,
  `street2`, `postal_code`, `city`, `country` — upper-case ISO 3166-1 alpha-2, blank until set),
  `email`, `phone`, `registered_office`, bank details (`bankgiro`, `iban`, `bic`),
  `f_tax_approved`, `default_invoice_locale` (`"sv"`/`"en"`, see `INVOICE_LOCALES` in
  `contracts.py`), `late_interest` (free text, printed on an invoice as-is), invoice numbering
  (`invoice_number_prefix`, `next_invoice_number`), `allow_self_review` (read by `timesheets` and
  `expenses` to let a manager approve/return their own week or report — see their `CLAUDE.md`
  `Workflow` sections) and the logo. Every text
  field defaults to `""` rather than `NULL` — an empty company profile is a valid, if incomplete,
  state; a future `invoices` module checks completeness before allowing an issue.
- `GetCompanySettings` → `CompanySettingsDTO` (the logo's *presence* only, as `has_logo`, never its
  bytes — see "Logo" below). `UpdateCompanySettings` **replaces the whole row** in one call (`PUT
  /company`, not a partial patch) since the admin page is a single settings form; it validates
  `default_invoice_locale` (`InvalidInvoiceLocaleError` otherwise) and records `company.updated`
  with the changed field names in `details.fields`, only when something actually changed.
  `next_invoice_number` is deliberately editable here too (not only incremented by
  `AllocateInvoiceNumber`), so a first-time setup can resume numbering after an existing paper
  trail instead of always starting at 1 — flag this if it should be locked down instead.

## Logo

- Stored as `bytea` (`logo` + `logo_content_type`) directly on the settings row, so `pg_dump`
  backups already cover it — no new Docker volume, unlike `expenses`' file-based attachments.
  `ALLOWED_LOGO_CONTENT_TYPES` (SVG, PNG, JPEG) and `LOGO_MAX_BYTES` (512 KB) are enforced in
  `CompanyService`, not by a database constraint (mirrors how `expenses.ExpenseAttachment`
  validates size).
- `SetCompanyLogo`/`ClearCompanyLogo` (`PUT`/`DELETE /company/logo`, `AdminDep`, the former
  multipart like `expenses`' attachment upload) each record `company.updated` with
  `details.fields = ["logo"]`. `GetCompanyLogo` → `CompanyLogoDTO | None` (bytes + content type);
  `GET /company/logo` renders it directly as the image response (`fastapi.Response`, not
  `FileResponse` — there is no file on disk) or 404 when unset.

## Invoice numbering

- `AllocateInvoiceNumber` is **nested-only** (no HTTP route, like
  `timesheets.LockProjectMonthExpenseReports`): it locks the settings row (`SELECT ... FOR
  UPDATE`), returns `invoice_number_prefix + next_invoice_number` and increments the counter.
  Numbering is gapless because the increment commits with whatever outer transaction called it
  (a future `invoices.IssueInvoice`) — if that transaction later fails, the whole thing, including
  this increment, rolls back, so the number is never burned. Never call this from an HTTP router
  directly.

## HTTP API (`router.py`, `schemas.py`)

All routes live under `/company`. `GET /company` and `GET /company/logo` are `require_roles(admin,
accountant)` (an accountant needs the profile to render/complete invoices later); every write
(`PUT /company`, `PUT`/`DELETE /company/logo`) is `AdminDep`.
