# Plan: administrator tooling — system status, versions, backups, operations, billing periods, audit log

## Context

The admin area today covers users, customers, projects and the calendar, and `/admin/status` shows
only two health badges (API, database). An administrator can't see which software/database version
is running, can't back up the system, has no documented upgrade/rollback path, can't list sent
billing periods in one place (reopening is hidden on `/team`), and there is no record of who did
what (permanent deletes, level changes, reopened periods).

### Decisions confirmed with the user

1. **Backups run in the backend.** The backend image gets a PostgreSQL 17 client; a
   `time-reporting backup` CLI command writes `pg_dump -Fc` files to a volume with retention; a
   compose service runs it on a schedule. The admin UI can create a backup now, list and download
   backups. **Restore is CLI/runbook only**, never from the UI.
2. **Upgrade/downgrade is not done from the UI.** A script + runbook handles it (backup → pull/build
   → migrate → up); the `migrate` service backs up automatically before applying pending
   migrations. Rollback = previous image + restore from backup (no `alembic downgrade` in
   production). The UI only *shows* versions and flags a code/database revision mismatch.
3. **pgAdmin** is an optional compose profile (`tools`), bound to `127.0.0.1` only; nothing in the
   app changes for it.
4. **In scope as well:** an extended status page (DB size, connections, row estimates, uptime),
   a read-only configuration view (no secrets), an `/admin/billing` page listing sent billing
   periods with reopen, and an audit log (`/admin/audit`).

### Design decisions (flag on review if wrong)

- A new **`system`** module (no tables) owns status, versions, configuration view and backups;
  its routes live under `/api/v1/admin/system/...` and `/api/v1/admin/backups/...`, `AdminDep`
  only. DB statistics come from PostgreSQL catalogs (`pg_database_size`, `pg_stat_activity`,
  `pg_stat_user_tables.n_live_tup`, `alembic_version`), so no cross-module imports are needed.
- A new **`audit`** module owns an `audit_events` table. Other modules record events by executing
  `audit.contracts.RecordAuditEvent` as a nested command inside their own command handler, so the
  event commits or rolls back atomically with the change.
- The billing-period list is a new query in **`timesheets`** (which owns `ProjectBillingPeriod`),
  enriched with project/user names through `GetProjectsByIds` / `GetUsersByIds`.
- Admin navigation order: Users, Customers, Projects, Calendar, Billing, Audit log, Backups,
  System status.

## Tasks

Work on branch `feature/admin-tools`; one commit per task (`T<n>: ...`), each task leaves lint,
typecheck and tests green and updates the `CLAUDE.md` files it affects. First commit: this plan as
`.claude/plans/admin-tools.md`.

### T1 — backend: `system` module, versions and status

- `modules/system/` with `contracts.py`, `repository.py` (raw catalog SQL), `service.py`,
  `handlers.py`, `module.py`, `schemas.py`, `router.py`, `CLAUDE.md`; register in
  `modules/registry.py` and include the router in `api/router.py`.
