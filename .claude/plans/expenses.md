# Plan: expense reports — employees claim expenses, managers approve, receipts attached

## Context

Money spent on a project is recorded today as a cell in the weekly timesheet grid: a `TimeEntry`
against a `ProjectBillingItem` whose unit is `amount` (the `purchasing_expenses` /
`other_expenses` presets). That cell holds a number and an optional note — no vendor, no document
number, no receipt, and no approval of its own beyond the week it happens to sit in. An accountant
receiving a sent billing period gets a bare sum with nothing to substantiate it.

We add **expense reports**: a document an employee fills for one project and one calendar month,
with lines (date, billing item, amount, description, vendor, document number) and attached scans of
receipts and invoices. A manager approves or returns it, exactly as with a timesheet week, and a
project's month can only be sent to billing once both its weeks *and* its expense reports are
approved.

### Decisions confirmed with the user

1. **A document, in a new `expenses` module** — `ExpenseReport` → `ExpenseReportLine` →
   `ExpenseAttachment`, with its own submit/approve/return workflow mirroring timesheet weeks.
2. **One report per (employee, project, calendar month)**, so a report lines up exactly with a
   `ProjectBillingPeriod` and the "report straddling two months" problem never arises.
3. **Attachments are files on a named volume**, metadata in the database; `time-reporting backup`
   is extended to archive the attachment directory alongside the `pg_dump`, so the backup stays one
   operation and the existing runbook keeps working.
4. **Approval rights are the timesheets rule**: any admin or manager may approve any report (no
   self-approval), `/approvals` grows a second tab rather than a second permission model.
5. **`amount` billing items move out of the timesheet grid entirely** — money is claimed only
   through an expense report, with a receipt. `hour` and `day` (per diems) stay in the grid: a per
   diem is a count of days with no document behind it.
6. **Internal / non-billable projects are a separate plan.** This one stops at expense reports
   reaching billing; `Project.is_internal`, the company-cost report and its export come later.

### Design decisions (flag on review if wrong)

- **One-way module dependency: `timesheets` → `expenses.contracts`, never back.** `expenses` must
  not read `ProjectBillingPeriod` to know it is locked, or the two modules' contracts would
  reference each other — something the manager-dashboard plan deliberately avoided. Instead
  `SendProjectMonthToBilling` executes a nested `LockProjectMonthExpenseReports` (and reopening
  executes `UnlockProjectMonthExpenseReports`), so the lock is written into
  `ExpenseReport.locked_at` in the same transaction as the handoff. `expenses` depends only on
  `projects.contracts`, `users.contracts` and `audit.contracts`.
- **Currency is not stored on a line**, matching `ProjectBillingItem.unit_rate`: a project's
  currency is its customer's, reached through `ProjectDTO.customer.currency`.
- **A `draft` report is persisted**, unlike `TimesheetWeek` where "no row means draft" — the
  document has to exist before lines and files can hang off it.
- **File deletion is never transactional.** Upload writes the file, then inserts the row; delete
  removes the row and unlinks. Either half can be orphaned by a rollback, so a new
  `time-reporting prune-attachments` sweeps files with no row (and is the documented repair step).
- **Path-traversal defence is the backup service's proven one**: a storage key is validated against
  a strict regex before it is ever joined onto the attachment directory.

## Data model

New Postgres enum `expense_report_status` (`draft`, `submitted`, `approved`, `returned`).

`expense_reports` (`expenses/models.py: ExpenseReport`, `TimestampMixin`):

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `user_id` | uuid FK `users.id` `RESTRICT` | |
| `project_id` | uuid FK `projects.id` `RESTRICT` | |
| `period_start`, `period_end` | date | a calendar month's bounds; check `period_start <= period_end` |
| `status` | enum `expense_report_status` | |
| `submitted_at`, `reviewed_at` | timestamptz, nullable | |
| `reviewed_by_id` | uuid FK `users.id` `SET NULL`, nullable | |
| `return_comment` | text, nullable | |
| `locked_at` | timestamptz, nullable | set when the project's month is sent to billing |

Unique `(user_id, project_id, period_start)`; index `(project_id, period_start)` for the billing
scope query.

