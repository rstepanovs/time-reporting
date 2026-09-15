# frontend users/

Backend: `modules/users`.

- `api.ts` — typed calls for the user endpoints, plus `UserEmailConflictError` (409),
  `UserRuleError` (400) and `UserNotFoundError` (404).
- `hooks.ts` — `userKeys` + `useUsers`, `useCreateUser`, `useUpdateUser`, `useResetUserPassword`,
  and `useUserDirectory` (backed by `GET /users/directory`; takes an optional `roles` array to narrow
  the picker, e.g. to admins/project managers for a project's manager field).
- `UserFormModal.tsx` + `ResetPasswordModal.tsx` — the forms `pages/admin/AdminUsersPage.tsx` uses.
