# users module

Owns the `User` entity, access levels (`UserRole`: `admin`, `manager`, `accountant`) and account
management (admin CRUD, `/users/me`, password change/reset). `token_version` is incremented by
password changes/resets, which invalidates existing JWTs (see the `auth` module).

- Levels are **orthogonal and combinable** (`users.roles`, a Postgres array column mapped to
  `frozenset[UserRole]` in DTOs/schemas — empty means a plain employee): `admin` is system
  administration (users, calendar, permanent deletion, system status, reopening billing periods);
  `manager` is customers/projects/members/billing items/approvals/team overview/sending to billing;
  `accountant` is a flag only for now (real permissions arrive with the invoices module). Every
  account is implicitly an "employee" — reports time, can be a project member, sees the personal
  dashboard — which is never stored since it can't be granted or taken away.
- `GET /users` (admin-only) and `GET /users/directory` (`ManagerDep`, minimal, active-only fields,
  for pickers such as adding a project member or, via the same param, a project's manager) both take
  a repeated `role` query param backed by `ListUsers.roles` — any-of, only users holding at least one
  of the given levels.
- Search goes through a repository-level helper built on the shared `db/queries.py:escape_like`;
  the roles filter uses the array column's `overlap()` (Postgres `&&`) for "holds any of".
- `GetUsersByIds` is the batch query other modules use for display data (names, emails, roles).
- Contracts consumed by `auth`: `GetUserCredentialsByEmail`, `RecordSuccessfulLogin`, ...
- Self-modification guard (`UpdateUser`, `SelfModificationError`): a user can never deactivate or
  delete themselves, and can never remove their own `admin` level (both would risk locking every
  admin out) — but may freely change their own `manager`/`accountant` levels.
- `DeleteUser` (permanent) rejects deleting yourself and fails with `UserInUseError` while the user is
  still a project member, or has time entries (the FK violation is mapped to `UserInUseError`).
  Deletion is orchestrated by the `admin` module (`RemoveUser`), which clears memberships and managed
  projects first via `projects.contracts.RemoveUserFromAllProjects`.
- `CreateUser`/`UpdateUser`/`ResetUserPassword` each record an `audit.contracts.RecordAuditEvent`
  (nested command) on success — `user.created`, `user.roles_changed` and/or
  `user.activated`/`user.deactivated` (only for a field that actually changed — one `UpdateUser`
  call can write both), and `user.password_reset` respectively. `CreateUser.actor_id` is optional
  (`None` for the CLI's `create-admin`/`seed-demo`); `ResetUserPassword.actor_id` and `UpdateUser`'s
  existing `acting_user_id` are not, since both are admin-only routes. `ChangeOwnPassword` is
  deliberately never audited (self-service, not "by admin"). See `audit/CLAUDE.md`.
