# audit module

Owns one table, `audit_events` — an immutable, append-only log of administrative actions. Other
modules record an event by executing `audit.contracts.RecordAuditEvent` as a *nested* command from
within their own command handler (never from a router directly), so the event commits or rolls
back atomically with the change it describes: if anything later in that outer command still fails,
the whole transaction — including any `AuditEvent` row already flushed — rolls back with it (see
`test_audit_handlers.py` and the rollback tests next to `RemoveUser`/`SendProjectMonthToBilling`).

- `AuditEvent`: `occurred_at`, `actor_id` (`users.id`, `ON DELETE SET NULL` — a deleted actor's
  past events stay readable), `actor_name` (a *snapshot* taken at record time, resolved from
  `actor_id` via `users.contracts.GetUserById` inside `RecordAuditEventHandler` — callers never
  pass a name themselves), `action`, `entity_type`, `entity_id`, `summary`, `details` (JSONB, free
  form per action). `action`/`entity_type` are plain strings, not Postgres enums (contrast
  `NonWorkingDay.kind`), since the set of audited actions is expected to keep growing — see the
  comment on `AuditAction` in `contracts.py` for why that matters.
- `RecordAuditEvent(actor_id, action, entity_type, entity_id, summary, details=None)`: `actor_id`
  is `None` for a CLI-triggered command with no signed-in user (e.g. `create-admin`,
  `import-holidays`, a scheduled `time-reporting backup`) — the owning command's own contract
  carries an optional `actor_id`/`acting_user_id` field for this, defaulting to `None`, filled from
  `CurrentUserDep`/`AdminDep` only by the HTTP router.
- `ListAuditEvents(action, entity_type, entity_id, actor_id, occurred_from, occurred_to, limit,
  offset)`: every filter is optional and any-of-one; newest (`occurred_at`) first. `GET
  /admin/audit-events`, `AdminDep` only.

## Which commands are audited, and by whom

- `users.CreateUser` → `user.created`, `users.UpdateUser` → `user.roles_changed` (only when the
  new roles actually differ from the old) and/or `user.activated`/`user.deactivated` (only when
  `is_active` actually flips — a single `UpdateUser` call touching both can write both events),
  `users.ResetUserPassword` → `user.password_reset` (admin-only route; the separate
  self-service `ChangeOwnPassword` is never audited). All recorded by `users.handlers`, regardless
  of caller (HTTP or CLI) — see `users/CLAUDE.md`.
- `admin.RemoveUser`/`RemoveCustomer`/`RemoveProject` → `{user,customer,project}.deleted` on a
  permanent delete, and, **for customers and projects only**, `{customer,project}.archived` on the
  default archive branch. A user's archive branch does **not** get its own admin-level event: it's
  just `UpdateUser(is_active=False)` under the hood, which `users.handlers` already audits as
  `user.deactivated` — logging it again here would double-count the same action. See
  `admin/CLAUDE.md`.
- `timesheets.SendProjectMonthToBilling` → `billing_period.sent`,
  `timesheets.ReopenProjectBillingPeriod` → `billing_period.reopened`, both recorded by
  `timesheets.billing.BillingService`, `entity_id` is `"{project_id}:{period_start}"` (there is no
  single-UUID key for a billing period) with the project/customer/period names only in `summary`
  and, for the send, `details` — see `timesheets/CLAUDE.md`.
- `work_calendar.ImportPublicHolidays` → `calendar.public_holidays_imported`, `entity_id` is the
  year, recorded unconditionally (even when `added == 0`) — see `work_calendar/CLAUDE.md`.
- `system.CreateBackup` → `backup.created`, but **only** when `actor_id` is set, i.e. only for the
  "create backup now" API call — never for the CLI (`time-reporting backup`, run by hand or on the
  `backup`/`migrate` compose services' schedule), since logging every automatic scheduled backup
  would drown out real admin actions in the log. See `system/CLAUDE.md`.
- `expenses.ApproveExpenseReport` → `expense_report.approved`, `expenses.ReturnExpenseReport` →
  `expense_report.returned`, both recorded by `expenses.service.ExpenseService`, `entity_id` is
  the report's own id — see `expenses/CLAUDE.md`. Saving lines, submitting and creating a report
  are not audited (mirrors `timesheets`, which only audits the billing handoff, not day-to-day
  entry edits or submission).
- `company.UpdateCompanySettings`/`SetCompanyLogo`/`ClearCompanyLogo` → `company.updated`, recorded
  by `company.handlers`, only when something actually changed; `entity_type`/`entity_id` are both
  the fixed string `"company"` (there is no per-entity UUID — the settings row is a singleton).
  `details.fields` lists which fields changed (`"logo"` for a logo set/clear) — see
  `company/CLAUDE.md`.
- `invoices.CreateInvoiceDraft` → `invoice.created`, `invoices.DeleteInvoiceDraft` →
  `invoice.deleted`, both recorded by `invoices.service.InvoiceService`, `entity_id` is the
  invoice's own id — see `invoices/CLAUDE.md`. Saving header/line changes
  (`UpdateInvoiceDraft`) is not audited (mirrors `timesheets`/`expenses`, which only audit the
  billing handoff/review, not day-to-day edits).
