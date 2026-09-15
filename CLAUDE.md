# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Time tracking with subsequent billing. Monorepo containing a Python API (`backend/`) and a React web
client (`frontend/`). Infrastructure, a health-check endpoint, user accounts with JWT authentication,
customers and their projects, a shared non-working-day calendar, and weekly timesheets all exist;
the remaining domain model (invoices) does not yet.

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
uv run time-reporting seed-demo                                  # demo users (password demo-password) + customers
uv run time-reporting import-holidays --year 2026                # add a year's public holidays to the calendar
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
  `create-admin` and `seed-demo`, each run through a `Bus` built the same way as in a request.
- **`seed.py`** — demo data for local development (one user per role, sharing the password
  `demo-password`, active and archived customers, and a few projects with members per customer).
  Idempotent: existing emails/customer or project names are skipped. Projects are created for each
  customer before it is archived (creating a project requires an active customer); tests seed
  uniquely renamed copies, because the test database doubles as the dev database. Also imports the
  current and next year's public holidays plus one demo bridge day, and books normal working hours
  for the demo worker and project manager on every working day of the last 3 months (plus a little
  overtime/travel time each month), so the worker dashboard's month calendar and year-hours table
  both have data — each skipped once already present, so re-running stays idempotent too.

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
`AdminDep`, `ManagerDep`) is the one exception to the "only `contracts.py`" rule: every protected
router depends on it directly. Role and `is_active` are re-read from the database on every request (via
the token's `sub`), not trusted from the token, so deactivation/role/password changes take effect
immediately — enforced by comparing the token's `ver` claim against the user's current
`token_version`, which password changes/resets increment.

The **customers** module (`modules/customers/`) owns the `Customer` entity: name, legal details, a
structured billing address (ISO 3166-1 alpha-2 country), a billing period (`interval_count` ×
`BillingIntervalUnit`, counted from `anchor_date`), currency (ISO 4217) and payment terms. Any
authenticated user can read them; writes require `ManagerDep` (`admin` or `project_manager`).
`UpdateCustomer` treats `None` as "unchanged"; optional text fields are cleared by naming them in
`clear_fields`, which the router fills from fields sent as JSON `null`. `ListCustomers` filters by a
`search` substring against name or legal name. Deleting is archive-by-default, permanent-on-request
— see the **admin** module below; `DeleteCustomer` (permanent) fails with `CustomerInUseError` while
the customer still has any project.

The **projects** module (`modules/projects/`) owns the `Project` entity (belongs to one `Customer`,
`customer_id` immutable after creation) and `ProjectMember`, a plain user↔project link with no
per-project role. Project names are unique per customer, not globally. Creating a project, or
reactivating one, requires its customer to currently be active, but archiving a customer does not
cascade to its projects. Only active users can be added as members, and only to an active project; a
member later deactivated stays listed (with `is_active=false`) rather than disappearing. Access
follows customers: any authenticated user can read projects and members, `ManagerDep` is required to
create/update projects and to add/remove members. `ListProjects` filters by `customer_id`,
`member_id` and a `search` substring against the name. Cross-module display data (a project's
customer name, a member's name and email) is fetched via batch queries — `GetCustomersByIds` /
`GetUsersByIds` in the respective modules' `contracts.py` — rather than joining across modules;
`Project`/`ProjectMember` reference `customers.id` / `users.id` by table name only, never by
importing those modules' `models`. `DeleteProject` (permanent) cascades to its members (FK
`ON DELETE CASCADE`). `GetProjectsByIds` / `GetProjectBillingItemsByIds` (batch, like the customer/user
ones above) and `ListMemberProjectsWithBillingItems` (a user's active projects with their active
billing items, one round trip) exist for the **timesheets** module below to consume without joining
into these tables directly.

The projects module also owns `ProjectBillingItem`: the positions a project's invoices will be made
of (normal/overtime/travel hours, per diems, purchasing/other expenses), each with an immutable
`unit` (`hour`, `day` or `amount`) and, depending on that unit, a `unit_rate` or a `markup_percent`
in the customer's currency. Creating a project creates its six defaults (`DEFAULT_BILLING_ITEMS`,
unpriced); further items are added directly to one project (there is no catalog shared across
projects). Access mirrors projects: any authenticated user reads them, `ManagerDep` adds/edits/
archives/restores, and permanently deleting one — blocked by a foreign key once time entries
reference it, reported as `BillingItemInUseError` — is admin only, like every other permanent
delete. `DeleteProject` cascades to its billing items as well as its members.

