# Plan: weekly timesheets — employees record their time and expenses (backend + frontend)

## Context

Users, customers, projects, project members and per-project billing items exist, but nobody can
record work yet. Billing needs time entries: how many hours / days / money an employee booked on
which project, against which billing item (normal hours, overtime, travel, per diem, expenses...),
on which date.

We add a **weekly timesheet**: an employee picks one of the projects they are a member of and one
of its billing items as a row, and fills in a quantity per day. Weekends and non-working days
(public holidays, bridge days, company days off) are highlighted in the grid. A company-wide
non-working-day calendar is maintained by admins.

### Decisions confirmed with the user

- **One cell per day:** at most one entry per (user, billing item, date) holding a quantity in the
  item's unit (`hour` → hours, `day` → days, `amount` → money in the customer's currency) plus an
  optional note. The project is implied by the billing item.
- **Weekly grid:** rows = project × billing item, columns = Mon..Sun (ISO weeks, Monday first).
- **One calendar for the company:** public holidays imported per year from the Python `holidays`
  library for a configured country (e.g. `DE`), plus manually added/edited/removed days such as
  bridge days and company days off. Weekends (Sat/Sun) are computed, not stored.
- **Non-working days are only highlighted**, entering time on them is allowed.
- **No submit/approval workflow yet** — entries stay freely editable by their owner (locking comes
  with invoices).
- **Access:** everyone edits only their own timesheet; admins and project managers can *view*
  (read-only) any user's week.

### Design principles

- **Two new modules**, reached by others only through their `contracts.py`:
  - `work_calendar` (not `calendar`/`holidays`, to avoid confusion with the stdlib module and the
    PyPI package) owns `NonWorkingDay`; depends on nothing.
  - `timesheets` owns `TimeEntry`; depends on `projects.contracts`, `users.contracts`,
    `work_calendar.contracts`. `projects` never imports `timesheets` (no cycle); `admin` does, for
    removal blockers.
- **Server decides editability** so the rules aren't duplicated in the UI: every week row carries
  `is_open` (user still a member, project active, billing item active) and the week carries
  `can_edit` (viewer is the owner). A cell is editable when both are true.
- **Every write (create, change, delete) of an entry requires an open row**; rows on archived
  projects/items or after a membership was removed stay visible but read-only.
- **Batch save per week** in one bus command → one transaction; the UI has an explicit Save.
- **Validation in three layers** as for billing items: Pydantic shape, service rule errors, DB
  constraints (unique cell, `quantity > 0`).
- **`ON DELETE RESTRICT`** from `time_entries` to `users`, `projects`, `project_billing_items`:
  permanent deletes become blocked once time is booked, surfaced by the admin module's impact.

## Data model

`non_working_days` (`work_calendar/models.py: NonWorkingDay`, `TimestampMixin`):

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `day` | date, unique | one entry per date |
| `name` | varchar(255) | "German Unity Day", "Bridge day" |
| `kind` | enum `non_working_day_kind`: `public_holiday`, `bridge_day`, `company_day_off` | |

`time_entries` (`timesheets/models.py: TimeEntry`, `TimestampMixin`):

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `user_id` | uuid FK `users.id` `RESTRICT` | |
| `project_id` | uuid FK `projects.id` `RESTRICT` | denormalized from the item for filtering/counting; service guarantees it matches |
| `billing_item_id` | uuid FK `project_billing_items.id` `RESTRICT` | |
| `entry_date` | date | |
| `quantity` | numeric(12, 2) | check `quantity > 0` (clearing a cell deletes the row) |
| `note` | text, nullable | |

Unique `(user_id, billing_item_id, entry_date)` (also serves lookups by user); index
`(user_id, entry_date)` for week queries; index on `project_id`.

Service quantity rules by unit: `hour` 0 < q ≤ 24 and the sum of all `hour` entries of the user on
that date ≤ 24; `day` 0 < q ≤ 1 (half per diems allowed); `amount` q > 0.

## Contracts

