# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Time tracking with subsequent billing. Monorepo containing a Python API (`backend/`) and a React web
client (`frontend/`). Infrastructure, a health-check endpoint, and user accounts with JWT
authentication exist; domain models (projects, time entries, invoices) do not yet.

## Commands

Dependencies are not installed yet in a fresh checkout — run `uv sync` and (in `frontend/`) `npm install`
first. Both create lock files (`uv.lock`, `frontend/package-lock.json`) that must be committed; CI and
Docker builds install strictly from them (`uv sync --locked`, `npm ci`).

### Backend (run from repository root — the uv workspace root)

```sh
uv sync                                                          # install/update deps
uv run uvicorn time_reporting.main:app --reload                 # dev server; docs at /api/docs
uv run pytest                                                    # all tests
uv run pytest backend/tests/test_health.py::test_liveness        # single test
uv run ruff check .                                              # lint
uv run ruff format .                                             # format
uv run mypy                                                      # type check (strict)
uv run alembic -c backend/alembic.ini upgrade head               # apply migrations
uv run alembic -c backend/alembic.ini revision --autogenerate -m "describe change"
uv run time-reporting create-admin --email you@example.com --name "You"   # first admin account
```

### Frontend (run from `frontend/`)

```sh
npm run dev         # dev server at :5173, proxies /api to http://localhost:8000
npm run gen:api     # regenerate src/api/schema.d.ts from the running backend's OpenAPI schema
npm run lint
npm run typecheck   # tsc -b
npm test            # vitest run
npm run build
```

### Full stack via Docker Compose

```sh
cp .env.example .env
docker compose up --build   # frontend :8080, backend :8000
```

`compose.yaml` runs services in dependency order: `db` (Postgres) → `migrate` (one-shot `alembic upgrade
head`) → `backend` → `frontend` (nginx, proxies `/api/` to `backend`).

## Architecture

### Backend (`backend/src/time_reporting/`)

- **`main.py`** — `create_app()` FastAPI factory; app-level concerns (CORS, lifespan/engine disposal,
  OpenAPI/docs paths) live here, not in routers.
- **`core/config.py`** — `Settings` (pydantic-settings), read from environment / `.env`, accessed via the
  cached `get_settings()`.
- **`db/base.py`** — declarative `Base` with an explicit `MetaData` naming convention, so Alembic
  autogenerate produces stable, deterministic constraint names.
- **`db/session.py`** — async engine + `async_sessionmaker`; `get_session()` is the FastAPI dependency for
  a request-scoped `AsyncSession`.
- **`api/router.py`** — the single root `APIRouter`, mounted with prefix `/api/v1`; every route lives
  under that prefix. Cross-cutting routers (health) go in `api/routes/`; feature routers live inside
  their module (see below) and are included here.
