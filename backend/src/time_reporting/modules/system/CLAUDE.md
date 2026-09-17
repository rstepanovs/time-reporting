# system module

Owns no tables — reports the running backend's status and a read-only view of its non-secret
configuration, for `/admin/system/*` and `/admin/backups/*` (both `AdminDep` only, `router` and
`backups_router` respectively — see `router.py`).

## Status and configuration

- `GetSystemStatus(started_at)` → `SystemStatusDTO`: `backend_version` (`importlib.metadata`),
  `git_sha` (the `APP_GIT_SHA` setting, baked into the Docker image at build time — `None` outside
  Docker), a `DatabaseStatusDTO` (server version, size, connection count, and `current_revision` /
  `head_revision` / `migrations_pending` comparing the `alembic_version` table against the head of
  the migration scripts the running code ships, loaded through Alembic's `ScriptDirectory` from the
  `alembic_config_path` setting), per-table row estimates from `pg_stat_user_tables`, uptime
  computed from `started_at` (the router reads this from `app.state.started_at`, set once in
  `main.create_app` — not domain data this module could otherwise obtain, so it's a field on the
  query rather than read from settings or the database), and `last_backup_at` (from
  `BackupService.last_backup_at()`, the same value `ListBackups` reports).
- `GetSystemConfig` → `SystemConfigDTO`: a deliberate whitelist of settings safe to show an admin,
  including the backup settings below and the `expenses` module's `attachment_dir`/
  `attachment_max_bytes` (read from the same `Settings`, since this module owns the whitelist, not
  the individual settings). Never add `jwt_secret_key` or anything derived from `database_url` to
  it.
- `SystemRepository` runs raw SQL against PostgreSQL catalogs (`pg_database_size`,
  `pg_stat_activity`, `pg_stat_user_tables`, `alembic_version`) — no ORM models, since this module
  owns no tables of its own.

## Backups

- `BackupService` (`backup_service.py`) is pure subprocess/filesystem orchestration — no
  `AsyncSession`, so it's fully unit-testable by stubbing `asyncio.create_subprocess_exec`:
  - `create(revision=...)` takes a lock file (`os.open` with `O_CREAT | O_EXCL`, so a concurrent
    call raises `BackupInProgressError` instead of racing) and runs
    `pg_dump --format=custom --file <tmp> <dsn>` into a dotfile-named temp path in `backup_dir`,
    renamed to `time-reporting-<UTC timestamp>-<revision>.dump` only once `pg_dump` exits 0 (a
    failure — non-zero exit or timeout — deletes the temp file and raises `BackupFailedError`;
    stderr's tail is logged, never returned to the API caller). Calls `prune()` on success.
  - `list()` / `last_backup_at()` read `backup_dir` directly (no index file); `prune()` keeps the
    newest `backup_retention_count`.
  - `path_for(name)` is the only way a name from a URL path parameter becomes a filesystem path:
    `parse_backup_filename` (also used by `list()`) doubles as validation, since only a name this
    service could have produced matches the pattern — no path traversal.
  - `restore(path)` runs `pg_restore --clean --if-exists --single-transaction --no-owner`; CLI-only
    (`cli.py`'s `restore` command), never exposed over HTTP.
  - The DSN passed on the command line never carries the password (`_libpq_connection` strips it
    from `database_url` via `sqlalchemy.engine.make_url`); it goes to the subprocess only through
    the `PGPASSWORD` environment variable.
- `CreateBackup(only_if_migrations_pending=..., actor_id=...)` (command) → `BackupInfoDTO | None`:
  `False` (the API's "create backup now") always backs up and never returns `None`; `True` (the
  CLI's `backup --if-pending-migrations`, used by the `migrate` compose service before applying
  migrations) skips and returns `None` when there's no `alembic_version` yet (nothing to protect)
  or the database is already at head — otherwise it backs up under the *current* (pre-migration)
  revision. `actor_id` is set only by the "create backup now" route; a successful backup records a
  `RecordAuditEvent` (`backup.created`) only when it is set, so CLI/scheduled backups (`actor_id`
  always `None` there) are never logged — see `audit/CLAUDE.md`.
- `ListBackups` (query) → `BackupListDTO` (`backups`, `last_backup_at`); `GetBackupPath(name)`
  (query) → `Path`, used only by the download route.
- `GET /admin/backups`, `POST /admin/backups`, `GET /admin/backups/{name}` (`FileResponse`).
  `BackupInProgressError` → 409, `BackupFailedError` → 500, `BackupNotFoundError` → 404.
