# frontend system/

Backend: `modules/system`.

- `api.ts` — `getSystemStatus`/`getSystemConfig` against `/api/v1/admin/system/...`, read-only, no
  mutations.
- `hooks.ts` — `systemKeys` + `useSystemStatus`/`useSystemConfig` queries.

Backs `pages/admin/AdminSystemStatusPage.tsx`, which also polls the plain `/health` and
`/health/ready` endpoints directly (not through this area) for the API/database badges that
predate this module. The page shows a red alert when `database.migrations_pending` is set —
`current_revision` and `head_revision` differ either way, whether the code hasn't been migrated
yet or the database is ahead of what the running code ships.

Frontend version and git SHA come from the `__APP_VERSION__`/`__GIT_SHA__` globals declared in
`vite-env.d.ts`, injected by `vite.config.ts`'s `define` from `package.json`'s `version` and the
`VITE_GIT_SHA` build arg baked into `frontend/Dockerfile`'s image (`__GIT_SHA__` is `null` outside
Docker) — the same pattern as the backend's `APP_GIT_SHA` setting.