**`work_calendar.contracts`**: `NonWorkingDayKind`, `WEEKEND_DAYS = frozenset({6, 7})` (ISO),
`NonWorkingDayDTO`, `CalendarDayDTO(date, is_weekend, non_working_day: NonWorkingDayDTO | None)`;
queries `ListNonWorkingDays(date_from, date_to)`, `GetCalendarDays(date_from, date_to)`; commands
`AddNonWorkingDay`, `UpdateNonWorkingDay` (`None` = unchanged), `DeleteNonWorkingDay`,
`ImportPublicHolidays(year) -> int` (adds missing dates only, so manual edits/removals are never
overwritten — re-running is idempotent); errors `NonWorkingDayNotFoundError`,
`NonWorkingDayAlreadyExistsError` (date taken), `HolidayCountryNotSupportedError`.
Settings: `holiday_country: str = "DE"`, `holiday_subdivision: str | None = None` (+ `.env.example`).
Holiday names imported in English (`language="en_US"` where the library supports it).

**`projects.contracts`** (new batch queries, following `GetCustomersByIds`/`GetUsersByIds`):
`GetProjectsByIds(project_ids)`, `GetProjectBillingItemsByIds(item_ids)`,
`ListMemberProjectsWithBillingItems(user_id)` → active projects the user is a member of, each with
its active billing items (one round trip for the "add row" picker and for write validation).

**`timesheets.contracts`**: DTOs `TimesheetWeekDTO(user, week_start, can_edit, days:
tuple[CalendarDayDTO, ...], rows)`, `TimesheetRowDTO(project, billing_item, is_open, entries)`,
`TimeEntryDTO(date, quantity, note)`, `TimesheetOptionDTO(project, billing_items)`;
queries `GetTimesheetWeek(user_id, week_start, viewer_id)`, `ListTimesheetOptions(user_id)`,
`CountTimeEntries(user_id=None, project_id=None, billing_item_id=None) -> int`;
command `SaveTimesheetWeek(user_id, week_start, changes: tuple[TimeEntryChange, ...])` where
`TimeEntryChange(billing_item_id, date, quantity: Decimal | None, note: str | None)`, `quantity=None`
deletes the cell; errors `WeekStartNotMondayError`, `EntryDateOutsideWeekError`,
`DuplicateChangeError`, `TimesheetRowClosedError` (not a member / project or item archived),
`QuantityOutOfRangeError`, `DailyHoursExceededError`, `TimesheetBillingItemNotFoundError`.

## HTTP API

| Method | Path | Guard | Message |
|---|---|---|---|
| GET | `/calendar/days?from=&to=` (≤ 366 days) | `CurrentUserDep` | `GetCalendarDays` |
| GET | `/calendar/non-working-days?year=` | `CurrentUserDep` | `ListNonWorkingDays` |
| POST | `/calendar/non-working-days` | `AdminDep` | `AddNonWorkingDay` (201 / 409 date taken) |
| PATCH | `/calendar/non-working-days/{id}` | `AdminDep` | `UpdateNonWorkingDay` (404 / 409) |
| DELETE | `/calendar/non-working-days/{id}` | `AdminDep` | `DeleteNonWorkingDay` (204 / 404) |
| POST | `/calendar/non-working-days/import` `{year}` | `AdminDep` | `ImportPublicHolidays` → `{added}` (400 unsupported country) |
| GET | `/timesheets/weeks/{week_start}?user_id=` | `CurrentUserDep`; another user's week needs admin/PM (403 otherwise) | `GetTimesheetWeek` (400 not Monday, 404 user) |
| PUT | `/timesheets/weeks/{week_start}/entries` `{changes: [...]}` | `CurrentUserDep`, own week only | `SaveTimesheetWeek` → the updated week (400 rule errors with `detail`, 404 item) |
| GET | `/timesheets/options` | `CurrentUserDep` | `ListTimesheetOptions` for the caller |

Decimals serialize as strings (as billing items). `extra="forbid"` on bodies.

---

## Tasks

Branch `feature/timesheets` from `feature/billing-items`. First commit: copy this plan to
`.claude/plans/timesheets.md` (like earlier plans). Each task is one reviewable commit leaving
`ruff`, `mypy`, `pytest` (frontend: `lint`, `typecheck`, `test`) green.

Order: **B1 → B2 → B3 → B4 → B5** → **F1 → F2 → F3** → **D1**.

### B1. `work_calendar` module: model, bus, import, HTTP

