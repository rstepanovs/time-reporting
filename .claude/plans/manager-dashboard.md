# Plan: manager dashboard — team timesheets, project staff, month-end handoff to billing

## Context

The dashboard (`pages/DashboardPage.tsx`) is worker-centric: a project manager sees only their own
time. A manager needs to:

1. **Track the timesheets of every worker on every project they manage** — who has submitted,
   who is waiting for approval, who was returned, who hasn't reported yet.
2. **See the staff working on their projects** — members, their hours this month versus expected.
3. **At month end, once all timesheets are in, send the project's month to billing.** Invoicing
   doesn't exist yet, so "send" is a stub that records the handoff and locks the period.

Today there is no notion of "the manager of a project": `ProjectMember` is a plain link without a
per-project role, and every `project_manager` sees and reviews everything.

Target layout (manager section below the existing worker cards, only for `canManage(role)`):

```
My team ─────────────────────────────────────────────────────────────── [My projects ▾ | All]
┌ Timesheets · W37–W38 ──┐┌ Billing · Sep 2026 ───────────────────────┐┌ Staff ─────────────────────┐
│ Awaiting approval   4  ││ Project        Hours  Weeks    Status     ││ Name     Projects  Sep h/exp│
│ Returned            1  ││ ACME·Web        412   18/20  Not ready    ││ Anna W.  ACME·Web  88/96  ⚠│
│ Not submitted       3  ││ Beta·ERP        160    8/8   [Send →]     ││ Bob K.   Beta·ERP 96/96    │
│                        ││ Gamma·App       120    6/6   Sent 01.09   ││ …                          │
│      Approvals →       ││                          Team overview →  ││          Team overview →   │
└────────────────────────┘└───────────────────────────────────────────┘└────────────────────────────┘
```

Plus a full `/team?month=YYYY-MM` page: per managed project, members × ISO weeks intersecting
the month, each cell a status badge + hours linking to `/timesheet?week=&user=`, and the project's
billing status/button in its header.

### Decisions confirmed with the user

1. **"Manages" = `Project.manager_id`**: one responsible manager per project (nullable FK to
   `users`, must be an active `admin` or `project_manager`), set in the project form.
2. **Approval rights stay as they are**: any admin/PM may approve/return any week, and a week is
   still approved as a whole. The dashboard and `/approvals` only *filter* by managed projects
   (with an "All" toggle). Per-project approval is out of scope.
3. **Billing handoff is per project × calendar month** (not the customer's billing period —
   periods are stored as `period_start`/`period_end` so that can come later).
4. **The stub records the handoff and locks the period**: a project's month can be sent once;
   afterwards its time entries in that month can't be changed and weeks containing them can't be
   returned. An admin can reopen a sent period (the escape hatch for mistakes).
5. **A month can be sent on any day**, not only after it ends — work may be finished early.
   Sending stays a manual action for now; automating it comes later.

### Design principles

- The handoff record lives in the **timesheets** module (`ProjectBillingPeriod`): locking is a
  timesheet rule checked inside `SaveTimesheetWeek`/`ReturnTimesheetWeek`, and keeping it there
  avoids a `timesheets.contracts` ↔ `billing.contracts` cycle. The future invoices module will
  consume `timesheets.contracts` to pick up sent periods.
- Manager assignment lives in the **projects** module; timesheets reaches it only through a new
  `projects.contracts` query — no joins into `projects`/`project_members`.
- Aggregation stays in `modules/timesheets/summary.py` (new `TeamOverviewService` or functions next
  to the existing ones), reading entries and weeks through the module's own repositories and
  reusing `_is_working_day`, `_month_bounds`, `_start_of_iso_week`, `_QuantityAccumulator`.
- `today` stays a query/command field (router passes `date.today()`), as in the existing summaries.

### Readiness rule (project P, month M)

- **Scope**: every `(user, ISO week)` where the week intersects M and the user has at least one
  entry on P dated inside M.
