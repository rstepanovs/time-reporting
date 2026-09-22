# admin module

Owns no tables — it orchestrates archiving or permanently deleting a user, customer or project by
calling the owning module's commands, reached only through `users.contracts` /
`customers.contracts` / `projects.contracts` (plus `timesheets.contracts.CountTimeEntries`,
`invoices.contracts.CountInvoices` and `audit.contracts.RecordAuditEvent`, the latter for every
branch of `RemoveCustomer`/`RemoveProject` and the permanent-delete branch of `RemoveUser` — see
`audit/CLAUDE.md` for exactly which action each records and why a user's *archive* branch does not
also get its own event here).

- `RemoveUser` / `RemoveCustomer` / `RemoveProject` (`AdminDep` only, under `/admin`, each carrying
  an `acting_user_id` filled by the router from the caller for the self-removal guard and, since
  T9, the audit actor too) default to archiving (the same
  `UpdateUser`/`UpdateCustomer`/`UpdateProject` a manager already uses) and, with `permanent=True`,
  permanently delete once nothing blocks it: a customer with any project, or a user deleting
  themselves, raise `RemovalBlockedError` / `SelfRemovalError` (409 / 400) without changing
  anything.
- Deleting a user first removes its project memberships (`RemoveUserFromAllProjects`) so the
  `ON DELETE RESTRICT` foreign key doesn't get in the way, and clears `manager_id` on projects they
  manage; deleting a project cascades to its members and billing items.
- `GetUserRemovalImpact` / `GetCustomerRemovalImpact` / `GetProjectRemovalImpact` report what a
  permanent delete would affect (`blockers`, `effects`) before the user confirms; they're built only
  from each module's own contract queries (`ListProjects`, `ListProjectMembers`,
  `ListProjectBillingItems`, `CountTimeEntries`, `CountInvoices`), never new cross-module queries.
  - A project's impact always lists a `project_billing_items` effect, since every project has at
    least its six defaults.
  - A user or project with any time entries gets a `time_entries` blocker (`RemovalBlockerKind`);
    deleting either maps the resulting FK violation to `UserInUseError` / `ProjectInUseError` the
    same way an existing membership or project already did.
  - A customer referenced by any invoice (any status, via `invoices.CountInvoices`) gets an
    `invoices` blocker — permanently deleting a customer is blocked the same way whether it's the
    `customers.CustomerInUseError`-guarded projects check or this one that fires first.
  - A user managing any projects gets a `managed_projects` effect (`RemovalEffectKind`).
- A same-outer-command failure (e.g. the delete itself fails after memberships were already removed)
  rolls back the whole `RemoveUser` command, per the bus's transaction rule.
- Archiving stays reachable directly through the owning module's existing `PATCH` endpoint too
  (`ManagerDep`); only the permanent-delete path is admin-only.
