# frontend admin/

The shared archive-or-delete UI for users, customers and projects, plus the dashboard's
Administration section. Backend: `modules/admin`.

- `AdminShortcutsCard.tsx` — the dashboard's Administration section for `admin` users: a single
  `DashboardCard` with link-only shortcuts to Users/Customers/Projects/Calendar/Backups/System
  status, no data calls.

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
- `AdminBackupsPage` (`/admin/backups`) and `AdminSystemStatusPage` (`/admin/status`, health badges
  polled directly, no area of their own, plus Versions/Database/Tables/Uptime/Backups/Configuration
  cards) — both backed by `system/`; see `system/CLAUDE.md`.
