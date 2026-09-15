# Plan: worker dashboard as widget cards + reusable hour tables on a "My hours" page

## Context

The first dashboard (`pages/DashboardPage.tsx`: `MonthCalendar` + `YearHoursTable`) works, but the
user wants the start page to look like a widget board (reference screenshot of another time
reporting system): small cards side by side — actions, "my time" for the current and previous
month with hours and benefits, reported hours per week with a fill-rate line, hours per project,
my projects. The two tables already built should not be thrown away: they become reusable
components and get their own page, `/hours` ("My hours"), linked from the dashboard.

Target layout (cards wrap on narrow screens):

```
┌ Actions ────────┐┌ My time · Sep 2026 ┐┌ My time · Aug 2026 ┐┌ Hours per week ────┐┌ Hours per project ─┐
│ [Report time]   ││ Normal      64 h   ││ Normal     160 h   ││ ▇ ▇ ▇ ▅ ▇ ▂        ││ Project  Total  OT │
│ [Previous week] ││ Overtime     6 h   ││ Overtime     8 h   ││ W34 … W39          ││ ACME·Web  128    6 │
│                 ││ Travel       0 h   ││ Travel       4 h   ││ ── fill rate %     ││ Beta·ERP   40    0 │
│                 ││ Total 70/80  88%   ││ Total 172/168 102% ││                    ││ (last 6 weeks)     │
│                 ││ Per diem  2 days   ││ Per diem  5 days   ││                    ││                    │
│                 ││ Expenses 120 EUR   ││ Expenses   0       ││                    ││                    │
│                 ││        Details →   ││        Details →   ││                    ││                    │
└─────────────────┘└────────────────────┘└────────────────────┘└────────────────────┘└────────────────────┘
┌ My projects ────┐
│ ACME · Website  │
└─────────────────┘
```

### Decisions confirmed with the user

1. Existing tables → reusable components (presentation split from data loading, optional title,
   own tests) **plus** a `/hours` page (month calendar with month navigation + year table); month
   cards link to it ("Details →").
2. Month cards show **benefits too**: per-diem days (`day` unit) and expenses (`amount` unit)
   summed **per currency**, never across currencies.
3. Chart and per-project table use **ISO weeks**: current week + 5 previous.
4. Chart via **`@mantine/charts`** (recharts), version matching `@mantine/core` 9.6.1.
5. "Loading" (planned allocation) widget is skipped — the system has no planning data.
   "Charge rate" becomes **fill rate** = reported hours / expected hours to date (no billable vs
   non-billable split exists).

### Design principles

- Aggregation stays in the timesheets module (`modules/timesheets/summary.py`,
  `TimesheetSummaryService`); cross-module data only via existing batch queries
  `GetProjectBillingItemsByIds` / `GetProjectsByIds` and `GetCalendarDays`.
- `today` stays a query field (router passes `date.today()`); access rule via the router's
  existing `_resolve_target_user` (own data; admin/PM may pass `user_id`).
- Reuse `_HoursAccumulator` (extend with days + amounts per currency), `_is_working_day`,
  `_month_bounds`, `_start_of_iso_week` from `summary.py`.
- Every widget is a self-contained component; `components/DashboardCard.tsx` gives them the same
  frame (title, body, optional footer link).

## Backend (`backend/src/time_reporting/modules/timesheets/`)

### Contracts

- `CurrencyAmountDTO(currency: str, amount: Decimal)`.
- `MonthTimeSummaryDTO(user, year, month, is_current, working_days, expected_hours,
  expected_hours_to_date, hours: HoursTotalsDTO, per_diem_days: Decimal,
  expenses: tuple[CurrencyAmountDTO, ...])` — `per_diem_days` = all `day`-unit entries, expenses =
  all `amount`-unit entries grouped by the project's customer currency, sorted by currency.
- `WeekHoursDTO(week_start, iso_year, iso_week, is_current, expected_hours,
  expected_hours_to_date, totals: HoursTotalsDTO)`.
- `WeeklyHoursDTO(user, weeks: tuple[WeekHoursDTO, ...], projects: tuple[ProjectHoursDTO, ...])`
  — weeks oldest → newest; projects = per-project hour totals over the whole range, sorted by
  customer name, project name.
