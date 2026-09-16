# frontend users/

Backend: `modules/users`.

- `api.ts` — typed calls for the user endpoints, plus `UserEmailConflictError` (409),
  `UserRuleError` (400, e.g. an admin trying to remove their own `admin` level or deactivate
  themselves) and `UserNotFoundError` (404).
- `hooks.ts` — `userKeys` + `useUsers` (its `roles` param narrows `GET /users` to any-of, for
  `AdminUsersPage`'s level filter), `useCreateUser`, `useUpdateUser`, `useResetUserPassword`, and
  `useUserDirectory` (backed by `GET /users/directory`, same any-of `roles` narrowing, e.g. to
  managers for a project's manager field).
- `createUser`/`updateUser` take `roles: UserRole[]` (an empty array is a plain employee).
- `UserFormModal.tsx` + `ResetPasswordModal.tsx` — the forms `pages/admin/AdminUsersPage.tsx` uses.
  `UserFormModal`'s "Access levels" is a `Checkbox.Group` (Administrator/Manager/Accountant, each
  with a one-line description, plus a static note that every user is an employee regardless) backed
  by `roles: UserRole[]`; editing sends `roles` only when the set actually changed (order-independent
  comparison). The Administrator checkbox is disabled when editing your own account, mirroring the
  backend's self-guard — `manager`/`accountant` stay freely editable on your own row.
