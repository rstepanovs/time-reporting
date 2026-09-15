# Plan: worker dashboard — current month calendar and this year's hours by month

## Context

The signed-in landing page (`/`, `pages/HomePage.tsx`) still shows the API/database health probes
from the project skeleton. Workers book time on `/timesheet`, but nothing shows them how much they
have reported against what was expected. We turn `/` into a personal dashboard with:

1. **A link to this week's timesheet** — a button at the top, to `/timesheet`.
2. **Current month calendar** — rows = ISO weeks, columns Mon–Sun + week total; each day shows the
   hours booked, weekends / public holidays / bridge days / company days off are highlighted, a
   past working day with no hours is flagged; week total is `reported / expected`; the week number
   links to that week's timesheet.
3. **This year's hours by month** — rows = months from January to the current month (current one
   marked "in progress"), columns expected / normal / overtime / travel / (other) / total / Δ;
   a month row expands into a per-project breakdown; a year totals row at the bottom.

The timesheet page itself is out of scope — it will be redesigned separately. The dashboard only
links to it.

```
[Open this week's timesheet →]

September 2026
Week  Mon  Tue  Wed  Thu  Fri  Sat  Sun | Total
 36    8    8    8    8    8    ·    ·  | 40 / 40
 37    8    8   (H)   6    ·    ·    ·  | 22 / 32
 38    8    ·    ·    ·    ·    ·    ·  |  8 / 40
Month: 70 h · expected to date 80 h · expected for the month 168 h

2026
Month          Expected  Normal  Overtime  Travel  Total    Δ
▸ September*        80      64         6       0     70   −10
▸ August           168     160         8       4    172    +4
▾ July             184     176         0       0    176    −8
    ACME · Portal            120         0       0    120
    Beta · ERP                56         0       0     56
Total 2026        1336    1290        30      12   1332    −4
```

### Decisions confirmed with the user

- Two tables on the dashboard plus a link to the current timesheet; no embedded timesheet grid.
- Calendar shows only the current month (no month navigation — past months are in the year table).
- Year table: rows = months of the current year, per-project breakdown on expanding a month
  (projects are not columns — their number varies per worker).
- **Hours only**: per diems (`day`) and expenses (`amount`) are not shown on the dashboard.
- **Expected hours**: one global setting `DAILY_WORKING_HOURS` (default 8). A working day is not a
  weekend and has no `NonWorkingDay` (any kind). Expected = working days × 8. For the current month,
  Δ is computed against expected hours *to date* (working days up to today).

### Design principles

- **All aggregation lives in the timesheets module** (it owns `TimeEntry`), as two new queries in
  `timesheets/contracts.py`. Billing item presets and project/customer names come only from the
  existing batch queries `GetProjectBillingItemsByIds` / `GetProjectsByIds`, the calendar from
  `GetCalendarDays` — no new cross-module queries (`test_module_boundaries.py` stays green).
- **Only `hour`-unit entries** (the denormalized `TimeEntry.unit`) are aggregated. Categorized by
  the billing item's preset: `normal_hours` / `overtime_hours` / `travel_hours`, custom hour items →
  `other_hours`. Entries on archived projects/items still count.
- **`today` is a field of the query messages** (the router passes `date.today()`), so "to date" and
  "in progress" are deterministic in tests.
- **Same access rule as a week**: own data by default; another user's `user_id` only for admin /
  project manager (403 otherwise). The dashboard shows only the caller's own data.
- Ranges stay within `GetCalendarDays`' 366-day cap: a month calendar spans ≤ 6 weeks, a year
  summary ≤ one calendar year.

## Backend

### Setting

`core/config.py`: `daily_working_hours: Decimal = Field(default=Decimal("8"), gt=0, le=24)` with a
comment; `DAILY_WORKING_HOURS=8` in `.env.example`. Read via `get_settings()`, as
`work_calendar/service.py` reads `holiday_country`.

### Contracts (`modules/timesheets/contracts.py`)

DTOs:

- `HoursTotalsDTO(normal_hours, overtime_hours, travel_hours, other_hours, total_hours: Decimal)`.
- `CalendarDayHoursDTO(calendar_day: CalendarDayDTO, in_month: bool, is_working_day: bool,
  expected_hours: Decimal, hours: Decimal)`.
- `CalendarWeekHoursDTO(week_start: date, iso_week: int, days: tuple[CalendarDayHoursDTO, ...],
  expected_hours: Decimal, hours: Decimal)` — week totals include days outside the month.
- `MonthCalendarDTO(user: UserDTO, year, month: int, weeks: tuple[CalendarWeekHoursDTO, ...],
  expected_hours, expected_hours_to_date, hours: Decimal)` — month totals count only `in_month`
  days; "to date" = working days `<= today`.
