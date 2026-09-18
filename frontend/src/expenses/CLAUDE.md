# frontend expenses/

Backend: `modules/expenses` (workflow statuses, locking and attachment storage are documented
there).

## API layer

- `api.ts` — the caller's project/billing-item picker (`listExpenseOptions`), one month's reports
  (`listMyExpenseReports`, `userId` optional — another user needs manager), `createExpenseReport`,
  `getExpenseReport`, `saveExpenseReportLines` (one batch: changed lines plus `deleteLineIds`),
  `deleteExpenseReport` (draft only), `submitExpenseReport`/`approveExpenseReport`/
  `returnExpenseReport`, `listSubmittedExpenseReports` (`{ scope: "mine" | "all" }`, the manager's
  Expenses tab of `/approvals`), `addExpenseAttachment`/`deleteExpenseAttachment` and
  `attachmentDownloadUrl(id)` (a plain relative URL for an `<a href download>`, never fetched
  through `api` — following `system/api.ts`'s `backupDownloadUrl`).
- Errors: `ExpenseRuleError` (400/403/404 — a rule was violated, or the backend's generic message
  for a body-less 403), `ExpenseConflictError` (409 — the report's status or lock doesn't allow
  this), `AttachmentTooLargeError` (413) and `AttachmentTypeError` (415), the last two only from
  `addExpenseAttachment`. All carry the backend's `detail` as the message where present.
- Uploads: `addExpenseAttachment` builds a `File`/`file_name` pair and passes a custom
  `bodySerializer` that turns it into a real `FormData` — `openapi-fetch` then skips the JSON
  content type and sends it as-is, so `api/client.ts` needs no multipart-specific change. The
  generated `file` field is typed `string` (OpenAPI has no distinct binary type), so the actual
  `File` is cast, not converted.

## Query keys and cache rules (`hooks.ts`)

- `expenseKeys.allReports()` is a shared prefix over both the list query (`reports(userId, year,
  month)`) and the single-report query (`report(reportId)`) — every mutation that changes a report
  invalidates this prefix, so the month list and any other open report page pick it up, in addition
  to writing the mutated report straight into its own `report(reportId)` cache entry.
- `expenseKeys.allSubmissions()` is the same pattern for `submissions(scope)`, invalidated by
  submit/approve/return so every cached scope in `/approvals` drops the row.
- Attachment mutations only invalidate the owning report's `report(reportId)` — the list/summary
  views don't show attachments.

## Pages (`pages/ExpensesPage.tsx`, `pages/ExpenseReportPage.tsx`)

- `/expenses?month=YYYY-MM` — month navigation (the `HoursPage`/`TeamPage` pattern), a table of the
  month's reports (project, line count, total, status badge) linking to `/expenses/:reportId`, and
  a "New report" modal picking a project from `useExpenseOptions`.
- `/expenses/:reportId` — header with status, period and (when `returned`) the return comment;
  `ExpenseLinesTable.tsx` holds a local draft with an explicit Save (the `TimesheetGrid` dirty-state
  pattern: discard-confirmation on navigating away with unsaved changes); `AttachmentsCard.tsx` is a
  Mantine `FileInput multiple` upload plus a list with size, a download link and per-row delete.
  Submit/Approve/"Return…" gate on the server's `can_submit`/`can_review` (Submit auto-saves first,
  as `TimesheetGrid`'s does), never on a client-side role check; every editable control also checks
  `is_locked` since a report can be locked without changing status (sent-to-billing).