- Query `GetSystemStatus` → DTO:
  - `backend_version` from `importlib.metadata.version("time-reporting-backend")`, `git_sha` from a
    new `APP_GIT_SHA` setting (default `None`);
  - `database`: server version (`SHOW server_version`), size, current connections,
    `current_revision` (from `alembic_version`), `head_revision` (Alembic `ScriptDirectory` loaded
    from a new `alembic_config_path` setting, default `backend/alembic.ini` — valid both from the
    repo root and the image's `/app`), `migrations_pending` (`current != head`);
  - `tables`: `(name, estimated_rows)` from `pg_stat_user_tables`;
  - `started_at` / uptime — record the start time in `main.lifespan` on `app.state`.
- Query `GetSystemConfig` → an explicit whitelist of non-secret settings (`app_name`, `debug`,
  `cors_origins`, `access_token_expire_minutes`, `auth_cookie_secure`, `holiday_country`,
  `holiday_subdivision`, `daily_working_hours`, backup settings from T3 once they exist). Never
  `jwt_secret_key` or the DB password.
- `GET /admin/system/status`, `GET /admin/system/config` (`AdminDep`).
- `backend/Dockerfile`: `ARG GIT_SHA` → `ENV APP_GIT_SHA`; `compose.yaml` passes the build arg.
- Tests: endpoints require admin; status reports `migrations_pending == False` on the migrated test
  DB; config response contains no secret keys.

### T2 — frontend: System status page

- `frontend/src/system/` area (`api.ts`, `hooks.ts`, `CLAUDE.md`); `npm run gen:api` after T1.
- Rework `pages/admin/AdminSystemStatusPage.tsx`: keep the health badges; add cards for Versions
  (backend version + SHA, frontend version + SHA injected at build time via Vite `define` from
  `package.json` and a `VITE_GIT_SHA` build arg in `frontend/Dockerfile`), Database (Postgres
  version, size, connections, current/head revision with a red alert when migrations are pending
  or the DB is ahead of the code), Tables (row estimates), Uptime, Configuration (read-only list).
- Tests: renders versions; shows the mismatch alert when `migrations_pending`.

### T3 — backend: backups

- `backend/Dockerfile` runtime stage: install `postgresql-client-17` from the PGDG apt repository
  (Debian bookworm ships only 15, which can't dump a 17 server).
- Settings: `backup_dir` (default `backups`, `/var/backups/time-reporting` in compose),
  `backup_retention_count` (default 14), `backup_timeout_seconds`.
- `system` service `BackupService`: builds a libpq DSN from `database_url` (strip `+asyncpg`,
  password via `PGPASSWORD` env, never on the command line); `create()` runs
  `pg_dump --format=custom` with `asyncio.create_subprocess_exec` into a temp file, renames to
  `time-reporting-<UTC timestamp>-<alembic revision>.dump` on success, deletes it on failure;
  a lock file prevents concurrent runs; `prune()` keeps the newest N; `list()`; `path_for(name)`
  validates the name against the file-name pattern (no path traversal).
- Contracts: `CreateBackup` (command), `ListBackups` (query, includes `last_backup_at` also used by
  `GetSystemStatus`), errors `BackupInProgressError` (409), `BackupFailedError` (500 with stderr
  tail logged, generic detail returned), `BackupNotFoundError` (404).
- Endpoints: `GET /admin/backups`, `POST /admin/backups`, `GET /admin/backups/{name}` (`FileResponse`).
- CLI (`cli.py`):
  - `time-reporting backup [--if-pending-migrations]` — the flag backs up only when the DB already
    has an `alembic_version` and it differs from head (used by `migrate`);
  - `time-reporting restore FILE --yes` — `pg_restore --clean --if-exists --single-transaction
    --no-owner`; refuses without `--yes`; prints the revision recorded in the file name.
- Tests: service with a stubbed subprocess (success, failure cleanup, lock, prune, name
  validation); endpoints require admin; one integration test that really runs `pg_dump` is skipped
  when the binary isn't on `PATH`.

### T4 — infrastructure: scheduled backups, pre-migration backup, pgAdmin

- `compose.yaml`:
  - `backups` named volume mounted at `/var/backups/time-reporting` in `backend`, `migrate` and the
    new `backup` service; `BACKUP_DIR` in `x-backend-env`;
  - `migrate` command: `sh -c "time-reporting backup --if-pending-migrations && alembic -c
    backend/alembic.ini upgrade head"`;
  - `backup` service (backend image): loop `time-reporting backup` every `BACKUP_INTERVAL_HOURS`
    (default 24), `restart: unless-stopped`, depends on `migrate` completing;
  - `pgadmin` service under `profiles: [tools]`, `dpage/pgadmin4`, `127.0.0.1:${PGADMIN_PORT:-5050}:80`,
    credentials from `.env`, a mounted `servers.json` pre-registering the `db` server.
- `.env.example`: `BACKUP_RETENTION_COUNT`, `BACKUP_INTERVAL_HOURS`, `PGADMIN_EMAIL`,
  `PGADMIN_PASSWORD`, `PGADMIN_PORT`, `GIT_SHA`.
- `.gitignore`: local `backups/`.
- Verify: `docker compose up --build`, a dump appears in the volume; `docker compose --profile
  tools up pgadmin` reachable on localhost only.

### T5 — frontend: Backups page

- `/admin/backups` (`pages/admin/AdminBackupsPage.tsx`, nav entry, route under
  `RequireRole roles={["admin"]}`): table (file name, created at, size, DB revision), "Create
  backup now" button with loading state and error notification (409 in progress), per-row download
  link, a note that restore is done via the CLI (link to the runbook section by name).
- Status page shows "Last backup" with a warning when older than 2× the interval or missing.
- Tests: list render, create success/409 handling.

### T6 — operations: upgrade script and runbook

- `scripts/upgrade.sh`: `git pull` (or a given ref) → `docker compose build` → `docker compose run
  --rm migrate` (backs up first) → `docker compose up -d`; fails fast (`set -euo pipefail`), passes
  `GIT_SHA=$(git rev-parse --short HEAD)`.
- `docs/operations.md`: install, upgrade, rollback (check out previous ref, rebuild, stop
  `backend`, `docker compose run --rm migrate time-reporting restore <file> --yes`, start),
  backups (location, retention, copying off-host), restore, pgAdmin (profile, SSH tunnel for remote
  hosts), why there is no in-app upgrade and no production `alembic downgrade`.
- Link it from `README.md` and root `CLAUDE.md`.

### T7 — backend: billing periods list

- `timesheets.contracts`: `ListBillingPeriods(project_id | None, customer_id | None, month_from,
  month_to, offset, limit)` → page of `BillingPeriodListItemDTO` (project id/name, customer name,
  period start/end, sent at, sent by id/name), newest first; names via `GetProjectsByIds` /
  `GetUsersByIds` batch queries.
- `GET /billing-periods` (`AdminDep`; accountant access is deferred to the invoices work); reopen
  keeps using the existing `DELETE /billing-periods/{project_id}/{period_start}`.
- Tests: filters, pagination, permission.

### T8 — frontend: Billing page

- `/admin/billing` (`pages/admin/AdminBillingPage.tsx`): filters (project, customer, month range),
  paginated table, per-row "Reopen…" confirm modal reusing the existing reopen mutation from
  `timesheets/hooks.ts` (invalidate the list too).
- Tests: renders rows, reopen flow.

### T9 — backend: audit module

- `modules/audit/`: model `AuditEvent` (`id`, `occurred_at`, `actor_id` → `users` by table name,
  `ON DELETE SET NULL`, `actor_name` snapshot, `action` (StrEnum), `entity_type`, `entity_id`,
  `summary`, `details` JSONB); Alembic migration; index on `(occurred_at desc)` and
  `(entity_type, entity_id)`.
- Contracts: `RecordAuditEvent` (command, never commits on its own — nested), `ListAuditEvents`
  (query: action, entity type, actor, date range, pagination).
- Record events from the owning command handlers (add an `actor_id` field to commands that lack
  one, filled from `CurrentUserDep` in routers and `None` for CLI):
  - users: created, access levels changed, activated/deactivated, password reset by admin;
  - admin: user/customer/project archived or permanently deleted;
  - timesheets: billing period sent, billing period reopened;
  - work_calendar: public holidays imported;
  - system: backup created via API.
- `GET /admin/audit-events` (`AdminDep`).
- Tests: each listed command writes exactly one event; a failing command leaves none (rollback);
  `test_module_boundaries.py` stays green.

### T10 — frontend: Audit log page

- `/admin/audit` (`pages/admin/AdminAuditPage.tsx`): filters (action, entity type, actor, date
  range), paginated table (time, actor, action, summary), expandable details.
- Tests: renders and filters.

### T11 — documentation sweep and dashboard shortcuts

- Root `CLAUDE.md` (modules list, admin routes, Docker services), `pages/CLAUDE.md`,
  `admin/CLAUDE.md`, new module/area `CLAUDE.md` files consistent; `AdminShortcutsCard` gains
  Billing, Audit log, Backups.

## Critical files

- Backend: `modules/registry.py`, `api/router.py`, `main.py` (start time), `core/config.py`,
  `cli.py`, `modules/timesheets/{contracts,service,handlers,router}.py`,
  `modules/users/*`, `modules/admin/*`, `models/__init__.py` (audit model), new
  `modules/system/`, `modules/audit/`, `backend/Dockerfile`.
- Frontend: `router.tsx`, `components/AppLayout.tsx`, `admin/AdminShortcutsCard.tsx`,
  `pages/admin/*`, new `system/`, `audit/` areas, `frontend/Dockerfile`, `vite.config.ts`.
- Infra/docs: `compose.yaml`, `.env.example`, `scripts/upgrade.sh`, `docs/operations.md`,
  `README.md`, `CLAUDE.md`.

## Verification

- Per task: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest`;
  in `frontend/`: `npm run lint && npm run typecheck && npm test && npm run build`.
- End-to-end in Docker: `docker compose up --build`; sign in as admin; `/admin/status` shows
  versions, SHA, DB revision = head, table estimates; create a backup on `/admin/backups` and
  download it; the `backup` service writes a scheduled dump; add a dummy migration locally and
  confirm `migrate` backs up before upgrading; restore a dump via the runbook and confirm data
  returns; `/admin/billing` lists a period sent from `/team` and reopens it; the audit log shows
  the send, reopen and backup events; `docker compose --profile tools up pgadmin` works on
  `127.0.0.1:5050`.