- `uv add holidays` in `backend/` (commit `uv.lock`); settings `holiday_country`/`holiday_subdivision`.
- `modules/work_calendar/{contracts,models,repository,service,handlers,module,schemas,router}.py`
  following `customers/`; register in `modules/registry.py`, import models in `models/__init__.py`,
  include router in `api/router.py`. Unique-date violation → `NonWorkingDayAlreadyExistsError`
  (same pattern as `ProjectBillingItemRepository.save`).
- Alembic revision (autogenerate, check enum creation/drop in downgrade).
- CLI: `time-reporting import-holidays --year 2026` in `cli.py`, run through a `Bus` like
  `create-admin`.
- Tests `test_work_calendar_handlers.py` / `test_work_calendar_api.py`: add/update/delete, date
  conflict, import adds holidays and is idempotent and skips manually taken dates, `GetCalendarDays`
  flags weekends and non-working days, worker reads but gets 403 on writes, range limit.

### B2. Projects batch queries

- `GetProjectsByIds`, `GetProjectBillingItemsByIds`, `ListMemberProjectsWithBillingItems` in
  `projects/contracts.py`, repository helpers, handlers, registration (reuse `_customer_dto`,
  `_billing_item_dto`, customer batch via `GetCustomersByIds`).
- Tests in `test_projects_handlers.py`: unknown ids omitted; archived projects/items and
  non-member projects excluded from the member query.

### B3. `timesheets` module: model, migration, bus

- `TimeEntry` model + migration (FKs `RESTRICT`, unique, check, indexes).
- `TimesheetService`:
  - `get_week`: entries of the user in `[week_start, +6]`; projects/items fetched with the B2 batch
    queries (entries may point at archived ones); rows = distinct billing items with entries, ordered
    by project name then item `position`; `is_open` from `ListMemberProjectsWithBillingItems`;
    `days` from `GetCalendarDays`; `can_edit = viewer_id == user_id`.
  - `save_week`: validate Monday, dates in week, no duplicate cells in the batch; resolve items
    via `ListMemberProjectsWithBillingItems` (closed row → `TimesheetRowClosedError`, item unknown
    → not found); apply upserts/deletes, then check per-unit ranges and the ≤ 24 h daily total over
    the resulting state (so moving hours between rows in one batch works); flush only.
- Tests `test_timesheets_handlers.py`: create/update/delete cells; each rule error; archived
  project/item and removed membership make rows read-only but still listed; a batch failing
  midway changes nothing (outer `execute` rollback); non-working days and weekends in `days`;
  `CountTimeEntries` filters.

### B4. Timesheets HTTP API

- `timesheets/schemas.py`, `timesheets/router.py` per the table; own-week check for PUT, role
  check (`UserRole.ADMIN`/`PROJECT_MANAGER` on `CurrentUserDep`) for viewing another user.
- Tests `test_timesheets_api.py`: worker can't read another user's week (403), PM can read but not
  write it, 400 for non-Monday, decimals as strings, rule errors carry `detail`.

### B5. Removal blockers and demo data

- `admin/contracts.py`: `RemovalBlockerKind.TIME_ENTRIES`; user/project impact count via
  `CountTimeEntries`; `remove_project` gains the blocker check (replacing the "no blockers yet"
  comment). Make sure `DeleteProject` / `DeleteUser` map the FK violation to
  `ProjectInUseError` / `UserInUseError` and `DeleteProjectBillingItem` to
  `BillingItemInUseError` (already declared; verify the repositories actually catch the new FK).
- `seed.py`: import public holidays for the current and next year, add one demo bridge day;
  demo time entries for the demo worker/PM for the previous and current week (only when the user
  has no entries yet → idempotent). Update `test_seed.py`.
- Tests: admin impact lists `time_entries` blockers; permanent delete of a user/project/billing
  item with entries → 409.

### F1. Frontend API layer

- `npm run gen:api`.
- `calendar/api.ts` + `hooks.ts` (`calendarKeys`, `useCalendarDays`, `useNonWorkingDays`,
  add/update/delete/import mutations, `NonWorkingDayConflictError`).
- `timesheets/api.ts` + `hooks.ts` (`timesheetKeys.week(userId, weekStart)`, `useTimesheetWeek`,
  `useTimesheetOptions`, `useSaveTimesheetWeek` setting the returned week into the cache;
  `TimesheetRuleError` with backend `detail`).