- `ProjectHoursDTO(project: ProjectDTO, totals: HoursTotalsDTO)`.
- `MonthHoursDTO(year, month: int, is_current: bool, working_days: int, expected_hours,
  expected_hours_to_date: Decimal, totals: HoursTotalsDTO, projects: tuple[ProjectHoursDTO, ...])`
  — projects sorted by customer name, project name; only projects with hours that month.
- `YearHoursDTO(user: UserDTO, year: int, months: tuple[MonthHoursDTO, ...], expected_hours,
  expected_hours_to_date: Decimal, totals: HoursTotalsDTO)` — `months` newest first.

Queries:

- `GetMonthCalendar(user_id, year, month, today)` → `MonthCalendarDTO`. Range = Monday of the week
  containing the 1st … Sunday of the week containing the last day. Raises `UserNotFoundError`.
- `GetYearHours(user_id, year, today)` → `YearHoursDTO`. Months: January … `today`'s month when
  `year == today.year`, all 12 for a past year, none for a future year. Every listed month is
  present even with no hours. For past months `expected_hours_to_date == expected_hours`. Raises
  `UserNotFoundError`.

### Repository (`modules/timesheets/repository.py`)

- Month calendar: `sum_quantity_by_date` already exists but takes a set of dates; add
  `sum_hours_by_date_in_range(user_id, date_from, date_to) -> dict[date, Decimal]` (unit `hour`).
- Year: `sum_hours_by_month_and_billing_item(user_id, date_from, date_to)` → rows of a small
  frozen dataclass `(month_start: date, project_id, billing_item_id, total)`, grouped by
  `date_trunc('month', entry_date)::date`, project and billing item, filtered to unit `hour`.
  Both use the existing `(user_id, entry_date)` index.

### Service (`modules/timesheets/summary.py`, new `TimesheetSummaryService(bus)`)

Separate from `service.py` (week read/write) — read side only.

- `month_calendar(...)`: user, hours by date, calendar days → weeks of 7 days; expected per day =
  `daily_working_hours` if working day else 0.
- `year_hours(...)`: one `GetCalendarDays` over Jan 1 … end of the last listed month (working days
  per month, working days to date); one repository aggregation; one `GetProjectBillingItemsByIds`
  and one `GetProjectsByIds` for the distinct ids; fold into per-month and per-(month, project)
  totals; year totals = sums over the listed months.
- Private helpers: `_month_bounds`, `_start_of_iso_week`, `_end_of_iso_week`, `_is_working_day`,
  `_HoursAccumulator` (adds a quantity by preset, freezes to `HoursTotalsDTO`).

`handlers.py`: `GetMonthCalendarHandler`, `GetYearHoursHandler`; register in `module.py`.

### HTTP (`modules/timesheets/router.py`, `schemas.py`)