- **Ready** when: P isn't already sent for M, there is at least one week in scope (nothing to bill
  otherwise), and every week in scope is `approved`. Not ready lists blockers: weeks
  `draft`/`returned`/`submitted` with counts per user.
- **No date restriction**: a month can be sent on any day — work may finish before month end. The
  sent period still covers the whole calendar month, so sending mid-month also locks the month's
  remaining days for P (no later bookings on P in M unless an admin reopens).
- **Warnings (non-blocking)**: active members of P with *no* entries on P in M, and members whose
  total hour-unit entries (all projects) in M are below expected hours to date — the manager decides
  whether that's vacation or missing reporting.
- A week straddling two months (e.g. Sep 28 – Oct 4) belongs to both months' scope; once September
  is sent it can't be returned, so October's part is locked too until the week is reopened by an
  admin reopening September. Accepted trade-off of week-level approval.

## Backend

### Projects module (`modules/projects/`)

- Migration: `projects.manager_id UUID NULL REFERENCES users(id) ON DELETE RESTRICT`, indexed.
- `ProjectDTO.manager: ProjectManagerDTO | None` (`id`, `name`, `email`, `is_active`) — filled via
  `GetUsersByIds` like members are.
- `CreateProject.manager_id: UUID | None`; `UpdateProject.manager_id` (`None` = unchanged) and
  `"manager_id"` added to `ClearableProjectField`. Validation in the service: user exists, is
  active and has role `admin`/`project_manager` → new `ProjectManagerNotEligibleError` (400).
- `ListProjects.manager_id: UUID | None` filter.
- New batch query `ListManagedProjectsWithMembers(manager_id: UUID | None)` →
  `tuple[ManagedProjectDTO(project: ProjectDTO, members: tuple[ProjectMemberDTO, ...]), ...]`,
  active projects only, ordered by customer name, project name; `manager_id=None` = all active
  projects (admin "All" view). One round trip for the team/billing queries.