- Queries: `GetMonthTimeSummary(user_id, year, month, today)`;
  `GetWeeklyHours(user_id, weeks, today)` — the `weeks` ISO weeks ending with `today`'s week.
  Raises `UserNotFoundError`; `GetWeeklyHours` raises new `WeekRangeOutOfBoundsError` unless
  `1 <= weeks <= MAX_WEEKLY_HOURS_WEEKS` (26).

### Service (`summary.py`)

- Both read entries with the existing `TimeEntryRepository.list_for_user_in_range` (a month /
  ≤ 26 weeks) and aggregate in Python, like `month_calendar` does — no new SQL.
- `_HoursAccumulator` → `_QuantityAccumulator`: adds by unit (`hour` by preset, `day` → days,
  `amount` → per currency) with `hours()` still freezing to `HoursTotalsDTO` so `year_hours`
  is unchanged.
- Currency comes from `GetProjectsByIds` (`project.customer.currency`), preset from
  `GetProjectBillingItemsByIds`, working days from `GetCalendarDays`.
- Handlers `GetMonthTimeSummaryHandler`, `GetWeeklyHoursHandler`; register in `module.py`.

### HTTP (`router.py`, `schemas.py`)

- `GET /timesheets/months/{year}/{month}/summary?user_id=` → `MonthTimeSummaryResponse`
  (`year` 2000–2100, `month` 1–12 via `Path`).
- `GET /timesheets/weekly-hours?weeks=6&user_id=` → `WeeklyHoursResponse` (`weeks` 1–26 via
  `Query`, default 6); `WeekRangeOutOfBoundsError` → 400 (defensive; `Query` bounds give 422).

### Tests

- `tests/test_timesheets_summary_handlers.py`: month summary splits hours by preset, sums per
  diem days, groups expenses per currency across two customers (EUR + GBP), expected/to-date;
  weekly hours returns 6 weeks ending at `today`'s week with `is_current`, expected hours skip
  weekends/non-working days, per-project totals over the range, weeks spanning a year boundary
  (ISO year label), `weeks` 0/27 rejected, unknown user.
- `tests/test_timesheets_api.py`: own data 200, other user as worker 403, as manager 200,
  unknown user 404, out-of-range params 422, unauthenticated 401.

## Frontend (`frontend/src/`)

### Dependency

`npm install @mantine/charts@^9.6.1 recharts@<peer version @mantine/charts asks for>` (commit the
lock file); `import "@mantine/charts/styles.css"` in `main.tsx`. **Load the `dataviz` skill before
writing the chart.**

### API layer (`timesheets/`)

- `npm run gen:api`; `api.ts`: types `MonthTimeSummary`, `WeeklyHours`, `WeekHours`,
  `CurrencyAmount`; `getMonthTimeSummary({ year, month, userId? })`,
  `getWeeklyHours({ weeks, userId? })`.
- `hooks.ts`: `timesheetKeys.monthSummary(userId, year, month)` and
  `weeklyHours(userId, weeks)` under `timesheetKeys.summaries()` (already invalidated by
  `useSaveTimesheetWeek`); `useMonthTimeSummary`, `useWeeklyHours`.
- `week.ts`: `previousMonth(year, month)`, `formatIsoWeekLabel(isoYear, isoWeek)` ("W38"),
  `fillRatePercent(hours, expected)` → number | null; unit tests.

### Reusable tables (refactor of what exists)

- `timesheets/MonthCalendarTable.tsx` (presentational: `{ calendar, today, title? }`) +
  `timesheets/MonthCalendar.tsx` stays the data-loading wrapper (`{ userId, year, month, today,
  title? }`).
- `timesheets/YearHoursTableView.tsx` (presentational: `{ data, title? }`) +
  `timesheets/YearHoursTable.tsx` wrapper.
- Own tests `MonthCalendarTable.test.tsx` / `YearHoursTableView.test.tsx` rendering the existing
  fixtures `testMonthCalendar` / `testYearHours` (move the assertions from `DashboardPage.test.tsx`).

### "My hours" page

