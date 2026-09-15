# frontend admin/

The shared archive-or-delete UI for users, customers and projects. Backend: `modules/admin`.

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
  search and an archived/inactive toggle, and a per-row menu (Edit, role/entity-specific actions like
  Reset password or Restore, Remove… via `RemoveEntityModal`). An admin cannot edit their own
  role/active status or remove themselves from `AdminUsersPage`.
- `AdminCalendarPage` — non-working days, via `calendar/`.
- `AdminSystemStatusPage` (`/admin/status`) just polls the health endpoints for an API/database badge.