- **`api/deps.py`** — shared FastAPI dependencies: `SessionDep` (a request-scoped `AsyncSession`) and
  `BusDep` (a `Bus` built from that session and the app's frozen `HandlerRegistry`).
- **`models/__init__.py`** — re-exports `Base` and must import every model module (via each module's
  `models.py`), so Alembic autogenerate (via `migrations/env.py`, which imports `time_reporting.models`)
  sees the full metadata.
- **`migrations/env.py`** — async Alembic environment; reads the DB URL from `Settings`, not from
  `alembic.ini`, so it always agrees with the running app.
- **`cli.py`** — the `time-reporting` console script (`[project.scripts]` in `backend/pyproject.toml`);
  currently only `create-admin`, run through a `Bus` built the same way as in a request.

### Feature modules (`modules/`) and the CQRS bus

Domain functionality lives in self-contained modules under `modules/<name>/`, each typically with
`contracts.py`, `models.py`, `repository.py`, `service.py`, `handlers.py`, `module.py`, `schemas.py`
and `router.py`. **A module may import from another module only its `contracts.py`** (plus
`auth.dependencies` for the HTTP route guards every router needs) — never another module's `models`,
`repository` or `service` directly. `tests/test_module_boundaries.py` enforces this with an AST check
over every file in `modules/`.

Modules talk to each other exclusively through the in-process CQRS bus in `core/cqrs.py`:
- `Command[R]` / `Query[R]` are typed messages; concrete ones live in each module's `contracts.py`
  alongside the DTOs they return (never raw ORM entities) and the module's domain exceptions.
- `HandlerRegistry` maps a message type to a handler factory; each module's `module.py` registers its
  handlers, and `modules/registry.py:build_registry()` composes all of them. It is built once in
  `main.create_app()` (`app.state.handlers`) and frozen — no registration afterwards.
- `Bus(registry, session)` dispatches `await bus.execute(command)` / `await bus.query(query)`. All
  handlers reached from one `Bus` share its `AsyncSession`; the **outermost** `execute()` commits on
  success and rolls back on exception, nested commands and all queries never commit — services and
  repositories only `flush()`. Query handlers must not call `execute()`.
- `api/deps.py:BusDep` builds a request-scoped `Bus`; `cli.py` builds one per invocation the same way.

The **users** module (`modules/users/`) owns the `User` entity, roles (`UserRole`: `admin`,
`project_manager`, `worker`) and account management (admin CRUD, `/users/me`, password change/reset).
The **auth** module (`modules/auth/`) owns JWT issuing/validation and login, and reaches user data only
through `users.contracts` messages (`GetUserCredentialsByEmail`, `RecordSuccessfulLogin`, ...) — it never
imports `users.models` or `users.repository`. `auth/dependencies.py` (`CurrentUserDep`, `require_roles`,
`AdminDep`) is the one exception to the "only `contracts.py`" rule: every protected router depends on it
directly. Role and `is_active` are re-read from the database on every request (via the token's `sub`),
not trusted from the token, so deactivation/role/password changes take effect immediately — enforced by
comparing the token's `ver` claim against the user's current `token_version`, which password
changes/resets increment.

`core/passwords.py` (Argon2id via `pwdlib`, hashing off the event loop in a thread) and
`db/mixins.py:TimestampMixin` (`created_at`/`updated_at`) are shared kernel, not owned by a module.

### Frontend (`frontend/src/`)

- **`api/schema.d.ts`** — generated by `openapi-typescript` (via `npm run gen:api`) from the backend's
  live OpenAPI schema. Currently hand-written to match the scaffold's endpoints; regenerate after adding
  backend routes rather than hand-editing it further.
- **`api/client.ts`** — typed `openapi-fetch` client built from that schema; paths already include the
  `/api/v1` prefix.
- **`api/queryClient.ts`** — shared TanStack Query `QueryClient`.
- **`router.tsx`** — `createBrowserRouter` route tree; page components live in `pages/`, shared chrome
  (e.g. `AppShell`) in `components/`.
- **`App.tsx`** — top-level provider composition: `MantineProvider` → `DatesProvider` →
  `QueryClientProvider` → `RouterProvider`.
- **`test/setup.ts`** — Vitest setup (jsdom polyfills for `matchMedia`/`ResizeObserver` that Mantine
  needs, RTL cleanup). Wired in via `vite.config.ts`'s `test.setupFiles`.

### API convention

All backend routes are namespaced under `/api/v1`; the frontend calls relative `/api` paths (dev: Vite
proxy in `vite.config.ts`; prod: nginx `location /api/` in `frontend/nginx.conf`), so no absolute backend
URL is hardcoded in the frontend.

## Auth

- `JWT_SECRET_KEY` is a **required** setting (`core/config.py`, min 32 chars) — generate with
  `openssl rand -hex 32`; set it in `.env` for local dev, it's already required by `compose.yaml` and
  CI. There is no self-registration endpoint: create the first administrator with
  `uv run time-reporting create-admin`, then manage further accounts via `POST/GET/PATCH /users` (admin
  only) or `PUT /users/{id}/password`.
- Access tokens only (no refresh tokens) — `POST /auth/login` (OAuth2 password form; `username` is the
  email) returns a bearer token good for `access_token_expire_minutes` (default 60).
- Tests need a running, migrated Postgres (`docker compose up -d db`, then `alembic upgrade head`):
  `tests/conftest.py`'s `db_session` fixture runs each test in a rolled-back transaction on a real
  connection, so there is no SQLite/mock fallback.

## Stack notes

- Python 3.13, managed as a **uv workspace**: the root `pyproject.toml` (not itself a package,
  `tool.uv.package = false`) declares `backend` as a workspace member; ruff/mypy/pytest are configured
  once at the root and apply to `backend/`.
- TypeScript is pinned to `~5.9` (not the latest major) because `typescript-eslint` requires `<6.1` and
  `openapi-typescript` requires `^5.x`.
- Node 24 is required (see `frontend/.nvmrc`) — `react-router@8` and `jsdom@30` need Node ≥ 22.22.