- `pages/HoursPage.tsx` at `/hours`: month navigation (‹ Previous · This month · Next ›, state in
  the `?month=YYYY-MM` query param like `TimesheetPage`'s `?week=`), `MonthCalendar` for the
  selected month, `YearHoursTable` for its year. Nav item "My hours" in `AppLayout` after Timesheet.
- `pages/HoursPage.test.tsx`: renders both for `?month=2026-09`, Previous navigates to 2026-08.

### Dashboard widgets

- `components/DashboardCard.tsx`: Mantine `Paper withBorder` with title, children, optional
  `footer` link (right-aligned, like "My time" in the screenshot).
- `timesheets/QuickActionsCard.tsx`: "Report time" → `/timesheet`, "Previous week" →
  `/timesheet?week=<addWeeks(startOfIsoWeek(today), -1)>`.
- `timesheets/MonthTimeCard.tsx` (`{ userId, year, month, today, highlighted? }`): hours rows
  (normal/overtime/travel, other only if > 0), total `reported / expected to date` + fill rate %,
  benefits (per diem days, expenses per currency or "—"); `highlighted` = filled primary
  background for the current month; footer "Details →" to `/hours?month=YYYY-MM`.
- `timesheets/WeeklyHoursChart.tsx` (`{ userId, today }`): `CompositeChart` — bars = total hours,
  line = fill rate % on a right axis, x labels "W34"…, current week labelled "Current"; footer
  "My hours →".
- `timesheets/WeeklyProjectHoursCard.tsx`: table Project · Total · Overtime from
  `WeeklyHours.projects` (same query/cache as the chart), subtitle "Last 6 weeks"; empty state.
- `timesheets/MyProjectsCard.tsx`: `useTimesheetOptions()` → "Customer · Project" list, each
  linking to `/projects/:id`; empty state "You are not a member of any project yet".

### Page

- `pages/DashboardPage.tsx`: `SimpleGrid cols={{ base: 1, sm: 2, lg: 3, xl: 5 }}` with
  QuickActions, MonthTimeCard (current, highlighted), MonthTimeCard (previous month via
  `previousMonth`), WeeklyHoursChart, WeeklyProjectHoursCard; `MyProjectsCard` on the next row.
- `pages/DashboardPage.test.tsx` rewritten (mock `@/timesheets/api`: `getMonthTimeSummary`,
  `getWeeklyHours`, `listTimesheetOptions`): action links, both month cards with fill rate and
  expenses per currency, current card highlighted, project table rows, my projects links, details
  link target; chart only asserted to render its card title (recharts in jsdom).
- New fixtures in `test/fixtures.ts`: `testMonthTimeSummary` (+ previous month), `testWeeklyHours`.

## Tasks (one commit each)

1. Commit this plan as `.claude/plans/worker-dashboard-cards.md`.
2. Backend: month summary + weekly hours queries, accumulator extension, handler tests.
3. Backend: HTTP endpoints + API tests.
4. Frontend: refactor tables into view + wrapper with own tests; `HoursPage` at `/hours` + nav.
5. Frontend: add `@mantine/charts`, API layer (`gen:api`, api/hooks/week helpers + tests, fixtures).
6. Frontend: `DashboardCard` and the five widgets.
7. Frontend: rebuild `DashboardPage` from cards + tests.
8. Docs: `CLAUDE.md` (new queries/endpoints, widgets, `/hours`, `@mantine/charts`).

## Verification

- Backend: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest`
  on a clean migrated DB (`docker compose down -v && docker compose up -d db && alembic upgrade
  head` — the test DB doubles as the dev DB, so seeded data breaks calendar tests).
- Frontend (`frontend/`, Node 24 from nvm): `npm run gen:api`, `npm run lint`, `npm run typecheck`,
  `npm test`, `npm run build`.
- Manual: `uv run time-reporting seed-demo`, backend on :8000 + `npm run dev`, sign in as
  `worker@example.com` / `demo-password`: cards match the layout, fill rates and per-currency
  expenses look right, chart shows 6 weeks, "Details →" opens `/hours?month=…`, month navigation
  on `/hours` works; take a screenshot for the user via the browser. Reset the DB afterwards only if
  tests need to run again.
