# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Time tracking with subsequent billing. Monorepo containing a Python API (`backend/`) and a React web
client (`frontend/`). Infrastructure, a health-check endpoint, user accounts with JWT authentication,
customers and their projects, a shared non-working-day calendar, and weekly timesheets all exist;
the remaining domain model (invoices) does not yet.

Detailed notes live next to the code and load only when files in that directory are read:
`backend/src/time_reporting/modules/<module>/CLAUDE.md` for each backend module and
`frontend/src/<area>/CLAUDE.md` for each frontend area (`pages/CLAUDE.md` maps each page to the area
that documents it). Repeatable procedures are project skills in `.claude/skills/` (committing,
opening a PR, seeding demo data).

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
```

Seeding (`create-admin`, `seed-demo`, `import-holidays`) is covered by the `seed-test-data` skill.

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
  `create-admin`, `seed-demo` and `import-holidays`, each run through a `Bus` built the same way as in
  a request.
- **`seed.py`** — idempotent demo data for local development; tests seed uniquely renamed copies,
  because the test database doubles as the dev database. Details: the `seed-test-data` skill.
- **Shared kernel** (not owned by a module): `core/passwords.py` (Argon2id via `pwdlib`, hashing off
  the event loop in a thread), `db/queries.py` (`escape_like` — a literal, non-wildcard `ILIKE`
  pattern from user input) and `db/mixins.py:TimestampMixin` (`created_at`/`updated_at`).

### Feature modules (`modules/`) and the CQRS bus

Domain functionality lives in self-contained modules under `modules/<name>/`, each typically with
`contracts.py`, `models.py`, `repository.py`, `service.py`, `handlers.py`, `module.py`, `schemas.py`
and `router.py`. **A module may import from another module only its `contracts.py`** (plus
`auth.dependencies` for the HTTP route guards every router needs) — never another module's `models`,
`repository` or `service` directly. `tests/test_module_boundaries.py` enforces this with an AST check
over every file in `modules/`. Cross-module display data is fetched via batch queries
(`GetCustomersByIds`, `GetUsersByIds`, ...) rather than joining across modules; a model references
another module's table by table name only.

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

Modules (each documented in its own `CLAUDE.md`):
- **`users`** — `User`, access levels (`admin`/`manager`/`accountant`, combinable, on top of the
  implicit "employee" baseline every account has), account management, user directory.
- **`auth`** — JWT issuing/validation, login/session cookie, route guards (`auth/dependencies.py`).
- **`customers`** — `Customer`: legal details, billing address/period, currency, payment terms.
- **`projects`** — `Project`, `ProjectMember`, `ProjectBillingItem`, a project's `manager_id`.
- **`work_calendar`** — `NonWorkingDay`: the company-wide holiday calendar.
- **`timesheets`** — `TimeEntry`, the weekly submit/approve workflow, dashboards, team overview,
  billing handoff and locking.
- **`admin`** — no tables; orchestrates archiving/permanent deletion of users, customers, projects.

Permanently deleting any entity is admin-only and goes through the `admin` module; archiving uses the
owning module's `PATCH` endpoint (`ManagerDep`).

### Frontend (`frontend/src/`)

- **`api/schema.d.ts`** — generated by `openapi-typescript` (via `npm run gen:api`) from the backend's
  live OpenAPI schema. Regenerate after changing backend routes; never hand-edit it.
- **`api/client.ts`** — typed `openapi-fetch` client built from that schema; paths already include the
  `/api/v1` prefix. A middleware sends the `X-Requested-With` CSRF header on every request and, on any
  401, marks the app signed out (sets the `currentUserQueryKey` query data to `null`).
- **`api/queryClient.ts`** — shared TanStack Query `QueryClient`.
- **Feature areas** — `auth/`, `customers/`, `users/`, `projects/`, `calendar/`, `timesheets/`,
  `admin/`: each typically has `api.ts` (typed calls plus the area's own error classes mapped from
  HTTP status codes, with the backend's `detail` as the message where it's user-facing), `hooks.ts`
  (a `<area>Keys` query-key factory plus TanStack Query queries/mutations) and its modals/components.
  Each area's `CLAUDE.md` has the details.
- **`router.tsx`** — route tree (`routes`, also used by tests): `/login` is public, everything else sits
  under `RequireAuth` → `AppLayout`. Page components live in `pages/` (see `pages/CLAUDE.md`), shared
  chrome in `components/`. `/` (`DashboardPage`) is the default landing page; `/timesheet` (query
  params `week`/`user`), `/hours` (`month`), `/projects`, `/projects/:projectId`,
  `/account/password`; `/approvals` and `/team`
  sit under `RequireRole roles={["admin","project_manager"]}`;
  `/admin/{users,customers,projects,calendar,status}` sit under `RequireRole roles={["admin"]}`, with
  `/admin` redirecting to `/admin/users`.
- **`components/AppLayout.tsx`** — the signed-in shell: header with the account menu and an
  `AppShell.Navbar` (collapsible on mobile via a `Burger`) linking to the pages in `pages/`
  (Dashboard, Timesheet, My hours, Projects, in that order — plus Approvals then Team, inserted
  right after My hours, shown only when `canManage(user.role)`), plus an "Administration" nav group
  (Users/Customers/Projects/Calendar/System status) shown only when `isAdmin(user.role)`.
  `components/DashboardCard.tsx` is the shared frame the dashboard's widget cards render inside
  (title, content, an optional "Details →" style footer link, a highlight tint via
  `data-highlighted`).
- **`App.tsx`** — top-level provider composition: `MantineProvider` → `DatesProvider` →
  `QueryClientProvider` → `RouterProvider` (imported from `react-router/dom`, which `flushSync`
  navigation requires).
- **`test/`** — Vitest setup and the `renderApp` helper; see `test/CLAUDE.md` before writing a
  frontend test.

### API convention

All backend routes are namespaced under `/api/v1`; the frontend calls relative `/api` paths (dev: Vite
proxy in `vite.config.ts`; prod: nginx `location /api/` in `frontend/nginx.conf`), so no absolute backend
URL is hardcoded in the frontend.

## Auth

- `JWT_SECRET_KEY` is a **required** setting (`core/config.py`, min 32 chars) — generate with
  `openssl rand -hex 32`; set it in `.env` for local dev, it's already required by `compose.yaml` and
  CI. There is no self-registration endpoint: create the first administrator with
  `uv run time-reporting create-admin`, then manage further accounts via `POST/GET/PATCH /users` (admin
  only) or `PUT /users/{id}/password`; permanently deleting a user, customer or project goes through
  `DELETE /admin/{users,customers,projects}/{id}` instead (also admin only).
- Access tokens only (no refresh tokens) — `POST /auth/login` (OAuth2 password form; `username` is the
  email) returns a bearer token good for `access_token_expire_minutes` (default 60).
- The web client never sees the token: `POST /auth/session` (JSON `email`/`password`) sets it as an
  `HttpOnly`, `SameSite=Strict`, `Path=/api` cookie (`Secure` unless `AUTH_COOKIE_SECURE=false`), and
  `DELETE /auth/session` clears it. `get_current_user` accepts a bearer header (which wins) or that
  cookie; cookie-authenticated unsafe requests (not GET/HEAD/OPTIONS) must also carry `X-Requested-With`
  or get 403 (CSRF defense). Signing out only clears the cookie — the JWT stays valid until it expires.
- Route guards every router uses: `auth/dependencies.py` — `CurrentUserDep`, `require_roles`
  (admits a user holding *any* of the given levels), `AdminDep`, `ManagerDep`, `AccountantDep`. A
  user's access levels are orthogonal (a plain `CurrentUserDep` is the implicit "employee" every
  account has); levels and `is_active` are re-read from the database on every request, so
  deactivation/level/password changes take effect immediately.
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
- `@mantine/charts` (a `recharts` wrapper) renders the dashboard's hours-per-week chart; its CSS is
  imported once in `main.tsx` alongside Mantine's other stylesheets.
