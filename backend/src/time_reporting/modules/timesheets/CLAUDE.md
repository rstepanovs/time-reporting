# timesheets module

Owns `TimeEntry`, `TimesheetRowComment`, `TimesheetWeek` (status) and `ProjectBillingPeriod`.

Depends on: `projects.contracts` (`ListMemberProjectsWithBillingItems`,
`ListManagedProjectsWithMembers`, `GetProjectsByIds`, `GetProjectBillingItemsByIds`),
`work_calendar.contracts` (`GetCalendarDays`), `users.contracts` (`GetUserById`, `GetUsersByIds`,
`UserRole`). Consumed by `admin` via `CountTimeEntries`.

## Entries and the weekly grid

- `TimeEntry`: at most one row per (user, billing item, date), holding a `quantity` in the billing
  item's `unit` (hours, days or a money amount) and an optional note.
- `project_id` and `unit` are denormalized onto the row from the billing item at write time (never
  changed afterwards) so this module's own queries — summing a user's hours for a day, filtering by
  project — never join into the projects module's tables; both are guarded by `ON DELETE RESTRICT`,
  so a project, billing item or user with time entries can't be permanently deleted.
- Each row can also carry a `TimesheetRowComment` — a per (user, week, billing item) note, separate
  from each `TimeEntry.note` — so `GetTimesheetWeek`'s rows are keyed off the union of billing items
  with entries *or* a comment (a comment-only row is still listed).
- `GetTimesheetWeek(user_id, week_start, viewer_id)` reads a Monday-to-Sunday week (raises
  `WeekStartNotMondayError` otherwise): its rows carry `is_open` (from
  `ListMemberProjectsWithBillingItems` — still a member, project and billing item both active) so a
  week keeps showing entries booked before a project was archived or the user removed, but
  read-only.
- The week has a `status` (`TimesheetWeekStatus`: `draft`/`submitted`/`approved`/`returned`, backed
  by a `TimesheetWeek` row keyed `(user_id, week_start)` — no row means `draft`, the status is never
  persisted as `draft`). `can_edit`/`can_submit` are `viewer_id == user_id` and the week is
  `draft`/`returned`, while `can_review` is the viewer holding `manager`, the week being
  `submitted`/`approved`, and the viewer not being the week's owner — nobody, not even an admin,
  reviews their own week. None of these three are enforced here — only computed for the caller to
  render around — the router still owns authorization.
- `SaveTimesheetWeek` applies a batch of cell changes (`quantity=None` deletes a cell) and
  `row_comments` changes (`comment=None`/blank deletes one) as one command: raises
  `TimesheetWeekLockedError` if the week is `submitted`/`approved`, else validates the
  week/dates/no-duplicate-cells first, then that every targeted row (whether a cell or a comment) is
  open (`TimesheetRowClosedError`, or `TimesheetBillingItemNotFoundError` if the item doesn't exist
  at all) and each quantity is in range for its unit, applies them, and only then re-checks that the
  user's total `hour`-unit quantity per day is still ≤ 24 (`DailyHoursExceededError`) — checked after
  applying the batch specifically so moving hours between two rows in one save works even though an
  intermediate per-change state would not.
- Deleting a whole row from the UI is expressed as a save that nulls every one of its cells and its
  comment — there's no separate "delete row" message.
- Any authenticated user reads and writes their own week. `CountTimeEntries` (filterable by
  user/project/billing item) backs the admin module's removal-impact reporting.

## Workflow

- `SubmitTimesheetWeek` (draft/returned → submitted, owner only) and `ApproveTimesheetWeek` /
  `ReturnTimesheetWeek` (submitted → approved, or submitted/approved → `returned` with a required
  `comment`, `ManagerDep` at the router) drive the workflow, each raising
  `InvalidWeekStatusTransitionError` outside its allowed source statuses and `SelfReviewError` for
  anyone — including an admin — reviewing their own week.
- `ListSubmittedTimesheetWeeks` (oldest submission first, with each week's total `hour`-unit
  quantity via `TimeEntryRepository.sum_hours_by_user_week`, optional `manager_id` for the "my
  projects" scope) backs the frontend's approvals page.

## Employee dashboard queries

All follow the week endpoint's view rule (own data, or another user's for a `manager`) via the HTTP
layer's `_resolve_target_user`. `today` is a field of each query (the router fills in the real
date) so "expected to date" and "which month is current" stay deterministic in tests.