`expense_report_lines` (`TimestampMixin`):

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `report_id` | uuid FK `expense_reports.id` `CASCADE` | index |
| `billing_item_id` | uuid FK `project_billing_items.id` `RESTRICT` | must be an active `amount` item of the report's project |
| `expense_date` | date | must fall inside the report's period |
| `amount` | numeric(12, 2) | check `amount > 0` |
| `description` | varchar(255) | what was bought |
| `vendor` | varchar(255), nullable | |
| `document_no` | varchar(100), nullable | receipt / invoice number |
| `position` | int | display order, `max + 1` on add |

`expense_attachments` (`created_at` only, no `updated_at`): `id`, `report_id` FK `CASCADE` (index),
`file_name` varchar(255) (original, for display and the download filename), `content_type`
varchar(100), `size_bytes` int check `> 0`, `sha256` char(64), `storage_key` varchar(255) unique,
`uploaded_by_id` FK `users.id` `SET NULL` nullable. Attachments hang off the **report**, not a
line — per-line linking is out of scope.

`time_entries` gains a check constraint `unit <> 'amount'` as the third validation layer, once the
data migration below has emptied those rows.

## Contracts

**`projects.contracts`** — `ListMemberProjectsWithBillingItems` gains
`units: frozenset[BillingUnit] | None = None`, so `timesheets` asks for `{HOUR, DAY}` and
`expenses` for `{AMOUNT}` through the one existing membership query.

**`expenses.contracts`** — DTOs `ExpenseReportDTO` (project, user, period, status, `can_edit`,
`can_submit`, `can_review`, `is_locked`, totals, lines, attachments), `ExpenseReportLineDTO`,
`ExpenseAttachmentDTO`, `ExpenseReportSummaryDTO`, `ExpenseReportPageDTO`, `MonthExpenseTotalsDTO`.

Queries: `GetExpenseReport(report_id, viewer_id)`, `ListMyExpenseReports(user_id, year, month)`,
`ListExpenseOptions(user_id)` (projects with their active `amount` items),
`ListSubmittedExpenseReports(manager_id | None)`, `ListProjectMonthExpenseReports(project_id,
period_start)` (what `timesheets` reads for readiness and totals), `GetMonthExpenseTotals(user_id,
year, month)` (for the employee dashboard card), `GetAttachmentPath(attachment_id, viewer_id)` →
`Path`, following `system.contracts.GetBackupPath`.

Commands: `CreateExpenseReport`, `SaveExpenseReportLines(report_id, changes)` (one batch, one
transaction, like `SaveTimesheetWeek`), `DeleteExpenseReport`, `SubmitExpenseReport`,
`ApproveExpenseReport(reviewer_id)`, `ReturnExpenseReport(reviewer_id, comment)`,
`AddExpenseAttachment`, `DeleteExpenseAttachment`, and the two nested-only lock commands
`LockProjectMonthExpenseReports` / `UnlockProjectMonthExpenseReports`.

Errors (`ExpenseError` base): `ExpenseReportNotFoundError`, `ExpenseReportAlreadyExistsError`,
`ExpenseReportLockedError`, `ExpenseReportNotEditableError`, `InvalidExpenseStatusTransitionError`,
`ExpenseSelfReviewError`, `ExpenseReturnCommentRequiredError`, `ExpenseProjectClosedError`,
`ExpenseBillingItemNotFoundError`, `ExpenseDateOutsidePeriodError`, `AttachmentNotFoundError`,
`AttachmentTooLargeError`, `AttachmentTypeNotAllowedError`.

New settings (`core/config.py`): `attachment_dir: str = "attachments"`,
`attachment_max_bytes: int = 10_485_760`. Allowed content types are a frozenset constant in
`expenses/contracts.py` (PDF, JPEG, PNG, WebP, HEIC), not a setting.

## HTTP API

`APIRouter(prefix="/expenses", tags=["expenses"])`, all under `/api/v1`.

