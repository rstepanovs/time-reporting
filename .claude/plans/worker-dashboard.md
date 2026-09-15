# Plan: worker dashboard — month calendar, monthly statistics and this week's timesheet

## Context

The signed-in landing page (`/`, `pages/HomePage.tsx`) still shows the API/database health probes
from the project skeleton. Workers now book time on `/timesheet`, but nothing shows them *how much*
they have reported against what was expected, or how past months looked. We turn `/` into a
personal dashboard with three blocks:

1. **Month calendar, one row per ISO week** — every day shows the hours booked, highlighted as
   weekend / public holiday / bridge day / company day off, and colored by completeness; a totals
   column shows `reported / expected` hours per week. Month navigation with ‹ › and "Today".
2. **This week's timesheet** — the existing editable `TimesheetGrid` for the current week (Save,
   Add row, Copy rows from previous week); the calendar and statistics refresh after a save.
3. **Monthly statistics table** — the last 6 months (current month first, marked "in progress"):
   working days, expected hours, normal / overtime / travel / other hours, total hours, difference
   to expected, per-diem days and expenses per currency; each month expands into a per-project
   breakdown.

### Decisions confirmed with the user

- Calendar: month grid Mon–Sun, rows = ISO weeks, week totals column (`reported/expected`).
- Expected hours: one global setting `DAILY_WORKING_HOURS` (default 8). A working day is a day that
  is not a weekend and has no `NonWorkingDay` entry (any kind). Expected hours = working days × 8.
- Monthly table: breakdown by billing item kind plus an expandable per-project breakdown.
- This week: the full editable grid, reusing `TimesheetGrid`.

### Design principles

- **All aggregation lives in the timesheets module** (it owns `TimeEntry`), exposed as two new
  queries in `timesheets/contracts.py`. It reaches billing item presets, project/customer names and
  currencies only through the existing batch queries `GetProjectBillingItemsByIds` /
  `GetProjectsByIds`, and the calendar through `GetCalendarDays` — no new cross-module queries, no
  joins into other modules' tables (`test_module_boundaries.py` stays green).
