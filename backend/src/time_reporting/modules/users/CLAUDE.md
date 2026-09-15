# users module

Owns the `User` entity, roles (`UserRole`: `admin`, `project_manager`, `worker`) and account
management (admin CRUD, `/users/me`, password change/reset). `token_version` is incremented by
password changes/resets, which invalidates existing JWTs (see the `auth` module).

- `GET /users` is admin-only. `GET /users/directory` (`ManagerDep`) is a minimal, active-only,
  search-filtered user list for pickers (e.g. adding a project member or, via a repeated `role` query
  param backed by `ListUsers.roles`, a project's manager — only admins/project managers).
- Search goes through a repository-level helper built on the shared `db/queries.py:escape_like`.
- `GetUsersByIds` is the batch query other modules use for display data (names, emails).
- Contracts consumed by `auth`: `GetUserCredentialsByEmail`, `RecordSuccessfulLogin`, ...
- `DeleteUser` (permanent) rejects deleting yourself and fails with `UserInUseError` while the user is
  still a project member, or has time entries (the FK violation is mapped to `UserInUseError`).
  Deletion is orchestrated by the `admin` module (`RemoveUser`), which clears memberships and managed
  projects first via `projects.contracts.RemoveUserFromAllProjects`.
