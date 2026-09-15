# frontend users/

Backend: `modules/users`.

- `api.ts` — typed calls for the user endpoints, plus `UserEmailConflictError` (409),
  `UserRuleError` (400) and `UserNotFoundError` (404).
- `hooks.ts` — `userKeys` + `useUsers`, `useCreateUser`, `useUpdateUser`, `useResetUserPassword`,
  and `useUserDirectory` (backed by `GET /users/directory`; takes an optional `roles` array to narrow
  the picker to any-of, e.g. to managers for a project's manager field).
- `createUser`/`updateUser` take `roles: UserRole[]` (an empty array is a plain employee).
- `UserFormModal.tsx` + `ResetPasswordModal.tsx` — the forms `pages/admin/AdminUsersPage.tsx` uses.
  `UserFormModal`'s single `Select` is a stand-in for `roles` (it can only set/clear one level at a
  time, via a synthetic `"employee"` option) until T5 replaces it with a checkbox group.