| Method | Path | Guard | Message |
|---|---|---|---|
| GET | `/reports?year=&month=&user_id=` | `CurrentUserDep`; another user needs manager | `ListMyExpenseReports` |
| POST | `/reports` `{project_id, year, month}` | `CurrentUserDep`, own only | `CreateExpenseReport` (201 / 409 exists) |
| GET | `/reports/{id}` | `CurrentUserDep`; owner, manager or accountant | `GetExpenseReport` |
| PUT | `/reports/{id}/lines` | `CurrentUserDep`, own + editable | `SaveExpenseReportLines` (400 rules / 409 locked) |
| DELETE | `/reports/{id}` | `CurrentUserDep`, own + draft | `DeleteExpenseReport` (204) |
| POST | `/reports/{id}/submit` | `CurrentUserDep`, own | `SubmitExpenseReport` (409 status) |
| POST | `/reports/{id}/approve` | `ManagerDep` | `ApproveExpenseReport` (403 self / 409 status) |
| POST | `/reports/{id}/return` | `ManagerDep` | `ReturnExpenseReport` |
| GET | `/submissions?scope=mine\|all` | `ManagerDep` | `ListSubmittedExpenseReports` |
| POST | `/reports/{id}/attachments` (multipart) | `CurrentUserDep`, own + editable | `AddExpenseAttachment` (201 / 413 / 415) |
| GET | `/attachments/{id}` | `CurrentUserDep`; owner, manager or accountant | `GetAttachmentPath` → `FileResponse` |
| DELETE | `/attachments/{id}` | `CurrentUserDep`, own + editable | `DeleteExpenseAttachment` (204) |
| GET | `/options` | `CurrentUserDep` | `ListExpenseOptions` |

Error mapping follows the timesheets router: rules → 400, missing → 404, cross-user / self-review →
403, status and lock conflicts → 409. `frontend/nginx.conf` needs `client_max_body_size 12m;` in
`location /api/` — nginx's 1 MB default would reject every upload in production.

---

## Tasks

Branch `feature/expenses` from `feature/admin-tools`. One reviewable commit per task
(`T<n>: ...`), each leaving `ruff`, `ruff format --check`, `mypy`, `pytest` (and for frontend tasks
`lint`, `typecheck`, `test`) green and updating the `CLAUDE.md` files it touches. First commit:
this plan as `.claude/plans/expenses.md`.

### T1 — projects: filter billing items by unit

- `ListMemberProjectsWithBillingItems.units: frozenset[BillingUnit] | None = None`; the repository
  applies it alongside the existing `is_active` filter. `None` keeps today's behavior.
- Tests in `test_projects_handlers.py`: `units={AMOUNT}` returns only expense items, a project
  whose every item is filtered out drops from the result.

### T2 — backend `expenses`: model, migration, report and lines

- `modules/expenses/{contracts,models,repository,service,handlers,module,__init__}.py` +
  `CLAUDE.md`, following `timesheets/`; register in `modules/registry.py` (after `timesheets`,
  before `admin`), import the models in `models/__init__.py`.
- Alembic revision creating the enum and the three tables (autogenerate, then check the enum's
  `downgrade` drop, as in `20260914_1150_..._create_project_billing_items_table.py`).
- `ExpenseService`: `create_report` (member of an active project, month bounds from year/month,
  unique conflict → `ExpenseReportAlreadyExistsError`), `get_report` (computes `can_edit` /
  `can_submit` / `can_review` / `is_locked` for the viewer, exactly as `TimesheetService.get_week`
  does — advisory only, the router still authorizes), `save_lines` (batch: validate every line's
  billing item is an active `amount` item of the project via
  `ListMemberProjectsWithBillingItems(units={AMOUNT})`, `expense_date` inside the period, then
  apply), `delete_report` (draft only).
- Tests `test_expenses_handlers.py`: create/duplicate, line add/update/delete in one batch, each
  rule error, a batch failing midway changes nothing, an archived project or lost membership makes
  the report read-only but still readable.

### T3 — backend `expenses`: workflow, locking, audit

- `submit_report` (`draft`/`returned` → `submitted`, clears review fields on resubmit),
  `approve_report` (`submitted` → `approved`, `ExpenseSelfReviewError`), `return_report`
  (`submitted`/`approved` → `returned`, non-empty comment, refused when `locked_at` is set).
- `LockProjectMonthExpenseReports` / `UnlockProjectMonthExpenseReports` — nested-only commands
  setting/clearing `locked_at` for every report of a project's month; `save_lines`, attachment
  writes and `return_report` all refuse a locked report with `ExpenseReportLockedError` (409).
- `ListSubmittedExpenseReports(manager_id)` — scoped through
  `projects.ListManagedProjectsWithMembers`, mirroring `ListSubmittedTimesheetWeeks`.
- New `AuditAction` members `expense_report.approved`, `expense_report.returned` (plain strings, no
  migration), recorded with a nested `RecordAuditEvent` from the service, as `billing.py` does.
