# expenses module

Owns `ExpenseReport` and `ExpenseReportLine`: an employee's claim for money spent on a project in
one calendar month, with lines instead of the days a timesheet week has, submitted and approved the
same way a timesheet week is.

Depends on `projects.contracts` (`ListMemberProjectsWithBillingItems` with
`units={BillingUnit.AMOUNT}`, `GetProjectById`, `GetProjectsByIds`, `GetProjectBillingItemsByIds`,
`ListManagedProjectsWithMembers`), `users.contracts` (`GetUserById`, `GetUsersByIds`) and
`audit.contracts` (`RecordAuditEvent`). Must never depend on `timesheets.contracts` — the billing
handoff runs the dependency the other way (see "Billing handoff and locking" below).

## Reports and lines

- One report per `(user, project, calendar month)` (`uq_expense_reports_user_id_project_id_period_start`);
  `period_start`/`period_end` are that month's bounds. Unlike `timesheets.TimesheetWeek`, a `draft`
  row *is* persisted — the document has to exist before lines (and later, attachments) can hang off
  it, so `ExpenseReportStatus.DRAFT` is a real, stored state, not a "no row" convention.
- `CreateExpenseReport` requires the user to currently be an active member of an active project
  that has at least one active `amount` billing item — checked in one round trip via
  `ListMemberProjectsWithBillingItems(units={AMOUNT})`, the same query `timesheets` uses for `hour`/
  `day` items. Any other case (unknown project, archived project, not a member, no expense items)
  raises `ExpenseProjectClosedError`; an existing report for the same user/project/month raises
  `ExpenseReportAlreadyExistsError`.
- A line's `billing_item_id` must be one of the report's *own* project's currently-open `amount`
  items (`ExpenseBillingItemNotFoundError` otherwise — this module doesn't distinguish "unknown"
  from "closed", unlike `timesheets`' two-way split, since a line has no independent life outside
  its report); its `expense_date` must fall inside the report's period
  (`ExpenseDateOutsidePeriodError`).
- `SaveExpenseReportLines` is one batch (creates + updates + deletes) in one transaction, validated
  entirely before anything is applied — the same pattern as `timesheets.SaveTimesheetWeek`. Unlike
  a timesheet cell (naturally keyed by `(billing_item_id, date)`), a line has no natural key — two
  receipts can share a billing item and date — so changes carry an explicit `line_id` (`None` =
  new). A `line_id` present in both an update and `delete_line_ids` is deleted; deleting an id that
  isn't one of the report's own lines is a no-op.
- `DeleteExpenseReport` only works on a `draft` report (stricter than editing, which also allows
  `returned`); it cascades to the report's lines by `ON DELETE CASCADE`.
- Editability: `ExpenseReportNotEditableError` when the status isn't `draft`/`returned`;
  `ExpenseReportLockedError` when `locked_at` is set. Both are checked on every write
  (`SaveExpenseReportLines`, and `ReturnExpenseReport`'s own lock check).

## Workflow

`ExpenseReportStatus`: `draft` → `submitted` → `approved`/`returned`, the same shape and rules as
`timesheets.TimesheetWeekStatus`: any manager may approve/return any report, never their own
(`ExpenseSelfReviewError`); `ReturnExpenseReport` works from either `submitted` or `approved` and
requires a non-empty `comment`, but is refused once the report is locked
(`ExpenseReportLockedError` — un-approving hours already sent to billing isn't allowed). Only
`ApproveExpenseReport` and `ReturnExpenseReport` are audited (`expense_report.approved` /
`expense_report.returned`, `entity_id` the report's own id) — creating, saving lines and submitting
are not, mirroring `timesheets`, which only audits the billing handoff itself.

`get_report` computes `can_edit`/`can_submit`/`can_review`/`is_locked` for the **viewer** passed in
— note that after `ReturnExpenseReport`/`ApproveExpenseReport` return their DTO, the viewer is the
reviewer, so that DTO's `can_edit` reflects the reviewer's own (lack of) editing rights, not the
report owner's; re-query with `viewer_id=<owner>` to see the owner's view. Advisory only, as with
`TimesheetService.get_week` — the router owns authorization.

## Billing handoff and locking

A report has no notion of "sent to billing" of its own; `LockProjectMonthExpenseReports`/
`UnlockProjectMonthExpenseReports` are **nested-only** commands (no HTTP route) that set/clear
`locked_at` on every report of a project's month, meant to be executed from `timesheets`' own
`SendProjectMonthToBilling`/`ReopenProjectBillingPeriod` handlers so the lock commits in the same
transaction as the handoff — `expenses` never reads `ProjectBillingPeriod` to know this itself.
`ListProjectMonthExpenseReports(project_id, period_start)` is how `timesheets` reads a
project-month's reports back for its billing readiness rule and totals — the one place the
dependency direction between the two modules is `timesheets` → `expenses`, never the reverse.
`ListSubmittedExpenseReports(manager_id)` backs a manager's approvals list, scoped through
`projects.ListManagedProjectsWithMembers` exactly like `timesheets.ListSubmittedTimesheetWeeks`.
