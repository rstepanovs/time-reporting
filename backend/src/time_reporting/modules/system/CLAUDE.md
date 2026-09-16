# system module

Owns no tables — reports the running backend's status and a read-only view of its non-secret
configuration, for the `/admin/system/*` routes (`AdminDep` only).

- `GetSystemStatus(started_at)` → `SystemStatusDTO`: `backend_version` (`importlib.metadata`),
  `git_sha` (the `APP_GIT_SHA` setting, baked into the Docker image at build time — `None` outside
  Docker), a `DatabaseStatusDTO` (server version, size, connection count, and `current_revision` /
  `head_revision` / `migrations_pending` comparing the `alembic_version` table against the head of
  the migration scripts the running code ships, loaded through Alembic's `ScriptDirectory` from the
  `alembic_config_path` setting), per-table row estimates from `pg_stat_user_tables`, and uptime
  computed from `started_at` (the router reads this from `app.state.started_at`, set once in
  `main.create_app` — not domain data this module could otherwise obtain, so it's a field on the
  query rather than read from settings or the database).
- `GetSystemConfig` → `SystemConfigDTO`: a deliberate whitelist of settings safe to show an admin.
  Never add `jwt_secret_key` or anything derived from `database_url` to it.
- `SystemRepository` runs raw SQL against PostgreSQL catalogs (`pg_database_size`,
  `pg_stat_activity`, `pg_stat_user_tables`, `alembic_version`) — no ORM models, since this module
  owns no tables of its own.
