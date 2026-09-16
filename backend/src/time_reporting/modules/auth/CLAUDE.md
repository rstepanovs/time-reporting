# auth module

Owns JWT issuing/validation and login (`POST /auth/login` bearer token, `POST`/`DELETE /auth/session`
cookie — protocol details in the root `CLAUDE.md` "Auth" section).

- Reaches user data only through `users.contracts` messages (`GetUserCredentialsByEmail`,
  `RecordSuccessfulLogin`, ...) — it never imports `users.models` or `users.repository`.
- `auth/dependencies.py` (`CurrentUserDep`, `require_roles`, `AdminDep`, `ManagerDep`,
  `AccountantDep`) is the one exception to the "only `contracts.py`" import rule: every protected
  router depends on it directly. `require_roles(*roles)` admits a user holding **any** of them —
  levels are orthogonal, so an admin+manager passes both `AdminDep` and `ManagerDep`, and an
  admin-only user fails `ManagerDep`. `CurrentUserDep` alone is the implicit "employee" guard: every
  authenticated user, regardless of levels.
- Levels and `is_active` are re-read from the database on every request (via the token's `sub`), not
  trusted from the token, so deactivation/level/password changes take effect immediately — enforced
  by comparing the token's `ver` claim against the user's current `token_version`, which password
  changes/resets increment.
