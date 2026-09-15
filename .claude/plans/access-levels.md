# Plan: composable access levels (admin / manager / accountant) on top of "every user is an employee"

## Context

Today a user has exactly one **role** — `users.role` enum `admin | project_manager | worker` — and
the roles are nested (`admin ⊃ project_manager ⊃ worker`). The concept changes:

- Roles become **access levels** a user can **combine** (e.g. someone is both a manager and an
  admin).
- **Every user is an employee** and reports time like any worker, so "employee" is the baseline
  every account has, not a level that can be granted or taken away (`worker` is renamed to
  `employee` in the UI).
- A new **accountant** level is introduced.
- The dashboard (and navigation) is assembled from the levels the user has.

### Decisions confirmed with the user

1. **Levels are orthogonal.** `admin` = system administration only (users, calendar, permanent
   deletion, system status, reopening billing periods). `manager` = customers, projects, members,
   billing items, approvals, team overview, sending to billing. Admin no longer implies manager.
2. **Employee is implicit.** Every account reports time, can be a project member and sees the
   personal dashboard. Only `admin`, `manager`, `accountant` are stored; an empty set = a plain
   employee.
3. **Accountant is only a flag for now.** It exists in the model, API, user form, labels, and gets
   a placeholder dashboard section. Real permissions come with the invoices module.
4. **Admin-only exceptions are simplified:**
   - nobody approves or returns their own week, not even an admin;
   - the "All" scope on `/approvals`, `/team` and the dashboard is available to every manager;
   - reopening a sent billing period stays admin-only.

### Derived decisions (follow from the above, flag on review if wrong)

- **Sending to billing:** any manager may send any project, the same rule as approvals, which any
  manager can do for any week. `NotProjectManagerError` goes away. Before, it was "the project's
  `manager_id` or an admin"; with orthogonal admin, keeping that rule would leave projects without
  a `manager_id` impossible to send.
- **Project manager eligibility:** `Project.manager_id` must be an active user with the `manager`
  level.
- **Viewing another user's timesheet or hours** (`?user=`): `manager` level only.
- **Self-modification guard:** a user can't remove their own `admin` level or deactivate
  themselves (prevents admin lock-out), but may change their own `manager`/`accountant` levels.
- **Reopen UI:** the "Reopen" button stays on `/team`, which requires `manager`, so in the UI only
  an `admin`+`manager` user sees it. The endpoint itself is `AdminDep`. When the accountant gets
  real permissions, reopening likely moves to their billing view.