- `RemoveUserFromAllProjects` also clears `manager_id` where it points at the user (return value
  stays the membership count; add `managed_projects_cleared` to its DTO or a sibling command
  `ClearProjectManager(user_id)` — pick whichever keeps the admin module's call site simplest).
- HTTP: `manager_id` in create/update request bodies (JSON `null` clears), `manager` in
  `ProjectResponse`, `?manager_id=` on `GET /projects`.

### Users module

- `GET /users/directory` gains an optional repeated `role` query param (`ListUsers.roles`) so the
  manager picker lists only admins/PMs.

### Admin module

- `GetUserRemovalImpact` adds a `managed_projects` effect (`RemovalEffectKind`) counted via
  `ListProjects(manager_id=…)`; `RemoveUser(permanent=True)` clears assignments before deleting.

### Timesheets module (`modules/timesheets/`)

#### Model + migration

- `ProjectBillingPeriod` (`project_billing_periods`): `id`, `project_id` (FK `projects.id`
  `ON DELETE RESTRICT`), `period_start`, `period_end` (dates, check `period_start <= period_end`),
  `sent_at`, `sent_by_id` (FK `users.id` `ON DELETE RESTRICT`), `TimestampMixin`; unique
  `(project_id, period_start)`. No row = not sent. Admin reopen deletes the row.
- `ProjectBillingPeriodRepository`: `get`, `list_for_projects_in_range`,
  `list_overlapping(project_ids, date_from, date_to)` (for lock checks).
- `TimesheetWeekRepository`: `list_for_users_in_range(user_ids, date_from, date_to)`.
- `TimeEntryRepository`: `list_for_projects_in_range(project_ids, date_from, date_to)` (hour and
  non-hour units; aggregation in Python like the other summaries).

#### Contracts

- `TeamMemberWeekDTO(week_start, iso_year, iso_week, status, project_hours, total_hours,
  expected_hours)` — `project_hours` = hours on this project inside M (only the in-month days of a
  straddling week), `total_hours` = all projects, whole week.
- `TeamMemberDTO(user: UserDTO, is_member: bool, project_hours, total_hours_in_month,
  expected_hours_to_date, weeks: tuple[TeamMemberWeekDTO, ...], warning: TeamMemberWarning | None)`
  — `is_member=False` for someone who booked on P in M but was removed since.
- `BillingPeriodStatus` enum: `not_ready` / `ready` / `sent`.
- `ProjectBillingPeriodDTO(project_id, period_start, period_end, status, sent_at, sent_by:
  UserDTO | None, blocking_weeks: int, weeks_in_scope: int, hours: HoursTotalsDTO, per_diem_days,
  expenses: tuple[CurrencyAmountDTO, ...])`.
- `TeamProjectDTO(project: ProjectOptionDTO-like summary (id, name, customer name),
  members: tuple[TeamMemberDTO, ...], billing: ProjectBillingPeriodDTO)`.
- `TeamMonthOverviewDTO(year, month, weeks: tuple[week_start…], projects: tuple[TeamProjectDTO, ...],
  counts: TeamStatusCountsDTO(awaiting_approval, returned, not_submitted, approved))`.
- Queries:
  - `GetTeamMonthOverview(manager_id: UUID | None, year, month, today)` — backs the dashboard cards
    and `/team`. `manager_id=None` means all active projects.
  - `ListProjectBillingPeriods(project_id)` — history for the project details page (optional,
    last task).
- Commands:
  - `SendProjectMonthToBilling(project_id, year, month, sent_by_id)` → `ProjectBillingPeriodDTO`.
    Allowed on any day. Raises `ProjectNotFoundError`-equivalent `TimesheetProjectNotFoundError`,
    `NotProjectManagerError` (sender is a PM who isn't the project's manager; admins may send any),
    `BillingPeriodNotReadyError` (carries the blocking counts), `BillingPeriodAlreadySentError`.
    The stub's "sending" = inserting the row; leave a clearly marked hook where the invoices module
    will be notified.
  - `ReopenProjectBillingPeriod(project_id, period_start)` — admin only; raises
    `BillingPeriodNotFoundError`.
- Extend `ListSubmittedTimesheetWeeks` with `manager_id: UUID | None` — only weeks with entries on
  projects that manager manages (resolved through `ListManagedProjectsWithMembers`).

#### Lock rules

- `SaveTimesheetWeek`: after the existing checks, reject any cell change whose `(project_id, date)`
  falls into a sent period → `BillingPeriodLockedError` (409). Row-comment changes on a row with
  locked dates are rejected the same way.
- `ReturnTimesheetWeek`: reject if the week has entries on a project whose sent period overlaps the
  week → `BillingPeriodLockedError` (409).
- `GetTimesheetWeek`: `TimesheetRowDTO.locked_dates: tuple[date, ...]` and `can_review` false when a
  return would be blocked, so the grid renders locked cells read-only and hides "Return…".

#### HTTP (`router.py`, `schemas.py`)

- `GET /timesheets/team/{year}/{month}?scope=mine|all` (`ManagerDep`; `scope=all` → admin only,
  403 for a PM) → `TeamMonthOverviewResponse`.
- `POST /timesheets/billing-periods` body `{project_id, year, month}` (`ManagerDep`) →
  201 `ProjectBillingPeriodResponse`; 403 not the project's manager, 409 not ready /
  already sent (distinct `detail`).
- `DELETE /timesheets/billing-periods/{project_id}/{period_start}` (`AdminDep`) → 204.
- `GET /timesheets/submissions?scope=mine|all` (default `all` to keep today's behavior).
- `BillingPeriodLockedError` → 409 on the week save/return endpoints.

### Seed (`seed.py`)

- Demo projects get `manager_id` = the demo project manager; the demo worker is a member.
- Keep the last month partly unapproved so the billing card shows one "Not ready" project and one
  "Ready"; don't create sent periods (the manual test does that). Idempotency unchanged.

### Tests

- `test_projects_*`: manager assignment/clear/validation (worker rejected, inactive rejected),
  `ListProjects(manager_id)`, `ListManagedProjectsWithMembers`, clearing on user removal.
- `test_admin_*`: `managed_projects` effect, permanent delete with an assignment succeeds.
- `test_timesheets_team_handlers.py`: overview scope (mine vs all), straddling week split of
  `project_hours`, status counts, warnings (no entries / under expected), readiness (blocking week,
  no weeks in scope, ready in the middle of the current month, sent), removed member still listed.
- `test_timesheets_billing_handlers.py`: send happy path; send mid-month then a later booking on the
  same project in that month is rejected; not ready; already sent; PM not
  manager 403-equivalent; admin sends any; save into a locked period rejected (cell and comment);
  save outside the locked month in the same straddling week allowed; return blocked; reopen unlocks.
- `test_timesheets_api.py`: endpoints' status codes and role guards (worker 403, PM `scope=all`
  403, admin reopen only).
- `test_module_boundaries.py` passes unchanged (only `contracts.py` imports).

## Frontend (`frontend/src/`)

### Projects

- `npm run gen:api`; `projects/api.ts` types `manager`, `managerId` in create/update;
  `users/api.ts` directory `roles` param.
- `ProjectFormModal.tsx`: "Manager" searchable `Select` via `useUserDirectory({ roles:
  ["admin","project_manager"] })`, clearable. `ProjectDetailsPage.tsx` shows the manager;
  `ProjectsPage.tsx` gets a Manager column and a "Managed by me" filter (`?manager=me`).

### Timesheets API layer

- `timesheets/api.ts`: `getTeamMonthOverview({ year, month, scope })`,
  `sendProjectMonthToBilling`, `reopenProjectBillingPeriod`, `listSubmittedTimesheetWeeks({ scope })`;
  `BillingPeriodError` classes mapping 400/403/409 `detail`.
- `timesheets/hooks.ts`: `timesheetKeys.team(year, month, scope)` under a new `timesheetKeys.team()`
  prefix; `useTeamMonthOverview`, `useSendProjectMonthToBilling`, `useReopenProjectBillingPeriod`.
  Save/submit/approve/return additionally invalidate `timesheetKeys.team()`; send/reopen invalidate
  `team()`, `submissions()` and the week queries (locks changed).
- `test/fixtures.ts`: `testTeamMonthOverview` (one not-ready, one ready, one sent project).

### Manager widgets (`timesheets/team/` or alongside existing cards)

- `TeamScopeToggle.tsx`: "My projects / All" `SegmentedControl`, shown only to admins (a PM is
  always `mine`); state in `?scope=` on `/team`, local state on the dashboard.
- `TeamTimesheetsCard.tsx`: counts awaiting approval / returned / not submitted for the current and
  previous ISO week; footer "Approvals →" (`/approvals?scope=mine`).
- `ProjectBillingCard.tsx` (`{ year, month, scope }`): table Project · Hours · Weeks approved x/y ·
  Status; "Send to billing" button for `ready` rows behind a confirm modal that repeats hours,
  per diems and expenses per currency and states that the period will be locked; success toast
  "Sent to billing — invoicing is not implemented yet". Default month: the previous month during
  the first 10 days of a month, else the current month, with a ‹ › switch.
- `TeamStaffCard.tsx`: distinct people across managed projects — name, projects, month hours vs
  expected to date, warning icon with tooltip; each row links to that user's current timesheet
  week; footer "Team overview →" (`/team`).

### Team page

- `pages/TeamPage.tsx` at `/team` (`RequireRole roles={["admin","project_manager"]}`), nav item
  "Team" after Approvals: month navigation (`?month=YYYY-MM`, reuse `HoursPage`'s pattern), scope
  toggle, per project a section with header (customer · project, billing status badge, Send /
  admin "Reopen" button) and a members × weeks table (`TeamWeekMatrix.tsx`, presentational):
  status badge + project hours per cell, link `/timesheet?week=&user=`, straddling weeks marked,
  warnings per member.
- `pages/ApprovalsPage.tsx`: "My projects / All" toggle wired to `scope`.
- `TimesheetGrid.tsx`: locked cells read-only (from `locked_dates`), a "Sent to billing" notice
  when any row has locked dates.

### Dashboard

- `pages/DashboardPage.tsx`: when `canManage(user.role)`, a "My team" `Title` + `SimpleGrid` with
  `TeamTimesheetsCard`, `ProjectBillingCard`, `TeamStaffCard` below the worker cards (a PM still
  books their own time, so the worker cards stay).

### Tests

- Component tests for the three cards, `TeamWeekMatrix`, `TeamPage` (month navigation, send flow
  with confirm, admin reopen visible only to admin), `ApprovalsPage` scope toggle,
  `ProjectFormModal` manager picker (edit flow), `TimesheetGrid` locked cells.
- `DashboardPage.test.tsx`: worker sees no team section; PM sees it; admin sees the scope toggle.

## Tasks (one commit each)

1. Commit this plan as `.claude/plans/manager-dashboard.md`.
2. Backend/projects: `Project.manager_id` + migration, DTO/commands/validation, `ListProjects`
   filter, `ListManagedProjectsWithMembers`, HTTP fields; users directory `role` filter; admin
   removal impact/cleanup; tests.
3. Frontend/projects: `gen:api`, manager in API layer, `ProjectFormModal` picker, details page,
   projects list column + "Managed by me"; tests.
4. Backend/timesheets: `GetTeamMonthOverview` (repositories, contracts, summary aggregation,
   readiness rule without persistence yet — status is `not_ready`/`ready` only) + handler tests.
5. Backend/timesheets: `ProjectBillingPeriod` + migration, `SendProjectMonthToBilling` /
   `ReopenProjectBillingPeriod`, lock rules in save/return/week read, `sent` status in the overview;
   handler tests.
6. Backend/timesheets HTTP: team, billing-periods, `submissions?scope=`, error mapping; API tests.
   Seed: manager assignments + a ready/not-ready month.
7. Frontend: timesheets API layer + hooks + fixtures for team/billing; grid locked cells.
8. Frontend: `TeamTimesheetsCard`, `ProjectBillingCard` (send flow), `TeamStaffCard`; manager
   section on `DashboardPage`; tests.
9. Frontend: `TeamPage` + `TeamWeekMatrix`, nav item, `ApprovalsPage` scope toggle; tests.
10. Docs: `CLAUDE.md` (project manager assignment, team overview, billing periods and locks, new
    endpoints/pages/widgets).

Tasks 2→3 and 4→5→6→7→8→9 are sequential; 3 can run in parallel with 4–6.

## Out of scope / follow-ups

- Per-project week approval and restricting review rights to a project's manager.
- Billing periods following the customer's `billing_interval_*` instead of calendar months.
- The real invoices module consuming sent periods (the stub's hook).
- Automating the handoff (e.g. sending a project's month once everything in scope is approved).
- Notifications/reminders to workers who haven't submitted.

## Verification

- Backend: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest`
  on a clean migrated DB (`docker compose down -v && docker compose up -d db && alembic upgrade
  head` — the test DB doubles as the dev DB).
- Frontend (`frontend/`, Node 24): `npm run gen:api`, `npm run lint`, `npm run typecheck`,
  `npm test`, `npm run build`.
- Manual: `uv run time-reporting seed-demo`, backend + `npm run dev`, sign in as
  `manager@example.com` / `demo-password`: team section on the dashboard, counts match `/approvals`,
  approve the remaining weeks of last month → project becomes Ready → send → status Sent, worker's
  grid shows those days locked and "Return…" is gone; as `admin@…` switch scope to All and reopen.
