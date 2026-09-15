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
- `GET /users` is admin-only. `GET /users/directory` (`ManagerDep`) is a minimal, active-only,
  search-filtered user list for pickers (e.g. adding a project member or, via a repeated `role` query
  param backed by `ListUsers.roles`, a project's manager — any-of, only users holding `manager`).
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
