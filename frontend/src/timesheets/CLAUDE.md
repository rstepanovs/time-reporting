# frontend timesheets/

Backend: `modules/timesheets` (workflow statuses, locks and billing readiness are documented there).

## API layer

- `api.ts` — read/save a week, `submitTimesheetWeek`/`approveTimesheetWeek`/`returnTimesheetWeek`/
  `listSubmittedTimesheetWeeks` (an optional `{ scope: "mine" | "all" }`), the caller's
  project/billing-item picker, the dashboard's `getMonthCalendar`/`getYearHours`/
  `getMonthTimeSummary`/`getWeeklyHours`, the manager team dashboard's `getTeamMonthOverview` (also
  `scope`-aware) and `sendProjectMonthToBilling`/`reopenProjectBillingPeriod`, admin-only
  `listBillingPeriods` (project/customer/month-range filters, pagination — backs
  `pages/admin/AdminBillingPage.tsx`) and `billingPeriodExportUrl(projectId, periodStart)` (a plain
  relative URL for that page's per-row "CSV" `<a href download>`, never fetched through `api` —
  following `system/api.ts`'s `backupDownloadUrl`), plus `TimesheetRuleError` covering 400/403/404
  and `TimesheetConflictError` for a 409 — the week's status changed underneath the caller, or a
  billing period isn't ready yet / was already sent — both with the backend's `detail` as the
  message.
- `hooks.ts` — `timesheetKeys` + `useTimesheetWeek`/`useTimesheetOptions`/`useMonthCalendar`/
  `useYearHours`/`useMonthTimeSummary`/`useWeeklyHours`/`useSubmittedTimesheetWeeks`/
  `useTeamMonthOverview`/`useBillingPeriods` queries and `useSaveTimesheetWeek`/
  `useSubmitTimesheetWeek`/`useApproveTimesheetWeek`/`useReturnTimesheetWeek`/
  `useSendProjectMonthToBilling`/`useReopenProjectBillingPeriod` mutations. Cache rules:
  - the first four mutations write their result straight into the week's query cache instead of
    invalidating;
  - saving also invalidates `timesheetKeys.summaries()` so the dashboard and `/hours` pick up a
    save, and, along with submit/approve/return, `timesheetKeys.team()`;
  - submit/approve/return also invalidate `timesheetKeys.allSubmissions()` (every cached
    `submissions(scope)`);
  - sending/reopening a billing period invalidate `team()`, `allSubmissions()` and every cached week
    (`timesheetKeys.weeks()`, since locks may have changed what they allow); reopening also
    invalidates every cached `billingPeriods(params)` entry so `/admin/billing` drops the row.

## Pure helpers

- `week.ts` — ISO-date helpers (`startOfIsoWeek`, `weekDays`, `addWeeks`, `addMonths`/
  `previousMonth`, day/week/month/ISO-week label formatting, `formatHours`, `fillRatePercent`) with
  their own unit tests.
- `dayKind.ts` (weekend/holiday/bridge background colors) and `dayStatus.ts` (a calendar day's status
  — off/future/today/complete/partial/missing/extra — versus its expected hours), shared by the grid
  and the month calendar.

## Weekly grid (`TimesheetGrid.tsx`, used by `pages/TimesheetPage.tsx`)

- Local draft state holds only actual edits keyed by billing-item+date, plus a separate
  billing-item-keyed map of pending row-comment edits and a set of billing items marked for deletion,
  so Save sends just the changed cells/comments and the null-outs a deleted row needs.
- A closed row, or the week once `submitted`/`approved`, renders read-only.
- An empty `draft` week with exactly one open project is seeded once on load with that project's
  `normal_working_hours` on every working day — kept in a draft-only prefill map so it renders and
  saves like a normal edit but doesn't itself count as "dirty" (no unsaved-changes prompt on an
  untouched prefilled week).
- A row's `locked_dates` (dates already sent to billing) render read-only regardless of `is_open`,
  with a lock icon/tooltip per cell and a "Sent to billing" badge on the row; such a row can't have
  its comment edited or be deleted, and the week shows a "Sent to billing" alert whenever any row is
  locked.
- A status header shows the week's `status` badge and, once reviewed, who reviewed it and when, plus
  the return comment when `returned`. "Submit" (behind a confirming modal, auto-saving first if
  there's anything pending) and, for a manager viewing the week, "Approve"/"Return…" (the latter's
  modal requires a non-blank comment; both hidden once `can_review` is false, including when a locked
  row would make a return fail) appear per `can_submit`/`can_review`.
- `AddRowModal.tsx` — "add a row" / "copy rows from previous week". The month calendar renders below
  the grid.

## Hours views