- Tests `test_expenses_workflow_handlers.py`: every transition and every rejected transition, self
  review, lock blocks edit/attachments/return, unlock restores them, one audit event per approve
  and return, none when the command fails.

### T4 — backend `expenses`: attachment storage

- Settings `attachment_dir`, `attachment_max_bytes`; both added to `SystemConfigDTO`'s whitelist.
- `ExpenseAttachmentStorage` (`expenses/storage.py`), modelled on
  `modules/system/backup_service.py`: `save()` validates content type and size, computes the
  sha256, writes to `<dir>/<hex[:2]>/<hex><ext>` through a `.tmp` file plus `rename`, and returns
  the key; `path_for(key)` validates the key against
  `^[0-9a-f]{2}/[0-9a-f]{32}\.[a-z0-9]{1,8}$` before joining it, as `parse_backup_filename` does;
  `delete(key)` unlinks.
- `AddExpenseAttachment` / `DeleteExpenseAttachment` / `GetAttachmentPath` handlers, the last
  returning a `pathlib.Path` across the bus (the `GetBackupPath` precedent).
- `cli.py`: `time-reporting prune-attachments [--dry-run]` deleting files with no database row.
- `backend/Dockerfile`: pre-create `/var/lib/time-reporting/attachments` owned by `app`, as the
  backup directory already is.
- Tests `test_expense_attachments.py` with `tmp_path`: save/read back, oversize → 413 error, wrong
  type → 415 error, key validation rejects `../` and absolute paths, prune removes only orphans.

### T5 — backend `expenses`: HTTP API and infrastructure