- `GET /timesheets/calendar?year=&month=&user_id=` → `MonthCalendarResponse`
  (`year` 2000–2100, `month` 1–12; both default to today's).
- `GET /timesheets/years/{year}?user_id=` → `YearHoursResponse` (`year` 2000–2100).
- Extract the week endpoint's view check into `_resolve_target_user(current_user, user_id)`, used by
  all three GETs; `UserNotFoundError` → 404.
- Response models mirror the DTOs (`from_attributes`), reusing `CalendarDayResponse`,
  `TimesheetProjectResponse`, `TimesheetUserResponse`.

## Frontend

### API layer (`frontend/src/timesheets/`)

- `npm run gen:api` once the endpoints exist.
- `api.ts`: types `MonthCalendar`, `CalendarWeekHours`, `CalendarDayHours`, `YearHours`,
  `MonthHours`, `HoursTotals`; `getMonthCalendar({ year, month, userId? })`,
  `getYearHours({ year, userId? })`, via `timesheetAwareError`.
- `hooks.ts`: `timesheetKeys.summaries()` = `[...all, "summaries"]` with `monthCalendar(userId,
  year, month)` / `yearHours(userId, year)` under it; `useMonthCalendar`, `useYearHours`.
  `useSaveTimesheetWeek.onSuccess` also `invalidateQueries({ queryKey: timesheetKeys.summaries() })`
  so the dashboard is fresh after booking time.
- `week.ts`: `formatMonthLabel(year, month)` ("September 2026"), `formatHours(value)`; tests.
- `dayStatus.ts` (pure, tested): `dayStatus(day, today)` → `"off"` | `"future"` | `"today"` |
  `"complete"` (hours ≥ expected > 0) | `"partial"` | `"missing"` (past working day, 0 h) |
  `"extra"` (hours on a non-working day).
- `dayKind.ts`: extract `TimesheetGrid.DayHeader`'s kind → background color mapping so the
  calendar and the grid share it.

### Components

- `timesheets/MonthCalendar.tsx` — props `{ userId, year, month, today }`. Mantine `Table` in
  `Table.ScrollContainer`: `Week | Mon … Sun | Total`. Day cell: day number (dimmed outside the
  month), hours, background by kind, status accent, tooltip with the non-working day's name,
  `data-kind` / `data-status` for tests. Week number links to `/timesheet?week=<week_start>`.
  Total `22 / 32 h`. Caption below: month hours · expected to date · expected for the month.
- `timesheets/YearHoursTable.tsx` — props `{ userId, year }`. Columns
  `Month | Expected | Normal | Overtime | Travel | Other | Total | Δ`; "Other" shown only when any
  month has other hours. Current month gets an "In progress" badge and Δ against expected to date;
  Δ colored (red negative, green positive). Chevron toggles project sub-rows (customer · project,
  hour columns only). Footer: year totals (Δ against the year's expected to date). Empty state when
  nothing was booked this year.

### Page, routing, navigation

- `pages/DashboardPage.tsx`: title "Dashboard", button "Open this week's timesheet" (`Link` to
  `/timesheet`), section with `formatMonthLabel` + `MonthCalendar`, section "<year>" +
  `YearHoursTable`. Uses `todayIso()` from `week.ts` for year/month/today.
- `router.tsx`: index route → `DashboardPage`; delete `pages/HomePage.tsx`.
- System status moves to admins: `pages/admin/AdminSystemStatusPage.tsx` (probe code moved as is)
  at `/admin/status`, "System status" in `ADMIN_NAV_ITEMS`.
- `components/AppLayout.tsx`: `NAV_ITEMS` = Dashboard (`/`), Timesheet, Projects.

## Tasks (one commit each)

1. **Commit this plan** (revision of `.claude/plans/worker-dashboard.md`).
2. **Backend: summary queries** — setting + `.env.example`; contracts; repository methods;
   `summary.py`; handlers + registration. Tests `backend/tests/test_timesheets_summary_handlers.py`:
   expected hours skip weekends and each non-working-day kind; calendar spans full ISO weeks with
   `in_month`, week totals include outside days, month totals don't; `expected_hours_to_date` by
   `today`; `day`/`amount` entries ignored; preset categorization incl. a custom hour item →
   `other_hours`; per-project breakdown; archived project still counted; year lists Jan…current
   month (all 12 for a past year, none for a future one), empty months present; unknown user raises.
3. **Backend: HTTP endpoints** — schemas, routes, shared view check. Tests in
   `test_timesheets_api.py`: worker reads own calendar / year; worker asking for another user → 403;
   manager allowed; 404 unknown user; 422 for `month=13`.
4. **Seed: demo history** — book normal hours on working days (via `GetCalendarDays`) for the last
   3 months up to today, plus a few overtime/travel hours, for the demo worker and manager, so both
   tables have data; keep "skip if the user already has entries"; adjust `test_seed.py`.
5. **Frontend: API layer** — `gen:api`, `api.ts`, `hooks.ts`, `week.ts` helpers, `dayStatus.ts`,
   `dayKind.ts` (used by `TimesheetGrid`), unit tests, fixtures `testMonthCalendar` /
   `testYearHours` in `test/fixtures.ts`.
6. **Frontend: components** — `MonthCalendar.tsx`, `YearHoursTable.tsx`.
7. **Frontend: page and navigation** — `DashboardPage.tsx`, router, nav, `/admin/status`. Tests
   `pages/DashboardPage.test.tsx` (mock `@/auth/api`, `@/timesheets/api`): link to `/timesheet`,
   week rows and totals, day `data-kind`/`data-status`, week link targets, month row expands to
   projects, "Other" column hidden when zero; update `AppLayout.test.tsx`.
8. **Docs** — `CLAUDE.md`: new queries/endpoints in the timesheets paragraph,
   `DAILY_WORKING_HOURS`, `/` is the dashboard (replace "`/timesheet` is the default landing page"),
   `/admin/status`, new frontend files, seed history.

## Verification

- Backend: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest`
  (no migration — no schema change).
- Frontend (`frontend/`): `npm run gen:api`, `npm run lint`, `npm run typecheck`, `npm test`,
  `npm run build`.
- Manual: `uv run time-reporting seed-demo`, backend + `npm run dev`, sign in as the demo worker:
  `/` shows the button to the timesheet, the current month calendar with holidays/bridge day
  highlighted and correct week totals, week number opens that week; the year table lists
  January…current month with correct Δ and expands to projects; booking hours on `/timesheet` and
  returning to `/` shows updated numbers; `/admin/status` works for an admin and is a 404 for the
  worker; `GET /api/v1/timesheets/years/2026?user_id=<other>` as the worker → 403.
