# frontend auth/

The web session (backend protocol: root `CLAUDE.md` "Auth" section).

- `api.ts` — current user, sign in/out, password change, typed errors.
- `hooks.ts` — `useCurrentUser`, `useAuthenticatedUser`, `useSignIn`, `useSignOut`,
  `useChangePassword`.
- `RequireAuth.tsx` — route guard redirecting to `/login` with the page to return to.
- Signing in or out drops every cached query, so no data leaks between users; explicit sign-out and
  password change navigate to `/login` with `flushSync`, so the next sign-in does not return to the
  page left behind.
- `roles.ts` — `hasRole(user, role)` plus `canManage`/`isAdmin`/`isAccountant`, all taking the user
  (levels are orthogonal, so a user can pass more than one); `roleLabels` covers the three levels,
  plus `EMPLOYEE_LABEL` for the implicit baseline every account has (never stored, so it isn't a
  `UserRole` value).
- `RequireRole.tsx` — renders its children only for a signed-in user holding any of the given roles,
  the plain not-found page otherwise (so a non-admin can't tell `/admin` exists); must be nested
  inside `RequireAuth`.