- **Data migration:**

  | old `role` | new levels |
  | --- | --- |
  | `admin` | `{admin, manager}` (keeps today's effective rights) |
  | `project_manager` | `{manager}` |
  | `worker` | `{}` |

- **`create-admin` CLI** grants `{admin, manager}`, so a fresh install's first user can set up
  customers and projects straight away.

## Target model

- `users.contracts.UserRole(StrEnum)`: `ADMIN = "admin"`, `MANAGER = "manager"`,
  `ACCOUNTANT = "accountant"`. The name stays `UserRole` to keep churn down; no `employee` value.
- Storage: `users.roles` is a Postgres `ARRAY(Enum(user_role))`, `NOT NULL`, server default `'{}'`.
  An array rather than a join table: the set is tiny and always read with the user,
  `ListUsers.roles` filtering maps to `User.roles.overlap(...)`, and no extra round trip per request
  in `get_current_user`.
- DTOs, schemas and the API use `roles: frozenset[UserRole]` in Python and `roles: UserRole[]` in
  JSON, replacing `role`. This covers `UserDTO`, `CreateUser`, `UpdateUser` (`roles: ... | None`),
  `ProjectMemberDTO`, and the users/projects response schemas. `GET /users/directory?role=`
  (repeatable) keeps its meaning: "has any of".
- Guards (`auth/dependencies.py`):
  - `require_roles(*roles)` admits a user holding **any** of them;
  - `AdminDep` = `admin`, `ManagerDep` = `manager` only, new `AccountantDep` = `accountant` (defined
    for later, unused for now);
  - `CurrentUserDep` is the "employee" guard.
- Frontend `auth/roles.ts`: `hasRole(user, role)`, `canManage(user)`, `isAdmin(user)`,
  `isAccountant(user)` take the user, not a role. `roleLabels` covers the three levels, plus an
  `EMPLOYEE_LABEL`. `RequireRole roles={[...]}` means "has any of".

## Tasks

T1–T4 must land in one PR: the schema change breaks backend and frontend typecheck at once. Each
task is one commit on a new branch off `main` (e.g. `feature/access-levels`). Each task updates the
`CLAUDE.md` next to the code it touches.

### T1 — Backend: multi-level user model, migration, guards (mechanical, semantics-preserving)

- `modules/users/contracts.py`:
  - new `UserRole` values;
  - `roles` on `UserDTO`, `CreateUser`, `UpdateUser`;
  - `ListUsers.roles` = any-of.
- `modules/users/models.py`: `roles: Mapped[frozenset[UserRole]]` / `list[UserRole]` via
  `ARRAY(Enum(UserRole, name="user_role", values_callable=...))`.
- Alembic migration (hand-edited, since autogenerate can't express this):
  1. create the new enum type;
  2. add `roles` with default `'{}'`;
  3. backfill with the mapping above;
  4. drop `role` and the old type, rename the new type to `user_role`.

  Downgrade maps back: `admin ∈ roles` → `admin`, `manager` → `project_manager`, else `worker`.
- `users/repository.py` (`overlap` filter), `service.py`, `handlers.py`, `schemas.py`, `router.py`:
  - `role` → `roles`;
  - self-guard as described (own `admin` removal or self-deactivation → `SelfModificationError`,
    message updated);
  - validate no duplicates.
- `auth/dependencies.py`: any-of `require_roles`, `ManagerDep` = manager only, `AccountantDep`.
- Call-site replacements (`x.role == ADMIN` → `ADMIN in x.roles`, `role in {ADMIN, PM}` →
  `MANAGER in roles`):
  - `projects/service.py` (`_ELIGIBLE_MANAGER_ROLES`), `projects/contracts.py`, `handlers.py`,
    `schemas.py` (member `roles`);
  - `timesheets/router.py` (`_VIEW_ANY_ROLES`, scope check), `service.py` (`_MANAGER_ROLES`,
    `can_review`, `_ensure_not_self_review`), `billing.py` — admin exceptions kept for now, removed
    in T2;
  - `cli.py` (`create-admin` → `{ADMIN, MANAGER}`).
- Tests:
  - `tests/conftest.py` + `tests/support.py`: `make_user(roles=frozenset())` replaces
    `role=UserRole.WORKER`; add small constants `ADMIN = frozenset({UserRole.ADMIN,
    UserRole.MANAGER})`, `MANAGER`, `EMPLOYEE` so existing tests translate 1:1;
  - update `test_users_*`, `test_auth_*`, `test_projects_*`, `test_timesheets_*`, `test_admin_*`,
    `test_cli.py`, `test_work_calendar_api.py`, `test_customers_api.py`;
  - new tests: combined levels pass both guards; a user holding only `admin` is rejected by
    `ManagerDep`; directory any-of filter; self-guard cases; migration is exercised by CI's
    `alembic upgrade head`.
- Docs: `users/CLAUDE.md`, `auth/CLAUDE.md`, `projects/CLAUDE.md`, root `CLAUDE.md` (module list,
  Auth section).

### T2 — Backend: simplified workflow rules

- `timesheets/service.py`:
  - `can_review` = viewer has `manager`, the week is reviewable, `viewer_id != user_id`, not locked;
  - `_ensure_not_self_review` rejects every self-review.
- `timesheets/router.py`: drop the `scope == "all"` admin check on `/team/{year}/{month}` (and its
  403 response doc); `_resolve_target_user` = manager only.
- `timesheets/billing.py`: any manager may send (the router's `ManagerDep` is the check); remove
  `NotProjectManagerError` from contracts, router and tests. Reopen stays `AdminDep`.
- Tests: an admin+manager can't approve their own week; a manager can use `scope=all` on team; a
  non-project manager can send to billing; a user holding only `admin` can't approve or view
  others' weeks.
- Docs: `timesheets/CLAUDE.md` (workflow, billing handoff, team overview sections).

### T3 — Seed & CLI data

- `seed.py`: `DemoUser.roles`. Demo users (all share `demo-password`):

  | user | email | levels |
  | --- | --- | --- |
  | Alice Admin | `admin@example.com` | `{admin}` |
  | Mark Manager | `manager@example.com` | `{manager}` |
  | Emma Employee | `employee@example.com` | `{}` |
  | Andy Accountant | `accountant@example.com` | `{accountant}` |
  | Max Multi | `lead@example.com` | `{admin, manager}` |

  The combined user shows off combined levels. `worker@example.com` is left untouched in existing
  dev databases, since seeding is idempotent by email.
- Everyone is an employee, so drop `DEMO_TIME_ENTRY_ROLES` and seed time entries for every demo
  user who is a project member. Add the new users as members of the demo projects.
- `_reviewer_id` picks a `manager`-level user other than the week's owner. Every non-reviewer's
  weeks go through submit/approve (replacing the `role is WORKER` check).
- Tests: `test_seed.py`, `test_cli.py`.
- Docs: `.claude/skills/seed-test-data/SKILL.md`, `README.md` (demo user list).

### T4 — Frontend: follow the new API (no new UX yet)

- `npm run gen:api`, then `auth/api.ts`/`users/api.ts` types.
- `auth/roles.ts`: user-based helpers as above. `RequireRole` = any-of. `router.tsx`:
  `/approvals`, `/team` → `["manager"]`; `/admin/*` → `["admin"]`.
- Call sites:
  - `AppLayout.tsx`: account menu shows level badges or "Employee"; Approvals/Team for managers;
    Administration for admins;
  - `ProjectsPage.tsx`, `ProjectDetailsPage.tsx`: manage = manager, permanent delete = admin; the
    members table's "Role" column → levels badges;
  - `TimesheetPage.tsx` (`canPickUser` = manager), `TeamPage.tsx` (Reopen = admin);
  - `TeamScopeToggle.tsx`: shown for every manager (it's only rendered in manager views anyway, so
    effectively always);
  - `ProjectFormModal.tsx` (manager picker `roles: ["manager"]`), `users/hooks.ts`.
- `test/fixtures.ts`: `testManager` (`["manager"]`), `testEmployee` (`[]`, renamed from
  `testWorker`), `testAdmin` (`["admin","manager"]`), plus `testAdminOnly` (`["admin"]`).
- Update affected `*.test.tsx`; add a test that a user holding only admin sees Administration but
  not Approvals/Team.
- Minimal `UserFormModal.tsx` compile fix only (a real multi-select comes in T5).
- Docs: `auth/CLAUDE.md`, `users/CLAUDE.md`, `test/CLAUDE.md` (fixtures), root `CLAUDE.md`
  (AppLayout, router, RequireRole wording).

### T5 — Frontend: managing access levels

- `users/UserFormModal.tsx`: replace the Role `Select` with a `Checkbox.Group` "Access levels"
  (Administrator / Manager / Accountant, each with a one-line description), with a static note
  that every user is an employee and reports time. Edit sends `roles` only when changed. The
  checkbox for your own Administrator level is disabled, mirroring the backend guard.
- `pages/admin/AdminUsersPage.tsx`: "Access levels" column with badges (or "Employee"); optional
  level filter (the directory/list any-of filter is already on the backend; add `roles` to
  `GET /users` if not already exposed).
- `users/api.ts`: `UserRuleError` message for the new self-guard.
- Tests: `AdminUsersPage.test.tsx` (create with multiple levels, edit, own-admin checkbox disabled).

### T6 — Frontend: dashboard assembled from levels

`pages/DashboardPage.tsx` becomes a list of sections, each gated by a level:

| Section | Shown to | Content |
| --- | --- | --- |
| **My time** | everyone | today's two grids (Quick actions, month cards, weekly chart/projects, My projects) |
| **My team** | `manager` | existing Team timesheets / Project billing / Staff cards + scope toggle |
| **Billing** | `accountant` | `timesheets/AccountantPlaceholderCard.tsx` (or `billing/`), a `DashboardCard` explaining that invoicing is coming, no data calls |
| **Administration** | `admin` | `admin/AdminShortcutsCard.tsx` with links to Users, Customers, Projects, Calendar, System status (link-only, no new backend) |

- Section order for combined users: My time → My team → Billing → Administration.
- `DashboardPage.test.tsx`: one case per level plus a combined case (admin+manager sees My team and
  Administration; admin-only sees only My time + Administration; accountant sees Billing).
- Docs: `timesheets/CLAUDE.md` (dashboard section), `admin/CLAUDE.md`, `pages/CLAUDE.md`, root
  `CLAUDE.md` (DashboardPage description).

### T7 — Wording sweep

- Replace "worker" with "employee" in user-facing strings and doc comments. Examples:
  - `QuickActionsCard.tsx`, `TimesheetGrid.tsx` ("Tell the employee…"), `ProjectFormModal.tsx`
    description;
  - `timesheets/contracts.py` / `summary.py` docstrings ("employee dashboard"),
    `core/config.py` comment;
  - `grep -rniE "worker|project.manager"` over `backend/src`, `frontend/src`, `*.md`, excluding
    `core/passwords.py`'s thread "worker".
- Old `.claude/plans/*.md` are historical and stay unchanged.

## Verification

- Backend, from the repo root with `docker compose up -d db`:
  1. `uv run alembic -c backend/alembic.ini upgrade head` on a DB that already holds seeded
     old-style users; then check `SELECT email, roles FROM users` matches the mapping.
  2. `downgrade -1` / `upgrade head` round-trip.
  3. `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`.
- Frontend, from `frontend/`: `npm run gen:api` (backend running), `npm run lint`,
  `npm run typecheck`, `npm test`, `npm run build`.
- Manual (`seed-demo`, `npm run dev`), sign in as:
  - `employee@` → only My time, no Approvals/Team/Administration, `/admin` → not found;
  - `manager@` → My team with a working "All" toggle, can approve others but not own week, can send
    any ready project;
  - `admin@` (admin only) → My time + Administration, `/approvals` and `/team` → not found;
  - `lead@` → all manager + admin sections, sees "Reopen" on a sent period on `/team`, cannot
    approve own week;
  - `accountant@` → My time + Billing placeholder;
  - in Admin → Users, grant/revoke levels for another user; own Administrator checkbox is disabled.
