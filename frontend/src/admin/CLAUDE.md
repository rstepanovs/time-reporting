# frontend admin/

The shared archive-or-delete UI for users, customers and projects, plus the dashboard's
Administration section. Backend: `modules/admin`.

- `AdminShortcutsCard.tsx` — the dashboard's Administration section for `admin` users: a single
  `DashboardCard` with link-only shortcuts to Users/Customers/Projects/Calendar/Billing/Company/
  Audit log/Backups/System status, no data calls.

- `api.ts` — `getRemovalImpact`/`removeEntity` against `/api/v1/admin/...`, plus
  `RemovalBlockedError` (409, carries `blockers`), `RemovalRuleError` (400) and
  `RemovalNotFoundError` (404).
- `hooks.ts` — `useRemovalImpact` (fetched only while a dialog is open) and `useRemoveEntity`, which
  also invalidates the projects lists for users/customers.
- `RemoveEntityModal.tsx` — archives by default, offers a "Delete permanently" checkbox disabled with
  the blocking reason when other data references the record, and shows what else a permanent delete
  would remove once checked.

## Admin pages (`pages/admin/`)

- `AdminUsersPage`/`AdminCustomersPage`/`AdminProjectsPage`: each lists its entity with a debounced
  search and an archived/inactive toggle, and a per-row menu (Edit, entity-specific actions like
  Reset password or Restore, Remove… via `RemoveEntityModal`). An admin can edit their own
  `manager`/`accountant` levels but not remove their own `admin` level (that checkbox is disabled on
  their own row in `UserFormModal`, mirroring the backend guard), and cannot remove themselves from
  `AdminUsersPage`.
- `AdminCalendarPage` — non-working days, via `calendar/`.
- `AdminBillingPage` (`/admin/billing`) — every sent billing period (customer/project/month-range
  filters, paginated), a per-row "Reopen…" confirm modal reusing `timesheets/hooks.ts`'s
  `useReopenProjectBillingPeriod` (same mutation and modal shape as `pages/TeamPage.tsx`'s), plus a
  per-row "CSV" link (`timesheets/api.ts`'s `billingPeriodExportUrl`, a plain `<a href download>`
  like `backupDownloadUrl`) to that period's time-entry/expense-line export. A row whose
  `invoice_id` is set (stamped by `invoices.CreateInvoiceDraft`) shows an "Invoiced" badge instead
  of the "Reopen…" button — the backend refuses reopening an invoiced period (409) anyway, this
  just avoids offering a button that would fail. Backed by `timesheets/`, not an area of its own.
  The page itself is still admin-only (`RequireRole roles={["admin"]}`); the underlying
  `GET`/CSV-export routes also accept an accountant directly, for `invoices/`'s own "To invoice"
  tab (`ListInvoiceablePeriods`) to call.
- `AdminCompanyPage` (`/admin/company`) — the company profile/settings form (legal identity,
  address, bank details, invoicing defaults, the `allow_self_review` workflow switch) and a logo
  upload/preview/remove control. Backed by `company/`, not an area of `admin/` itself.
- `AdminAuditPage` (`/admin/audit`) — the administrative audit log: action/entity type/actor/date
  range filters, a paginated table (time, actor, action, summary) with each row expandable to show
  its raw `details` JSON. Backed by `audit/`.
- `AdminBackupsPage` (`/admin/backups`) and `AdminSystemStatusPage` (`/admin/status`, health badges
  polled directly, no area of their own, plus Versions/Database/Tables/Uptime/Backups/Configuration
  cards) — both backed by `system/`; see `system/CLAUDE.md`.