- `GetMonthCalendar(user_id, year, month, today)` renders a month as full ISO weeks with
  expected-vs-booked `hour`-unit totals per day/week (expected hours = working days, from
  `GetCalendarDays`, times `Settings.daily_working_hours`).
- `GetYearHours(user_id, year, today)` sums a year's `hour`-unit entries by month, split by billing
  item preset (`normal_hours`/`overtime_hours`/`travel_hours`, any other preset or a custom item as
  `other_hours`) with a per-project breakdown. `day`/`amount`-unit entries (per diems, expenses)
  aren't part of either query — the dashboard is hours-only.
- `GetMonthTimeSummary(user_id, year, month, today)` is one month's hours (as `HoursTotalsDTO`) plus
  the benefits `HoursTotalsDTO` leaves out — `day`-unit entries as `per_diem_days`, `amount`-unit
  entries summed per customer currency (never combined across currencies) as `expenses`.
- `GetWeeklyHours(user_id, weeks, today)` is `weeks` ISO weeks ending with `today`'s week (oldest
  first, capped at `MAX_WEEKLY_HOURS_WEEKS` = 26, `WeekRangeOutOfBoundsError` outside that) with a
  per-project hour breakdown over the whole range.

## Team overview (`team.py`)

`GetTeamMonthOverview(manager_id, year, month, today)` (a separate `TeamOverviewService` reusing
`summary.py`'s pure helpers) backs a manager's team dashboard cards and the `/team` page: for every
project `manager_id` manages (`manager_id=None` covers every active project — the router's
`scope=all`, available to any manager — via `projects.ListManagedProjectsWithMembers`):
- its current members plus anyone else who booked time on it this month but was since removed
  (`TeamMemberDTO.is_member=False`, still shown, read-only history);
- each member's per-ISO-week status/hours (`TeamMemberWeekDTO` — a straddling week's `project_hours`
  are clipped to the query month's days, `total_hours` are not, matching what that week's own page
  would show) plus a non-blocking `warning` (`no_entries` / `under_expected_hours`, only for current
  members);
- a dashboard-card status tally (`TeamStatusCountsDTO`: awaiting_approval/returned/not_submitted/
  approved, one count per distinct current-member × in-scope-week pair);
- each project's billing readiness (`ProjectBillingPeriodDTO`).

## Billing handoff and locking

- A project's billing readiness for a calendar month is computed by `billing_readiness()`
  (`team.py`, a pure function shared with the send command so the rule lives once): its **scope** is
  every (user, ISO week) with at least one entry on the project dated inside the month; it is
  **ready** when that scope is non-empty and every week in it is `approved` — **not ready** otherwise
  (no entries yet, or some week still needs approval/re-approval).
- Sending is a stub — invoicing doesn't exist yet. `SendProjectMonthToBilling(project_id, year,
  month, sent_by_id)` inserts a `ProjectBillingPeriod` row (`project_id`, `period_start`/`period_end`
  = the calendar month, `sent_at`, `sent_by_id`; unique per `(project_id, period_start)`) once ready,
  raising `BillingPeriodNotReadyError` (carries `blocking_weeks`) or
  `BillingPeriodAlreadySentError` otherwise; allowed on any day, not only after the month ends, since
  a project's work can finish early. Any manager may send any project, regardless of its
  `manager_id` — the router's `ManagerDep` is the only check, same as approvals.
- `ReopenProjectBillingPeriod(project_id, period_start)` (admin only) deletes the row, unlocking it.
- Once sent, a period **locks** its dates: `SaveTimesheetWeek` rejects a cell change dated inside a
  sent period, or any row-comment change on a billing item whose project has any sent period
  overlapping the week (`BillingPeriodLockedError`), and `ReturnTimesheetWeek` rejects returning a
  week that has entries on a project with a sent period overlapping it (a return would re-open
  already-billed hours).
- Because a week must already be fully `approved` for its billing period to become ready, and an
  approved week is *itself* locked for editing (`TimesheetWeekLockedError`), the billing lock in
  practice only bites a still-`draft`/`returned` week whose dates fall in an already-sent month, or a
  `return` attempt on an approved one — a week straddling two months has its non-sent days end up
  locked too, until an admin reopens the sent month, an accepted trade-off of week-level (not
  per-date) approval.
- `GetTimesheetWeek`'s `TimesheetRowDTO.locked_dates` reports which of a row's days fall in a sent
  period (regardless of `is_open`), and folds into `can_review` (false once any row is locked, so a
  blocked `return` isn't offered) so the HTTP layer needs no separate lock query.
