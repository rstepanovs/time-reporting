# frontend auth/

The web session (backend protocol: root `CLAUDE.md` "Auth" section).

- `api.ts` — current user, sign in/out, password change, typed errors.
- `hooks.ts` — `useCurrentUser`, `useAuthenticatedUser`, `useSignIn`, `useSignOut`,
  `useChangePassword`.
- `RequireAuth.tsx` — route guard redirecting to `/login` with the page to return to.
- Signing in or out drops every cached query, so no data leaks between users; explicit sign-out and
  password change navigate to `/login` with `flushSync`, so the next sign-in does not return to the
  page left behind.
- `roles.ts` — `canManage` (admin or project manager) and `isAdmin`.
- `RequireRole.tsx` — renders its children only for a signed-in user with one of the given roles, the
  plain not-found page otherwise (so a non-admin can't tell `/admin` exists); must be nested inside
  `RequireAuth`.