- `expenses/schemas.py` (`<Thing>Response` with `from_attributes`, `<Command>Request` with
  `extra="forbid"`; other modules' DTOs re-declared with an `Expense` prefix, as timesheets does)
  and `expenses/router.py` per the table above; include it in `api/router.py`.
- Upload route takes `UploadFile` (`python-multipart` is already a dependency); reads at most
  `attachment_max_bytes + 1` bytes to reject oversize without buffering the whole body.
- `compose.yaml`: `attachments` named volume at `/var/lib/time-reporting/attachments` on `backend`
  and `backup`, `ATTACHMENT_DIR` in the `x-backend-env` anchor; `.env.example` gains
  `ATTACHMENT_MAX_BYTES`; `frontend/nginx.conf` gains `client_max_body_size 12m;`.
- Tests `test_expenses_api.py`: status codes and guards per route (another employee gets 403 on
  read and write, a manager reads but cannot edit, upload/download round-trip, 413/415), decimals
  round-trip as strings.

### T6 — backend `timesheets`: `amount` leaves the grid

- `ListTimesheetOptions` passes `units={HOUR, DAY}`; `save_week` rejects an `amount` item with a
  new, explicit `TimesheetUnitNotAllowedError` rather than the confusing "billing item not found".
- Alembic revision: for every distinct `(user_id, project_id, month)` with `amount` entries, insert
  an `expense_reports` row — `approved` with `locked_at = sent_at` when a `project_billing_periods`
  row already covers that project-month, else `draft` — plus one line per entry
  (`description = coalesce(note, billing item name)`, `position` by date); then delete those
  `time_entries` and add the `unit <> 'amount'` check constraint. Pure SQL, no app imports.
- `summary.py`: `MonthTimeSummaryDTO.expenses` now comes from
  `expenses.GetMonthExpenseTotals` instead of `amount` entries; the `_QuantityAccumulator`'s
  `add_amount` path stays for per diems only.
- Tests: an `amount` item is absent from `ListTimesheetOptions` and rejected by `SaveTimesheetWeek`;
  the month summary reports expenses from approved reports. Run the migration up and down by hand
  on the dev database and confirm the demo data survives the round trip.

### T7 — backend `timesheets`: billing readiness and the lock

- `billing_readiness` takes the month's expense reports too: in scope when there is at least one
  week **or** one report, blocked by any report not `approved`; `BillingPeriodNotReadyError` carries
  `blocking_reports` beside `blocking_weeks`.
- `BillingService.send_to_billing` fills `ProjectBillingPeriodDTO.expenses` from approved reports
  (via `ListProjectMonthExpenseReports`) and executes the nested
  `LockProjectMonthExpenseReports`; `reopen_period` executes the unlock.
- `TeamProjectDTO` / `GetTeamMonthOverview` surface the blocking report count so the manager sees
  why a month is not ready.
- `seed.py`: demo expense reports for the demo worker — one approved, one submitted (so the team
  page shows a real blocker), created only when the user has none, keeping seeding idempotent.
- Tests `test_timesheets_billing_handlers.py`: a month with only expenses is sendable; a submitted
  report blocks; sending locks every report of the month; reopening unlocks them;
  `test_module_boundaries.py` stays green (only `expenses.contracts` is imported).

### T8 — backend `system`: attachments in the backup

- `BackupService.create()` also writes `time-reporting-<ts>-<rev>-attachments.tar.gz` from
  `settings.attachment_dir` (stdlib `tarfile`, no new dependency) — the `system` module only ever
  sees a directory path, so no module boundary is crossed. `prune()` removes a backup's two files
  together; `parse_backup_filename` and `path_for` accept both; `BackupDTO` gains
  `attachments_size_bytes | None`.
- `time-reporting restore` extracts the archive over the attachment directory after the
  `pg_restore`, refusing if the archive is missing while the dump has attachment rows.
- `docs/operations.md`: what the second file is, restoring both, and `prune-attachments`.
- Tests: create produces both files, prune deletes pairs, restore extracts (subprocess stubbed as
  the existing backup tests do).

### T9 — frontend: `expenses` API layer

- `npm run gen:api` after T5.
- `frontend/src/expenses/{api.ts,hooks.ts,CLAUDE.md}`: types from `components["schemas"]`,
  `ExpenseRuleError` / `ExpenseConflictError` mapped from 400/403/404 and 409 like
  `timesheetAwareError`, plus `AttachmentTooLargeError` (413) and `AttachmentTypeError` (415);
  `expenseKeys` factory with an `allReports()` prefix for invalidation; `attachmentDownloadUrl(id)`
  as a plain string for an `<a href download>`, following `backupDownloadUrl`.
- Uploads go through `api.POST(..., { body: formData, bodySerializer: (b) => b })` — `openapi-fetch`
  passes `FormData` through and skips the JSON content type, so `api/client.ts` needs no change.
- `test/fixtures.ts`: `testExpenseReport`, `testExpenseReportPage`, `testExpenseAttachment`.

### T10 — frontend: employee expense pages

- Route `/expenses?month=YYYY-MM` (`pages/ExpensesPage.tsx`) and `/expenses/:reportId`
  (`pages/ExpenseReportPage.tsx`); nav item "Expenses" after "My hours" (note that
  `AppLayout.navItems` splices by index — the manager slice offsets shift).
- `ExpensesPage`: month navigation reusing `HoursPage`'s pattern, a table of the month's reports
  (project, lines, total, status badge) and a "New report" modal picking a project from
  `useExpenseOptions`.
- `ExpenseReportPage`: header with status, period and the return comment when returned;
  `expenses/ExpenseLinesTable.tsx` with a local draft and an explicit Save (the `TimesheetGrid`
  dirty-state pattern, including the discard-confirmation on navigation);
  `expenses/AttachmentsCard.tsx` with a Mantine `FileInput multiple` (no new dependency), a list
  with size and a download link, per-row delete; Submit behind a confirm modal that auto-saves
  first, as `TimesheetGrid` does. Buttons gate on the server's `can_edit` / `can_submit` /
  `is_locked`, never on a client-side role check.
- Tests: list renders and month navigation, create report, add/edit/remove lines and save, upload
  and delete an attachment, oversize error surfaced, locked report renders read-only.

### T11 — frontend: approval of expense reports

- `pages/ApprovalsPage.tsx` gains Mantine `Tabs` — "Timesheets" (today's table) and "Expenses"
  (`useSubmittedExpenseReports(scope)`), the existing scope toggle applying to both; each row links
  to `/expenses/:reportId`.
- `ExpenseReportPage` shows Approve / "Return…" for a manager when `can_review`, with the return
  comment modal and the `Alert`-style rule error handling from `TimesheetGrid`.
- `timesheets/ProjectBillingCard.tsx` and `pages/TeamPage.tsx` show the blocking expense-report
  count next to the blocking weeks; `DashboardPage`'s My-time section gains an expenses card only
  if it falls out cheaply — otherwise skip it.
- Tests: the tab lists submitted reports, a manager approves and returns, an employee sees no
  review actions, the billing card shows an expense blocker.

### T12 — billing period export (optional)

Invoicing does not exist, so a sent period currently reaches the accountant as a screen. A CSV is
the smallest real handoff and is cheap (stdlib `csv` + `StreamingResponse`).

- `GET /timesheets/billing-periods/{project_id}/{period_start}/export.csv` (`AdminDep`) — one row
  per time entry and per expense line: date, user, billing item, unit, quantity/amount, currency,
  description, vendor, document number.
- `/admin/billing` gains a per-row "CSV" download link (plain `<a href download>`).
- Tests: the route requires admin, the CSV carries both sources and a `Content-Disposition` name.

### T13 — documentation sweep

- Root `CLAUDE.md`: the `expenses` module in the module list, the `expenses/` frontend area, the new
  routes and nav entries, the `attachments` volume in the Docker section, and "remaining domain
  model (invoices)" left as it is.
- `expenses/CLAUDE.md` (backend and frontend), `timesheets/CLAUDE.md` (the `amount` items are gone,
  readiness now counts reports, the lock is pushed into `expenses`), `projects/CLAUDE.md` (the
  `units` filter), `system/CLAUDE.md` (attachments in the backup), `pages/CLAUDE.md`,
  `audit/CLAUDE.md` (the two new actions), `README.md`, `docs/operations.md`.

## Critical files

- Backend, new: `modules/expenses/*`, two Alembic revisions (schema in T2, data migration in T6).
- Backend, changed: `modules/projects/{contracts,repository,handlers}.py`,
  `modules/timesheets/{contracts,service,summary,team,billing,schemas,router}.py`,
  `modules/system/backup_service.py`, `modules/audit/contracts.py`, `core/config.py`, `cli.py`,
  `models/__init__.py`, `modules/registry.py`, `api/router.py`, `seed.py`, `backend/Dockerfile`.
- Frontend, new: `src/expenses/*`, `pages/ExpensesPage.tsx`, `pages/ExpenseReportPage.tsx`.
- Frontend, changed: `router.tsx`, `components/AppLayout.tsx`, `pages/ApprovalsPage.tsx`,
  `pages/TeamPage.tsx`, `timesheets/ProjectBillingCard.tsx`, `test/fixtures.ts`.
- Infra: `compose.yaml`, `.env.example`, `frontend/nginx.conf`, `docs/operations.md`.

## Verification

- Per task — backend: `uv run ruff check . && uv run ruff format --check . && uv run mypy &&
  uv run pytest` against a migrated Postgres (`docker compose up -d db`, `uv run alembic -c
  backend/alembic.ini upgrade head`). Frontend, in `frontend/`: `npm run lint && npm run typecheck
  && npm test && npm run build`.
- The T6 data migration gets its own manual round trip: `seed-demo`, book an `amount` entry in the
  grid on the current code, `alembic upgrade head`, confirm it turns into an expense report, then
  `alembic downgrade -1` and confirm the entry comes back.
- End to end in Docker (`docker compose up --build`, then `time-reporting seed-demo`): as the demo
  worker, create a report for a project and month, add lines, upload a PDF and a JPEG receipt,
  check that a 20 MB file is rejected with a clear message, submit; as the manager, see it in the
  Expenses tab of `/approvals`, return it with a comment, then approve the resubmitted one; confirm
  `/team` shows the project's month as Ready only once both the weeks and the report are approved,
  send it, and confirm the worker's report and grid are both read-only; as admin, reopen the period
  from `/admin/billing` and confirm the report becomes editable again, and that
  `/admin/audit` lists the approve, return, send and reopen events.
- Backups: create one from `/admin/backups`, confirm both files appear in the volume, then restore
  into a fresh database via the runbook and confirm the receipts download again.

## Out of scope

- Internal / non-billable projects, the company-cost report and its export (the agreed follow-up).
- Attaching a receipt to a specific line rather than the report.
- Foreign-currency expenses and conversion — a line is in the project's customer's currency.
- Mileage or per-kilometre rates, VAT rates and reclaim, approval limits by amount, multi-step
  approval, reimbursement or payout tracking.
- Restricting approval to the project's own manager (unchanged from timesheets).
- OCR or any automatic reading of an uploaded receipt; thumbnails and in-browser preview.
- An accountant-facing screen beyond the optional T12 export; real invoicing.