- **Categorization by the denormalized `unit` + the billing item's `preset`**:
  `hour` → `normal_hours` / `overtime_hours` / `travel_hours` by preset, custom hour items →
  `other_hours`; `day` → `days` (per diems and custom day items); `amount` → summed **per
  currency** (the project's customer currency — never added across currencies). Entries on
  archived projects/items still count: statistics describe what was booked.
- **`today` is a query parameter of the messages** (filled by the router with `date.today()`), so
  "expected to date" and "month in progress" are deterministic in tests.
- **Same access rule as a week**: own data by default; `user_id` of someone else only for admin /
  project manager (403 otherwise). The dashboard itself only shows the caller's own data.
- Range caps keep `GetCalendarDays` (≤ 366 days) valid: a month calendar spans ≤ 6 weeks, the
  monthly summary ≤ 12 months.

## Backend

### Setting

`core/config.py`: `daily_working_hours: Decimal = Field(default=Decimal("8"), gt=0, le=24)` with a
comment; add `DAILY_WORKING_HOURS=8` (commented) to `.env.example`. Read in the service via
`get_settings()`, the same way `work_calendar/service.py` reads `holiday_country`.

### Contracts (`modules/timesheets/contracts.py`)

DTOs:

- `CurrencyAmountDTO(currency: str, amount: Decimal)`
- `QuantityTotalsDTO(normal_hours, overtime_hours, travel_hours, other_hours, total_hours: Decimal,
  days: Decimal, amounts: tuple[CurrencyAmountDTO, ...])` — `total_hours` = sum of the four hour
  fields; amounts sorted by currency.
- `CalendarDaySummaryDTO(calendar_day: CalendarDayDTO, in_month: bool, is_working_day: bool,
  expected_hours: Decimal, hours: Decimal, has_other_entries: bool)` — `hours` = all `hour`-unit
  entries; `has_other_entries` = any `day`/`amount` entry that day (a small marker in the UI).
- `CalendarWeekSummaryDTO(week_start: date, iso_week: int, days: tuple[CalendarDaySummaryDTO, ...],
  expected_hours: Decimal, hours: Decimal)` — week totals include days outside the month.
- `TimesheetMonthCalendarDTO(user: UserDTO, year: int, month: int, weeks: tuple[...],
  expected_hours: Decimal, expected_hours_to_date: Decimal, hours: Decimal)` — month totals count
  only `in_month` days; "to date" = working days `<= today`.
- `ProjectMonthTotalsDTO(project: ProjectDTO, totals: QuantityTotalsDTO)`
- `MonthSummaryDTO(year: int, month: int, is_current: bool, working_days: int,
  expected_hours: Decimal, expected_hours_to_date: Decimal, totals: QuantityTotalsDTO,
  projects: tuple[ProjectMonthTotalsDTO, ...])` — projects sorted by customer name, project name.

Queries:

- `GetTimesheetMonthCalendar(user_id, year, month, today)` → `TimesheetMonthCalendarDTO`.
  Range = Monday of the week containing the 1st … Sunday of the week containing the last day.
  Raises `UserNotFoundError`.
- `GetTimesheetMonthlySummary(user_id, until_year, until_month, months, today)` →
  `tuple[MonthSummaryDTO, ...]`, newest first, one element per month even when empty. Raises
  `UserNotFoundError`, `MonthRangeOutOfBoundsError` (new, `TimesheetError`) unless
  `1 <= months <= MAX_SUMMARY_MONTHS` (12).

### Repository (`modules/timesheets/repository.py`)

- Month calendar reuses `list_for_user_in_range` (≤ 42 days of rows).
- New `sum_by_month_and_billing_item(user_id, date_from, date_to)` →
  `(month_start: date, billing_item_id, project_id, unit, total)` rows via
  `func.date_trunc("month", TimeEntry.entry_date)` grouped by month/item/project/unit. Served by the
  existing `(user_id, entry_date)` index.

### Service (`modules/timesheets/summary.py`, new `TimesheetSummaryService(bus)`)

Kept separate from `service.py` (week read/write) — pure read side.

- `month_calendar(...)`: load user (`GetUserById`), entries, calendar days; build weeks of 7
  `CalendarDaySummaryDTO`s; expected hours per day = `daily_working_hours` if working day else 0.
- `monthly_summary(...)`: one `GetCalendarDays` over the whole range for working days per month;
  one repository aggregation; one `GetProjectBillingItemsByIds` + one `GetProjectsByIds` for the
  distinct ids; fold rows into totals per month and per (month, project).
- Private pure helpers: `_month_bounds(year, month)`, `_add_months(year, month, delta)`,
  `_is_working_day(CalendarDayDTO)`, `_TotalsAccumulator` (adds a quantity by unit/preset/currency
  and freezes to `QuantityTotalsDTO`).

`handlers.py`: `GetTimesheetMonthCalendarHandler`, `GetTimesheetMonthlySummaryHandler`;
register both in `module.py`.

### HTTP (`modules/timesheets/router.py`, `schemas.py`)

- `GET /timesheets/calendar?year=&month=&user_id=` → `TimesheetMonthCalendarResponse`
  (`year` 2000–2100, `month` 1–12 via `Query(ge, le)`).
- `GET /timesheets/monthly-summary?months=6&until=YYYY-MM-DD&user_id=` →
  `list[MonthSummaryResponse]` (`months` 1–12, default 6; `until` defaults to today, its month is
  the newest one).
- Both reuse the week endpoint's view check — extract it into a small
  `_resolve_target_user(current_user, user_id)` helper used by all three GETs; map
  `UserNotFoundError` → 404, `MonthRangeOutOfBoundsError` → 400.
- Response models mirror the DTOs with `from_attributes`, reusing the existing
  `CalendarDayResponse`, `TimesheetProjectResponse`, `TimesheetUserResponse`.

## Frontend

### API layer (`frontend/src/timesheets/`)

- `npm run gen:api` after the backend endpoints exist.
- `api.ts`: types `TimesheetMonthCalendar`, `CalendarWeekSummary`, `CalendarDaySummary`,
  `MonthSummary`, `QuantityTotals`; `getTimesheetMonthCalendar({year, month, userId?})`,
  `getTimesheetMonthlySummary({months, until?, userId?})`, both via `timesheetAwareError`.
- `hooks.ts`: `timesheetKeys.summaries()` = `[...all, "summaries"]`,
  `monthCalendar(userId, year, month)` and `monthlySummary(userId, months)` under it;
  `useTimesheetMonthCalendar`, `useTimesheetMonthlySummary` (with `placeholderData:
  keepPreviousData` for smooth month switching). `useSaveTimesheetWeek.onSuccess` additionally
  `invalidateQueries({ queryKey: timesheetKeys.summaries() })`.
- `week.ts`: `addMonths(year, month, delta)`, `formatMonthLabel(year, month)` ("September 2026"),
  `currentYearMonth()`; tests in `week.test.ts`.
- `dayStatus.ts` (pure, with tests): `dayStatus(day, today)` →
  `"off"` (non-working, nothing booked) | `"future"` | `"complete"` (hours ≥ expected, expected > 0)
  | `"partial"` (0 < hours < expected) | `"missing"` (past working day, 0 h) | `"today"` |
  `"extra"` (hours on a non-working day); plus `formatHours(value)` shared by the new components.

### Components

- `timesheets/MonthCalendar.tsx` — props `{ userId }`; own `year/month` state, header with ‹ ›,
  "Today" and the month label; Mantine `Table` (inside `Table.ScrollContainer`) with columns
  `Week | Mon … Sun | Total`. Day cell: date number (dimmed when `!in_month`), hours, background by
  calendar kind (reuse the colors of `TimesheetGrid.DayHeader` — extract its kind→color mapping into
  `timesheets/dayKind.ts` and use it from both), a status accent by `dayStatus`, tooltip with the
  non-working day's name, `data-status` / `data-kind` attributes for tests. Week row: `iso_week`
  cell is a link to `/timesheet?week=<week_start>`; totals `12.5 / 40 h`, red when below expected
  for a fully past week. Footer: month totals `hours / expected (to date: …)`.
- `timesheets/MonthlySummaryTable.tsx` — props `{ userId, months? }`; columns
  `Month | Working days | Expected | Normal | Overtime | Travel | Other | Total | Δ | Per diem | Expenses`;
  current month gets an "In progress" badge and Δ against `expected_hours_to_date`; a chevron
  toggles per-project sub-rows (customer · project, same quantity columns, expected columns empty);
  expenses rendered as `1 234.00 EUR, 50.00 USD`. Empty state when nothing is booked.

### Page, routing, navigation

- `pages/DashboardPage.tsx`: `Title` "Dashboard"; a row of three `Paper` stat cards derived from the
  current calendar/summary queries (This week `h / expected`, This month `h / expected to date`,
  Overtime this month); `MonthCalendar`; section "This week" with week label, a link "Open
  timesheet" and `<TimesheetGrid key={weekStart} userId={user.id} weekStart={startOfIsoWeek(todayIso())}
  onDirtyChange={…} />`; section "Last 6 months" with `MonthlySummaryTable`. Responsive:
  `SimpleGrid cols={{ base: 1, sm: 3 }}` for the stat cards.
- `router.tsx`: index route → `DashboardPage`; delete `pages/HomePage.tsx`.
- System status moves to admins: `pages/admin/AdminSystemStatusPage.tsx` (the existing probe code
  moved verbatim) at `/admin/status`, nav item "System status" in `ADMIN_NAV_ITEMS`.
- `components/AppLayout.tsx`: `NAV_ITEMS` = Dashboard (`/`), Timesheet, Projects.

## Tasks (one commit each)

1. **Commit this plan** as `.claude/plans/worker-dashboard.md`.
2. **Backend: summary queries** — `daily_working_hours` setting + `.env.example`; contracts (DTOs,
   two queries, `MonthRangeOutOfBoundsError`, `MAX_SUMMARY_MONTHS`); repository aggregation;
   `summary.py`; handlers + registration. Tests in `backend/tests/test_timesheets_summary_handlers.py`:
   expected hours skip weekends and each non-working-day kind; calendar spans full ISO weeks with
   `in_month` flags, week totals include outside days but month totals don't; `expected_hours_to_date`
   by `today`; preset categorization incl. a custom hour item → `other_hours`, per diem → `days`,
   expenses grouped per currency across two customers; per-project breakdown; entries on an archived
   project still counted; empty months present; `months` 0 / 13 rejected; unknown user raises.
3. **Backend: HTTP endpoints** — schemas, two routes, shared view-check helper. Tests in
   `test_timesheets_api.py`: worker gets own calendar/summary; worker asking for another user → 403;
   manager allowed; 404 for unknown user; 422 for `month=13` / `months=0`.
4. **Seed: demo history** — extend `_seed_time_entries` in `seed.py` to book the previous 3 months
   (normal hours on working days via `GetCalendarDays`, a few overtime hours and a per diem) so the
   dashboard isn't empty; keep the "skip if the user already has entries" idempotency; adjust
   `test_seed.py`.
5. **Frontend: API layer** — `gen:api`, `api.ts`, `hooks.ts` (keys, queries, save invalidation),
   `week.ts` month helpers, `dayStatus.ts`, `dayKind.ts` (extracted from `TimesheetGrid`), unit tests,
   new fixtures in `test/fixtures.ts` (`testMonthCalendar`, `testMonthlySummary`).
6. **Frontend: dashboard components** — `MonthCalendar.tsx`, `MonthlySummaryTable.tsx`.
7. **Frontend: Dashboard page and navigation** — `DashboardPage.tsx`, router, nav, move system
   status to `/admin/status`. Tests `pages/DashboardPage.test.tsx` (mock `@/auth/api`,
   `@/timesheets/api`): week rows and totals render, day `data-status`/`data-kind`, month navigation
   calls the API with the previous month, week link targets `/timesheet?week=…`, summary row expands
   to project rows, saving in the embedded grid refetches calendar and summary; update
   `AppLayout.test.tsx` for the new nav items.
8. **Docs** — `CLAUDE.md`: the new queries/endpoints in the timesheets module paragraph,
   `DAILY_WORKING_HOURS`, `/` as the dashboard (replace "`/timesheet` is the default landing page"),
   `/admin/status`, the new frontend files; seed description (3 months of demo history).

## Verification

- Backend: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest`
  (Postgres up and migrated; no migration is needed — no schema change).
- Frontend (in `frontend/`): `npm run gen:api` (backend running), `npm run lint`, `npm run typecheck`,
  `npm test`, `npm run build`.
- Manual: `uv run time-reporting seed-demo`, start backend + `npm run dev`, sign in as the demo worker
  (`demo-password`): `/` shows the calendar with holidays/bridge day highlighted and correct week
  totals, month navigation works, the table shows 6 months with overtime/per diem columns and
  expandable projects; change a cell in "This week", Save → calendar day and month row update without
  reload; `/admin/status` works for the admin and is a 404 for the worker;
  `GET /api/v1/timesheets/calendar?year=2026&month=9&user_id=<other>` as the worker → 403.
