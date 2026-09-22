# frontend expenses/

Backend: `modules/expenses` (workflow statuses, locking and attachment storage are documented
there).

## API layer

- `api.ts` — the caller's project/billing-item picker (`listExpenseOptions`), one month's reports
  (`listMyExpenseReports`, `userId` optional — another user needs manager), `createExpenseReport`,
  `getExpenseReport`, `saveExpenseReportLines` (one batch: changed lines plus `deleteLineIds`),
  `deleteExpenseReport` (draft only), `submitExpenseReport`/`approveExpenseReport`/
  `returnExpenseReport`, `listSubmittedExpenseReports` (`{ scope: "mine" | "all" }`, the manager's
  Expenses tab of `/approvals`), `addExpenseAttachment` (optional `lineId`, to upload a receipt
  already linked to a line) / `deleteExpenseAttachment` / `setExpenseAttachmentLine` (`{
  attachmentId, lineId: string | null }`, link or unlink an existing attachment) and
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
- Attachment mutations (including `useSetExpenseAttachmentLine`) only invalidate the owning
  report's `report(reportId)` — the list/summary views don't show attachments.

## Pages (`pages/ExpensesPage.tsx`, `pages/ExpenseReportPage.tsx`)

- `/expenses?month=YYYY-MM` — month navigation (the `HoursPage`/`TeamPage` pattern), a table of the
  month's reports (project, line count, total, status badge) linking to `/expenses/:reportId`, and
  a "New report" modal picking a project from `useExpenseOptions`.
- `/expenses/:reportId` — header with status, period, an "Approve"/"Return…" pair gated purely on
  the server's `can_review` (never a client-side "is this my own report" check —
  `ExpenseSelfReviewError`'s frontend counterpart, and the reason a manager viewing their own
  report under `company.allow_self_review` sees the buttons with no page code change at all: see
  `pages/ExpenseReportPage.test.tsx`'s self-review test), a "Delete" button for the owner's own
  `draft` report, and the return comment when `returned`; a "Sent to billing" alert when
  `is_locked`. `ExpenseLinesTable.tsx` holds a local draft (edits keyed by line id, plus a
  temp-id-keyed list for not-yet-saved rows) with an explicit Save/Discard and Submit (behind a
  confirming modal that auto-saves first, as `TimesheetGrid`'s does) — all gated on `can_edit`/
  `can_submit`, which the backend already reflects `is_locked` into, so the frontend never checks
  it separately when deciding whether a control is editable. A line with at least one linked
  attachment (`report.attachments.some(a => a.line_id === line.id)`) shows a 📎 next to its
  description, in both the editable and read-only cells — computed from `report.attachments`, not
  a field on the line DTO itself. `AttachmentsCard.tsx` is a Mantine `FileInput multiple` upload
  (each file uploaded immediately, one request per file, unlinked — `addExpenseAttachment` accepts
  a `lineId` but the upload control here never passes one) plus a list with size, a download link,
  a per-row `Select` (`useSetExpenseAttachmentLine`) picking which of the report's own lines the
  receipt substantiates — labeled `"<date> · <description>"` rather than just the description, so
  its display value never collides with `ExpenseLinesTable`'s own description field showing the
  same line's text elsewhere on the page — and per-row delete, all gated on `can_edit` too (the
  picker itself becomes read-only plain text when not `can_edit`).
- The "← Back to expenses" link on `/expenses/:reportId` guards against `ExpenseLinesTable`'s dirty
  state the same way `TimesheetPage` guards its own in-page navigation: a confirming modal instead
  of navigating away, offered by `ExpenseLinesTable`'s `onDirtyChange` callback bubbling up to the
  page. Browser/sidebar navigation away from the page is not guarded, matching `TimesheetPage`.