- `MonthCalendarTable.tsx` / `YearHoursTableView.tsx` are presentational (already-loaded data as
  props, an optional `title` override, `title=""` to hide it) — weeks as rows/Mon..Sun as columns with
  the week number linking to `/timesheet?week=`, and one row per month (newest first, columns per
  hours category plus Δ against hours expected to date, expanding into a per-project breakdown)
  respectively.
- `MonthCalendar.tsx` / `YearHoursTable.tsx` are thin data-loading wrappers around them, reused by
  `pages/HoursPage.tsx` (`/hours`, month navigation via a `?month=YYYY-MM` param) and, for the
  current/previous month, by the dashboard's `MonthTimeCard.tsx`.

## Dashboard (`pages/DashboardPage.tsx`)

The dashboard is a list of sections gated by the level(s) the signed-in user holds, always in this
order: **My time** (everyone) → **My team** (`manager`) → **Billing** (`accountant`) →
**Administration** (`admin`); a combined user (e.g. `admin`+`manager`) sees every section their
levels unlock.

### My time (everyone)

All render inside `components/DashboardCard.tsx`, in a responsive `SimpleGrid`.
- `QuickActionsCard.tsx` — "Report time" / "Previous week" shortcuts to `/timesheet`.
- `MonthTimeCard.tsx` — one month's hours by preset, a reported/expected-to-date total with fill rate
  %, and per-diem/expense benefits, linking to `/hours?month=`.
- `WeeklyHoursChart.tsx` — `@mantine/charts` `CompositeChart`: hours booked per week as bars against
  expected hours as a dashed reference line on the *same* hours axis — never a fill-rate-% line on a
  second axis — over the last 6 ISO weeks.
- `WeeklyProjectHoursCard.tsx` — each project's total/overtime hours over that same 6-week window,
  sharing `WeeklyHoursChart`'s query/cache.
- `MyProjectsCard.tsx` — the user's projects, linking to each.

### Billing (`accountant`)

- `AccountantPlaceholderCard.tsx` — a single `DashboardCard` noting that invoicing tools are coming;
  static text only, no data calls. The accountant level is only a flag until the invoices module
  lands.

The Administration section (`admin`) is `admin/AdminShortcutsCard.tsx`, documented in
`admin/CLAUDE.md`.

## Manager views

- `TeamScopeToggle` — "My projects"/"All", available to any manager. URL-backed (`?scope=`) on
  `/approvals` and `/team`, local state on the dashboard.
- `pages/ApprovalsPage.tsx` (`/approvals`) is a Mantine `Tabs` (URL-backed `?tab=timesheets|
  expenses`, default `timesheets`) over two independent lists, the one `TeamScopeToggle` applying
  to both: "Timesheets" lists weeks awaiting review via `useSubmittedTimesheetWeeks` narrowed by
  the scope, each row linking to `/timesheet?week=&user=`; "Expenses" is the same for expense
  reports via `expenses.useSubmittedExpenseReports`, each row linking to `/expenses/:reportId` —
  see `expenses/CLAUDE.md`. Approve/return themselves happen on the target page
  (`TimesheetGrid`/`ExpenseReportPage`), not on this list.
- The dashboard's "My team" section (`manager` only), driven by `useTeamMonthOverview` for the
  current month:
  - `TeamTimesheetsCard.tsx` — awaiting-approval/returned/not-submitted counts, linking to
    `/approvals?scope=`.
  - `ProjectBillingCard.tsx` — each managed project's hours, weeks-approved x/y (plus a blocking
    expense-report count when `blocking_reports > 0`) and billing status for a ‹›-navigable month
    (previous month during a month's first 10 days, current month after), with a "Send to billing"
    button behind a confirming modal for a `ready` project.
  - `TeamStaffCard.tsx` — everyone on the manager's projects, deduplicated across projects, hours
    reported this month vs. expected with a warning icon/tooltip, linking to `/timesheet?week=&user=`
    for the current week; footer "Team overview →" to `/team`.
- `pages/TeamPage.tsx` (`/team`, nav item right after Approvals) is the fuller view: the scope toggle
  and a `?month=YYYY-MM` navigator like `/hours`, then per managed project a header (customer/name,
  hours, weeks approved x/y plus the same blocking-report count, a billing status badge, the same
  "Send to billing" modal when `ready` or, once `sent`, an admin-only "Reopen" behind its own
  confirming modal) and `TeamWeekMatrix.tsx` (presentational: members × the month's ISO weeks, each
  cell a status badge plus that member's hours on the project that week linking to
  `/timesheet?week=&user=`, a week outside the queried month marked with `*`, a warning icon/tooltip
  per member). Neither view lists the project's expense reports themselves — only the blocking
  count; see the "Expenses" tab of `/approvals` or `/expenses` for the reports.
