# frontend system/

Backend: `modules/system`.

- `api.ts` — `getSystemStatus`/`getSystemConfig` (read-only) and `listBackups`/`createBackup`
  against `/api/v1/admin/{system,backups}/...`, plus `backupDownloadUrl(name)` (a relative URL used
  directly as an `<a href download>`, not fetched through `api` — the response is a binary file).
  Errors: `BackupInProgressError` (409, `POST /admin/backups` while one is already running) and
  `BackupFailedError` (500, the backend's generic detail — never the raw `pg_dump`/`pg_restore`
  stderr, which only goes to the server log).
- `hooks.ts` — `systemKeys` + `useSystemStatus`/`useSystemConfig`/`useBackups` queries and
  `useCreateBackup`, which invalidates both `systemKeys.backups()` and `systemKeys.status()` (the
  latter also carries `last_backup_at`).
- `format.ts` — `formatBytes`, shared by the status and backups pages.

Backs two pages:

- `pages/admin/AdminSystemStatusPage.tsx` — also polls the plain `/health` and `/health/ready`
  endpoints directly (not through this area) for the API/database badges that predate this module.
  Shows a red alert when `database.migrations_pending` is set — `current_revision` and
  `head_revision` differ either way, whether the code hasn't been migrated yet or the database is
  ahead of what the running code ships. Its Backups card shows an orange alert when
  `last_backup_at` is missing or older than twice a hardcoded default interval (`GetSystemConfig`
  has no `backup_interval_hours`; that value only exists as `compose.yaml`'s `backup` service
  schedule, not a backend setting).
- `pages/admin/AdminBackupsPage.tsx` (`/admin/backups`) — table of backups with a per-row download
  link and a "Create backup now" button; restore stays CLI-only (no UI/API for it), so the page
  only points at the `time-reporting restore` command.

Frontend version and git SHA come from the `__APP_VERSION__`/`__GIT_SHA__` globals declared in
`vite-env.d.ts`, injected by `vite.config.ts`'s `define` from `package.json`'s `version` and the
`VITE_GIT_SHA` build arg baked into `frontend/Dockerfile`'s image (`__GIT_SHA__` is `null` outside
Docker) — the same pattern as the backend's `APP_GIT_SHA` setting.