- `timesheets/week.ts`: `startOfIsoWeek`, `weekDays`, `addWeeks`, formatting (dayjs `isoWeek`
  plugin), with unit tests.
- `admin/RemoveEntityModal.tsx`: label for the `time_entries` blocker.

### F2. Timesheet page

- Route `/timesheet?week=YYYY-MM-DD&user=<id>` (`router.tsx`), nav item "Timesheet" in
  `AppLayout.tsx` (first entry).
- `pages/TimesheetPage.tsx`: header with previous / "This week" / next buttons and a week picker
  (`@mantine/dates`); for admins/PMs a user `Select` backed by `useUserDirectory` ("My timesheet"
  by default; another user's week is read-only with a notice).
- `timesheets/TimesheetGrid.tsx` (Mantine `Table` in `Table.ScrollContainer`):
  - first column: project (customer) and billing item name, badges for archived/closed rows;
  - day columns headed "Mon 14.09"; weekend columns tinted `gray`, non-working days tinted
    `orange` (public holiday) / `yellow` (bridge day, company day off) using Mantine `*-light`
    colors (dark-theme safe), with a `Tooltip` naming the day; today's header emphasized;
  - cells: `NumberInput` (hours: step 0.25, max 24; per diem: step 0.5, max 1; amount: 2 decimals,
    currency suffix), a note icon opening a `Popover` with a `Textarea`; closed rows render text;
  - row total per row (in its unit); footer: daily hours total (hour items only, red above 24),
    weekly hours total;
  - legend under the table.
- Local draft state keyed by `billingItemId|date`; "Save" (sends only changed cells) and
  "Discard"; switching week/user while dirty asks for confirmation; server rule errors shown as an
  `Alert`.
- `timesheets/AddRowModal.tsx`: project `Select` then billing item `Select` from
  `useTimesheetOptions`, excluding rows already shown; added rows live in the draft until a value is
  saved. "Copy rows from previous week" adds last week's open rows (no values).
- Tests `timesheets/TimesheetPage.test.tsx`: weekend/holiday columns marked (e.g. `data-kind`
  attribute + tooltip text), entering values and saving sends the right changes, clearing a cell
  sends `quantity: null`, closed row read-only, PM viewing another user sees no inputs, rule error
  shown, add row + copy from previous week, dirty-navigation confirmation.

### F3. Admin calendar page

- `/admin/calendar` under the existing `RequireRole`; "Calendar" in the admin nav group.
- `pages/admin/AdminCalendarPage.tsx`: year selector; table of non-working days (date, weekday,
  name, kind badge) with row menu Edit/Delete; "Add day" modal (`DatePickerInput`, name, kind);
  "Import public holidays for {year}" button with a notification showing how many were added.
- Tests: list rendering, add with date conflict error, import notification.

### D1. Docs and verification

- `CLAUDE.md`: `work_calendar` and `timesheets` modules, new projects batch queries, the
  `time_entries` removal blocker, frontend `calendar/` / `timesheets/` / new pages; "remaining
  domain models" now lists invoices only.

## Verification

- Backend: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest`
  (Postgres up and migrated: `docker compose up -d db`, `uv run alembic -c backend/alembic.ini
  upgrade head`); migration downgrade/upgrade round-trip by hand.
- Frontend: `npm run lint && npm run typecheck && npm test && npm run build`.
- End to end: `docker compose up --build`, `time-reporting seed-demo`, then as admin import
  holidays and add a bridge day; as the demo worker open Timesheet, check Sat/Sun and holiday
  columns are tinted with tooltips, add a row, enter hours incl. a holiday, a per diem and an
  expense, save, reload; archive the project as a manager → row turns read-only; as a PM view the
  worker's week read-only; as admin try to permanently delete that project/user → blocked by time
  entries.

## Out of scope

- Submit/approval workflow and locking weeks; locking invoiced entries (with invoices).
- Per-user or per-country calendars, partial (half) non-working days, custom work weeks.
- Start/end times, multiple entries per cell, receipt attachments for expenses.
- Reports/exports across users or projects beyond viewing one user's week.
- Managers editing someone else's timesheet.
