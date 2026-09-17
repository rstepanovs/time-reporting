# expenses module

Owns `ExpenseReport`, `ExpenseReportLine` and `ExpenseAttachment`: an employee's claim for money
spent on a project in one calendar month, with lines instead of the days a timesheet week has,
submitted and approved the same way a timesheet week is, and receipt/invoice scans attached to the
report as a whole.

Depends on `projects.contracts` (`ListMemberProjectsWithBillingItems` with
`units={BillingUnit.AMOUNT}`, `GetProjectById`, `GetProjectsByIds`, `GetProjectBillingItemsByIds`,
`ListManagedProjectsWithMembers`), `users.contracts` (`GetUserById`, `GetUsersByIds`) and
`audit.contracts` (`RecordAuditEvent`). Must never depend on `timesheets.contracts` — the billing
handoff runs the dependency the other way (see "Billing handoff and locking" below).

## Reports and lines

- One report per `(user, project, calendar month)` (`uq_expense_reports_user_id_project_id_period_start`);
  `period_start`/`period_end` are that month's bounds. Unlike `timesheets.TimesheetWeek`, a `draft`
  row *is* persisted — the document has to exist before lines and attachments can hang off it, so
  `ExpenseReportStatus.DRAFT` is a real, stored state, not a "no row" convention.
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
  new, resolved against the report — `ExpenseLineNotFoundError` if it isn't one of its own lines).
  A `line_id` present in both an update and `delete_line_ids` is deleted; deleting an id that isn't
  one of the report's own lines is a no-op.
- `DeleteExpenseReport` only works on a `draft` report (stricter than editing, which also allows
  `returned`); it cascades to the report's lines and attachments by `ON DELETE CASCADE`.
- Editability: `ExpenseReportNotEditableError` when the status isn't `draft`/`returned`;
  `ExpenseReportLockedError` when `locked_at` is set. Both gate line changes and attachment writes.

## Workflow

`ExpenseReportStatus`: `draft` → `submitted` → `approved`/`returned`, the same shape and rules as
`timesheets.TimesheetWeekStatus`: any manager may approve/return any report, never their own
(`ExpenseSelfReviewError`); `ReturnExpenseReport` works from either `submitted` or `approved` and
requires a non-empty `comment`, but is refused once the report is locked
(`ExpenseReportLockedError` — un-approving hours already sent to billing isn't allowed). Only
`ApproveExpenseReport` and `ReturnExpenseReport` are audited (`expense_report.approved` /
`expense_report.returned`, `entity_id` the report's own id) — creating, saving lines, submitting and
attachment writes are not, mirroring `timesheets`, which only audits the billing handoff itself.

`get_report` computes `can_edit`/`can_submit`/`can_review`/`is_locked` for the **viewer** passed in
— note that after `ReturnExpenseReport`/`ApproveExpenseReport` return their DTO, the viewer is the
reviewer, so that DTO's `can_edit` reflects the reviewer's own (lack of) editing rights, not the
report owner's; re-query with `viewer_id=<owner>` to see the owner's view. Advisory only, as with
`TimesheetService.get_week` — the router owns authorization.

## Attachments

- `ExpenseAttachment` metadata (`file_name`, `content_type`, `size_bytes`, `sha256`,
  `storage_key`, `uploaded_by_id`) lives in the database; the file itself lives on disk under
  `settings.attachment_dir`, managed by `storage.py: ExpenseAttachmentStorage` — modelled closely on
  `system.backup_service.BackupService` (dotfile-then-rename writes, a filename/key pattern that
  doubles as path-traversal validation). Attachments hang off the **report**, not a specific line.
- `AddExpenseAttachment(report_id, actor_id, file_name, content_type, content: bytes)` validates
  the report is editable and unlocked, then the content type/size
  (`AttachmentTypeNotAllowedError`/`AttachmentTooLargeError` — allowed types are the
  `ALLOWED_ATTACHMENT_CONTENT_TYPES` frozenset in `contracts.py`: PDF, JPEG, PNG, WebP, HEIC), then
  writes the file and the row. `content` is the already-fully-read request body — the HTTP layer
  (added later) is responsible for rejecting an oversize upload while streaming it in, so a huge
  file is never buffered here in full just to be rejected.
- `DeleteExpenseAttachment(attachment_id, actor_id)` requires the report to still be editable and
  unlocked; it unlinks the file before deleting the row.
- `GetAttachmentPath(attachment_id, viewer_id)` → `Path`, the same shape as
  `system.contracts.GetBackupPath`, for a router to hand to `FileResponse`. Raises
  `AttachmentNotFoundError` for an unknown id *or* a row whose file is missing from disk — the two
  cases are indistinguishable to a caller.
- **File writes are never transactional.** A command writes the file, then the row; a rollback
  after the file write orphans a file with no row. `time-reporting prune-attachments [--dry-run]`
  (via `ListAttachmentStorageKeys` + `ExpenseAttachmentStorage.prune_orphans`) sweeps files whose
  key no row references — the documented repair step, safe to run any time since a row is always
  written strictly after its file.

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
