# expenses module

Owns `ExpenseReport` and `ExpenseReportLine`: an employee's claim for money spent on a project in
one calendar month, with lines instead of the days a timesheet week has.

Depends on `projects.contracts` (`ListMemberProjectsWithBillingItems` with
`units={BillingUnit.AMOUNT}`, `GetProjectById`, `GetProjectBillingItemsByIds`) and `users.contracts`
(`GetUserById`). Must never depend on `timesheets.contracts` — the billing handoff (once it exists)
will run the dependency the other way, `timesheets` reaching into `expenses`, so the lock this
module's `locked_at` column exists for can be written from there without a contract cycle.

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
  `ExpenseReportLockedError` when `locked_at` is set. `locked_at` has no writer yet — the column
  and the check exist ahead of the billing handoff that will set it.

## Status and review flags

`ExpenseReportStatus`: `draft`, `submitted`, `approved`, `returned` — the transition commands
(submit/approve/return) don't exist yet; `get_report` already computes `can_edit`/`can_submit`/
`can_review`/`is_locked` for the viewer the same way `TimesheetService.get_week` does (advisory
only, the router owns authorization), ready for those commands to use once added.
