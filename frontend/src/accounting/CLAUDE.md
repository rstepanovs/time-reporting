# frontend accounting/

Backend: `modules/accounting` (the monthly handoff package — see that module's `CLAUDE.md` for
`GetAccountantPackageStatus`'s field semantics and what `BuildAccountantPackage` puts in the ZIP).
This area is read-only: one query and one plain download URL, no mutations.

## API layer (`api.ts`)

- `getAccountantPackageStatus(year, month)` → `accounting.GetAccountantPackageStatus`'s DTO —
  counts, per-currency totals and the three warning counts `/accounting` renders as `Alert`s.
- `accountantPackageDownloadUrl(year, month)` — a plain relative URL for an `<a href download>`,
  never fetched through `api` (following `attachmentDownloadUrl`/`invoicePdfUrl`); the actual
  render/zip happens server-side on that request, so there is nothing to prefetch or cache.
- No error-mapping class of its own: the route has no domain errors (any `year`/`month` is valid,
  even an empty one — see the backend `CLAUDE.md`), so a failed status fetch surfaces as the
  generic `ApiError`.

## Hooks (`hooks.ts`)

- `accountingKeys.status(year, month)` is the only key — no list/detail split, no mutation to
  invalidate anything with, since this page never writes.
- `useAccountantPackageStatus(year, month)` — the page's one query.

## Page (`pages/AccountingPage.tsx`)

- `/accounting?month=YYYY-MM`, behind `RequireRole roles={["accountant"]}`; nav: the "Billing"
  group's second item, after "Invoices" (`components/AppLayout.tsx`).
- Month navigation is `HoursPage`/`ExpensesPage`'s duplicated local pattern (`MONTH_PARAM_PATTERN`,
  `currentYearMonth`, `formatMonthParam`, Previous/This month/Next buttons writing the `month`
  search param) — not shared, following those two pages' own precedent of not extracting it.
- Three `Alert`s (yellow), one per warning count on the status DTO, shown only when the count is
  greater than zero: draft invoices not yet issued, expense reports not yet approved, sent billing
  periods not yet invoiced — each would leave the corresponding ZIP contents incomplete rather than
  blocking the download itself (the route always succeeds; there's nothing to retry).
- A per-currency totals table (invoiced / expenses, `formatHours` for both — the `InvoicingCard`
  reuse, dropping trailing zeros) and a plain count line ("N invoices, M expense lines"), then
  "Download ZIP" as a plain `<a href={accountantPackageDownloadUrl(year, month)} download>` —
  no confirmation, no loading state of its own; the browser's own download UI covers it.
- `invoices/InvoicingCard.tsx` links here for last month (`/accounting?month=<last month>`), a
  second `Anchor` in the card body rather than `DashboardCard`'s single `footer` link, which stays
  pointed at `/invoices`.