The **users** module also exposes `GET /users/directory` (`ManagerDep`): a minimal, active-only,
search-filtered user list for pickers (e.g. adding a project member), since `GET /users` itself is
admin-only. Both `users.ListUsers` and `customers.ListCustomers`-style listing now support this
through repository-level search helpers; `db/queries.py:escape_like` is the shared kernel helper for
building a literal (non-wildcard) `ILIKE` pattern from user input, reused by both modules.
`DeleteUser` (permanent) rejects deleting yourself and fails with `UserInUseError` while the user is
still a project member; `RemoveUserFromAllProjects` clears its memberships first (see below).

The **work_calendar** module (`modules/work_calendar/`) owns `NonWorkingDay`: one company-wide
calendar of public holidays, bridge days and company days off (`NonWorkingDayKind`), each on a unique
date. Weekends are computed, not stored. `GetCalendarDays(date_from, date_to)` (capped at 366 days)
returns every day in the range flagged with `is_weekend` and its `NonWorkingDayDTO` if any — the one
query the timesheets module and its UI need to render a week. `ImportPublicHolidays(year)` adds a
year's holidays from the `holidays` PyPI library for the country (and optional subdivision) in
`Settings.holiday_country`/`holiday_subdivision`, skipping dates already present (manually added or
previously imported) so it's safe to re-run; an unsupported country/subdivision raises
`HolidayCountryNotSupportedError`. Any authenticated user reads the calendar; only admins add, edit
(`day`/`name`; `kind` is immutable), delete or import. Also reachable via the
`time-reporting import-holidays --year` CLI command.

