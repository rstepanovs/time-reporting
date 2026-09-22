# frontend company/

Backend: `modules/company` — a singleton settings row, always readable, never created/deleted.

## API layer

- `api.ts` — `getCompanySettings`, `updateCompanySettings` (a **full replace**: the form always
  submits every field, mirroring `CompanySettingsUpdateRequest` on the backend — there is no
  partial-patch diffing like `customers/api.ts`'s `CustomerUpdateBody`), `setCompanyLogo` (uploads
  a single `File`, multipart, following `expenses/api.ts`'s `formDataBodySerializer`),
  `clearCompanyLogo`, and `companyLogoUrl()` (a plain relative URL for an `<img src>`, never
  fetched through `api` — following `system/api.ts`'s `backupDownloadUrl`).
- Errors: `CompanyLogoTooLargeError` (413) and `CompanyLogoTypeError` (415) from `setCompanyLogo`
  only; every other failure is a generic `ApiError`, since the settings form has no conflict/lookup
  errors to distinguish.
- `INVOICE_LOCALE_OPTIONS` — the two-item `Select` data for `default_invoice_locale`, backed by the
  generated `InvoiceLocale` schema type (`"sv" | "en"`).

## Query keys and cache rules (`hooks.ts`)

- `companyKeys.settings` is a single fixed key (there is only ever one settings row, so no id or
  list parameter). Every mutation (`useUpdateCompanySettings`, `useSetCompanyLogo`,
  `useClearCompanyLogo`) writes its response straight into that cache entry with `setQueryData`
  rather than invalidating, since the response already is the new state.

## Page (`pages/admin/AdminCompanyPage.tsx`)

- `/admin/company`, admin-only (`RequireRole roles={["admin"]}` at the `/admin` route level; the
  backend additionally lets `accountant` read but not write — the frontend has no accountant-only
  view of this page, so an accountant without `admin` never reaches it).
- One page, not a modal (unlike `customers/CustomerFormModal.tsx`): a single Mantine form with
  section headings — Company, Address, Bank, Invoicing, Customer numbering, Workflow — submitted as
  one `CompanySettingsUpdateBody`, since the backend command is a full replace. `useForm`'s
  `initialValues` come from the loaded settings, so the form only renders once
  `useCompanySettings()` has data (the `AdminBackupsPage`/`AdminCalendarPage` loading/error
  pattern).
- The Customer numbering section (`customer_number_prefix`/`next_customer_number`) mirrors the
  Invoicing section's invoice-numbering fields: a new customer created with no `customer_number` of
  its own (`customers/CustomerFormModal.tsx` leaves the field blank) gets the next one allocated
  automatically — see `modules/company/CLAUDE.md`'s "Customer numbering" and
  `modules/customers/CLAUDE.md`.
- The Workflow section's `allow_self_review` `Switch` carries an inline description explaining
  what it does (needed for [[t3-self-approval]] once that reads this flag) rather than linking out
  to documentation.
- The logo control is a Mantine `Avatar` preview (only rendered when `has_logo`, since
  `GET /company/logo` 404s otherwise) plus a `FileInput` and a "Remove logo" button, each wired to
  its own mutation rather than folded into the settings form — a logo change takes effect
  immediately, it isn't part of the "Save changes" draft. The preview URL is cache-busted with
  `?t=<updated_at>` so the browser refetches the `<img>` after a new logo is set (the URL is
  otherwise always the same path).