The **timesheets** module (`modules/timesheets/`) owns `TimeEntry`: at most one row per (user,
billing item, date), holding a `quantity` in the billing item's `unit` (hours, days or a money
amount) and an optional note. `project_id` and `unit` are denormalized onto the row from the billing
item at write time (never changed afterwards) so this module's own queries — summing a user's hours
for a day, filtering by project — never join into the projects module's tables; both are guarded by
`ON DELETE RESTRICT`, so a project, billing item or user with time entries can't be permanently
deleted. `GetTimesheetWeek(user_id, week_start, viewer_id)` reads a Monday-to-Sunday week (raises
`WeekStartNotMondayError` otherwise): its rows carry `is_open` (from `projects.contracts`'
`ListMemberProjectsWithBillingItems` — still a member, project and billing item both active) so a
week keeps showing entries booked before a project was archived or the user removed, but read-only;
`can_edit` is just `viewer_id == user_id`, since only the router enforces who may view someone else's
week (admin or project manager) — the query itself doesn't authorize. `SaveTimesheetWeek` applies a batch
of cell changes (`quantity=None` deletes a cell) as one command: validates the week/dates/no-
duplicate-cells first, then that every targeted row is open (`TimesheetRowClosedError`, or
`TimesheetBillingItemNotFoundError` if the item doesn't exist at all) and each quantity is in range
for its unit, applies them, and only then re-checks that the user's total `hour`-unit quantity per
day is still ≤ 24 (`DailyHoursExceededError`) — checked after applying the batch specifically so
moving hours between two rows in one save works even though an intermediate per-change state would
not. Any authenticated user reads and writes their own week; `CountTimeEntries` (filterable by user/
project/billing item) backs the admin module's removal-impact reporting below. `GetMonthCalendar(user_id,
year, month, today)` and `GetYearHours(user_id, year, today)` back the worker dashboard: the former
renders a month as full ISO weeks with expected-vs-booked `hour`-unit totals per day/week (expected
hours = working days, from `GetCalendarDays`, times `Settings.daily_working_hours`); the latter sums
a year's `hour`-unit entries by month, split by billing item preset (`normal_hours`/`overtime_hours`/
`travel_hours`, any other preset or a custom item as `other_hours`) with a per-project breakdown —
`day`/`amount`-unit entries (per diems, expenses) aren't part of either, the dashboard is hours-only.
`today` is a field of both queries (the router fills in the real date) so "expected to date" and
"which month is current" stay deterministic in tests. `GetMonthTimeSummary(user_id, year, month,
today)` and `GetWeeklyHours(user_id, weeks, today)` back the dashboard's widget cards: the former is
one month's hours (as `HoursTotalsDTO`) plus the benefits `HoursTotalsDTO` leaves out —
`day`-unit entries as `per_diem_days`, `amount`-unit entries summed per customer currency (never
combined across currencies) as `expenses`; the latter is `weeks` ISO weeks ending with `today`'s
week (oldest first, capped at `MAX_WEEKLY_HOURS_WEEKS` = 26, `WeekRangeOutOfBoundsError` outside
that) with a per-project hour breakdown over the whole range for the accompanying table. All four
queries follow the week endpoint's view rule (own data, or another user's for admin/project
manager) via the HTTP layer's `_resolve_target_user`.

The **admin** module (`modules/admin/`) owns no tables — it orchestrates archiving or permanently
deleting a user, customer or project by calling the owning module's commands, reached only through
`users.contracts` / `customers.contracts` / `projects.contracts`. `RemoveUser` / `RemoveCustomer` /
`RemoveProject` (`AdminDep` only, under `/admin`) default to archiving (the same
`UpdateUser`/`UpdateCustomer`/`UpdateProject` a manager already uses) and, with `permanent=True`,
permanently delete once nothing blocks it: a customer with any project, or a user deleting
themselves, raise `RemovalBlockedError` / `SelfRemovalError` (409 / 400) without changing anything;
deleting a user first removes its project memberships (`RemoveUserFromAllProjects`) so the
`ON DELETE RESTRICT` foreign key doesn't get in the way, and deleting a project cascades to its
members. `GetUserRemovalImpact` / `GetCustomerRemovalImpact` / `GetProjectRemovalImpact` report what
a permanent delete would affect (`blockers`, `effects`) before the user confirms; they're built only
from each module's own contract queries (`ListProjects`, `ListProjectMembers`,
`ListProjectBillingItems`, `timesheets.contracts.CountTimeEntries`), never new cross-module queries.
A project's impact always lists a `project_billing_items` effect, since every project has at least
its six defaults. A user or project with any time entries gets a `time_entries` blocker
(`RemovalBlockerKind`); deleting either maps the resulting FK violation to `UserInUseError` /
`ProjectInUseError` the same way an existing membership or project already did. A
same-outer-command failure (e.g. the delete itself fails after memberships were already removed)
rolls back the whole `RemoveUser` command, per the bus's transaction rule.
Archiving stays reachable directly through the owning module's existing `PATCH` endpoint too
(`ManagerDep`); only the permanent-delete path is admin-only.

`core/passwords.py` (Argon2id via `pwdlib`, hashing off the event loop in a thread), `db/queries.py`
(`escape_like`) and `db/mixins.py:TimestampMixin` (`created_at`/`updated_at`) are shared kernel, not
owned by a module.

### Frontend (`frontend/src/`)

- **`api/schema.d.ts`** — generated by `openapi-typescript` (via `npm run gen:api`) from the backend's
  live OpenAPI schema. Regenerate after changing backend routes; never hand-edit it.
- **`api/client.ts`** — typed `openapi-fetch` client built from that schema; paths already include the
  `/api/v1` prefix. A middleware sends the `X-Requested-With` CSRF header on every request and, on any
  401, marks the app signed out (sets the `currentUserQueryKey` query data to `null`).
- **`api/queryClient.ts`** — shared TanStack Query `QueryClient`.
- **`auth/`** — the web session: `api.ts` (current user, sign in/out, password change, typed errors),
  `hooks.ts` (`useCurrentUser`, `useAuthenticatedUser`, `useSignIn`, `useSignOut`, `useChangePassword`)
  and `RequireAuth.tsx` (route guard redirecting to `/login` with the page to return to). Signing in or
  out drops every cached query, so no data leaks between users; explicit sign-out and password change
  navigate to `/login` with `flushSync`, so the next sign-in does not return to the page left behind.
- **`customers/`** / **`users/`** — `api.ts` (typed calls for the endpoints each module needs, plus
  their own conflict/rule/not-found error classes — `CustomerConflictError`/`UserEmailConflictError`
  (409), `UserRuleError` (400), `CustomerNotFoundError`/`UserNotFoundError` (404)) and `hooks.ts`
  (`customerKeys`/`userKeys` + list/detail queries and create/update mutations, e.g. `useCustomers`,
  `useCreateCustomer`, `useUpdateCustomer`, `useUsers`, `useCreateUser`, `useUpdateUser`,
  `useResetUserPassword`, `useUserDirectory`). `CustomerFormModal.tsx` (customers/) and
  `UserFormModal.tsx` + `ResetPasswordModal.tsx` (users/) are the create/edit forms the `/admin`
  pages use; elsewhere (e.g. the projects customer picker) only the read-only `useCustomers` is
  needed.
- **`projects/`** — `api.ts` (typed calls for all `/projects` endpoints plus `ProjectConflictError`
  (409) / `ProjectRuleError` (400, backend `detail` as the message) / `ProjectNotFoundError` (404),
  and for billing items `BillingItemConflictError` (409 name) / `BillingItemInUseError` (409 on
  delete, a different meaning than a project's own 409, mapped separately)),
  `hooks.ts` (`projectKeys` + `useProjects`/`useProject`/`useProjectMembers`/`useProjectBillingItems`
  queries and `useCreateProject`/`useUpdateProject`/`useAddProjectMember`/`useRemoveProjectMember`/
  `useAddProjectBillingItem`/`useUpdateProjectBillingItem`/`useDeleteProjectBillingItem` mutations,
  all invalidating `projectKeys.all` on success), `ProjectFormModal.tsx` (shared create/edit form used
  by `pages/ProjectsPage.tsx`, `pages/ProjectDetailsPage.tsx` and `pages/admin/AdminProjectsPage.tsx`;
  an optional `onCreated` callback lets the admin page stay put instead of navigating to the new
  project), and `BillingItemFormModal.tsx` (create/edit a billing item; the unit is locked once
  editing, and its rate/markup field swaps by unit). `pages/ProjectDetailsPage.tsx`'s "Billing items"
  section is readable by anyone, editable by managers, and offers "Delete permanently" to admins
  only — the one write in this router that isn't `ManagerDep`.
- **`calendar/`** — `api.ts` (calendar days, non-working-day CRUD, public-holiday import, plus
  `NonWorkingDayConflictError` (409 date taken) / `NonWorkingDayNotFoundError` (404) /
  `CalendarRuleError` (400)) and `hooks.ts` (`calendarKeys` + `useCalendarDays`/`useNonWorkingDays`
  queries and add/update/delete/import mutations, all invalidating `calendarKeys.all`).
  `NonWorkingDayFormModal.tsx` (create/edit; `kind` is locked once editing, like a billing item's
  unit) backs `pages/admin/AdminCalendarPage.tsx`.
- **`timesheets/`** — `api.ts` (read/save a week, the caller's project/billing-item picker, the
  dashboard's `getMonthCalendar`/`getYearHours`/`getMonthTimeSummary`/`getWeeklyHours`, plus
  `TimesheetRuleError` covering 400/403/404 with the backend's `detail` as the message) and
  `hooks.ts` (`timesheetKeys` + `useTimesheetWeek`/`useTimesheetOptions`/`useMonthCalendar`/
  `useYearHours`/`useMonthTimeSummary`/`useWeeklyHours` queries and `useSaveTimesheetWeek`, which
  writes the mutation result straight into the week's query cache instead of invalidating, and also
  invalidates `timesheetKeys.summaries()` so the dashboard and `/hours` pick up a save). `week.ts`
  holds pure ISO-date helpers (`startOfIsoWeek`, `weekDays`, `addWeeks`, `addMonths`/`previousMonth`,
  day/week/month/ISO-week label formatting, `formatHours`, `fillRatePercent`) with their own unit
  tests. `dayKind.ts` (weekend/holiday/bridge background colors) and `dayStatus.ts` (a calendar
  day's status — off/future/today/complete/partial/missing/extra — versus its expected hours) are
  pure helpers shared by `TimesheetGrid.tsx` (the weekly grid: local draft state holds only actual
  edits keyed by billing-item+date, so Save sends just the changed cells and a closed row renders
  read-only), `AddRowModal.tsx` ("add a row" / "copy rows from previous week"), and the month
  calendar below. `pages/TimesheetPage.tsx` uses the grid.
  `MonthCalendarTable.tsx`/`YearHoursTableView.tsx` are presentational (already-loaded data as
  props, an optional `title` override, `title=""` to hide it) — weeks as rows/Mon..Sun as columns
  with the week number linking to `/timesheet?week=`, and one row per month (newest first, columns
  per hours category plus Δ against hours expected to date, expanding into a per-project
  breakdown) respectively; `MonthCalendar.tsx`/`YearHoursTable.tsx` are thin data-loading wrappers
  around them, reused by `pages/HoursPage.tsx` (`/hours`, month navigation via a `?month=YYYY-MM`
  param) and, for the current/previous month, by the dashboard's `MonthTimeCard.tsx`. The
  dashboard's other widgets: `QuickActionsCard.tsx` ("Report time" / "Previous week" shortcuts to
  `/timesheet`), `MonthTimeCard.tsx` (one month's hours by preset, a reported/expected-to-date
  total with fill rate %, and per-diem/expense benefits, linking to `/hours?month=`),
  `WeeklyHoursChart.tsx` (`@mantine/charts` `CompositeChart`: hours booked per week as bars against
  expected hours as a dashed reference line on the *same* hours axis — never a fill-rate-% line on
  a second axis — over the last 6 ISO weeks), `WeeklyProjectHoursCard.tsx` (each project's
  total/overtime hours over that same 6-week window, sharing `WeeklyHoursChart`'s query/cache) and
  `MyProjectsCard.tsx` (the user's projects, linking to each). All five widgets render inside
  `components/DashboardCard.tsx`, the shared card frame (title, content, an optional "Details →"
  style footer link, a highlight tint via `data-highlighted`). `pages/DashboardPage.tsx` composes
  them in a responsive `SimpleGrid`.
- **`admin/`** — the shared archive-or-delete UI for all three entities: `api.ts`
  (`getRemovalImpact`/`removeEntity` against `/api/v1/admin/...`, plus `RemovalBlockedError` (409,
  carries `blockers`), `RemovalRuleError` (400) and `RemovalNotFoundError` (404)), `hooks.ts`
  (`useRemovalImpact` — fetched only while a dialog is open — and `useRemoveEntity`, which also
  invalidates the projects lists for users/customers), and `RemoveEntityModal.tsx`: archives by
  default, offers a "Delete permanently" checkbox disabled with the blocking reason when other data
  references the record, and shows what else a permanent delete would remove once checked.
- **`auth/roles.ts`** — `canManage` (admin or project manager) and `isAdmin`; `auth/RequireRole.tsx`
  renders its children only for a signed-in user with one of the given roles, the plain not-found
  page otherwise (so a non-admin can't tell `/admin` exists), and must be nested inside `RequireAuth`.
- **`pages/admin/`** — `AdminUsersPage`/`AdminCustomersPage`/`AdminProjectsPage`: each lists its
  entity with a debounced search and an archived/inactive toggle, and a per-row menu (Edit,
  role/entity-specific actions like Reset password or Restore, Remove… via `RemoveEntityModal`). An
  admin cannot edit their own role/active status or remove themselves from `AdminUsersPage`.
  `AdminSystemStatusPage` (`/admin/status`) just polls the health endpoints for an API/database badge.
- **`router.tsx`** — route tree (`routes`, also used by tests): `/login` is public, everything else sits
  under `RequireAuth` → `AppLayout`. Page components live in `pages/`, shared chrome in `components/`.
  `/` (`DashboardPage`) is the default landing page: quick actions, this/last month's time,
  hours-per-week chart and per-project table, and the user's projects, all as widget cards.
  `/timesheet` (query params `week`/`user`) is where time is actually booked; `/hours` (query param
  `month`) is the fuller month-calendar-and-year-table view a "Details →" card links into.
  `/admin/{users,customers,projects,calendar,status}` sit under `RequireRole roles={["admin"]}`,
  with `/admin` redirecting to `/admin/users`.
- **`components/AppLayout.tsx`** — the signed-in shell: header with the account menu and an
  `AppShell.Navbar` (collapsible on mobile via a `Burger`) linking to the pages in `pages/`
  (Dashboard, Timesheet, My hours, Projects, in that order), plus an "Administration" nav group
  (Users/Customers/Projects/Calendar/System status) shown only when `isAdmin(user.role)`.
  `components/DashboardCard.tsx` is the shared frame the dashboard's widget cards render inside.
- **`App.tsx`** — top-level provider composition: `MantineProvider` → `DatesProvider` →
  `QueryClientProvider` → `RouterProvider` (imported from `react-router/dom`, which `flushSync`
  navigation requires).
- **`test/setup.ts`** — Vitest setup (jsdom polyfills for `matchMedia`/`ResizeObserver`/`document.fonts`
  that Mantine needs, RTL cleanup, and cleaning `@mantine/notifications`'s module-level queue — it
  outlives the React tree, so a toast shown in one test would otherwise still be queued when the next
  test's `<Notifications />` mounts). Wired in via `vite.config.ts`'s `test.setupFiles`.
  `test/renderApp.tsx` renders the full route tree in a memory router with a fresh `QueryClient`;
  tests mock `@/auth/api` and whichever of `@/projects/api` / `@/customers/api` / `@/users/api` /
  `@/admin/api` / `@/calendar/api` / `@/timesheets/api` the page under test calls. Mantine's
  `DatePickerInput` renders its trigger as a button, not a text input — editing its pre-filled value
  in a test is awkward, so prefer a flow (e.g. edit rather than create) that doesn't need to change
  it. Mantine's `Select` renders an input with
  `role="combobox"`, not `"textbox"`; a required field's `<label>` includes a trailing `*`, so match
  it with a prefix regex (e.g. `getByLabelText(/^name/i)`) rather than the exact label text.

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
