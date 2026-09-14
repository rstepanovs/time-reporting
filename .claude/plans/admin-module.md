# Plan: admin module — archive or permanently delete users, customers and projects (backend + frontend)

## Context

Administrators can already create and edit users (`/users`, admin only), customers and projects
(`/customers`, `/projects`, `ManagerDep`). Archiving exists only as `PATCH ... {"is_active": false}`,
and nothing can be deleted: customers and projects are documented as "never deleted", and users only
get deactivated. A record added by mistake (a duplicate customer, a user with a wrong email) stays
in the database forever.

We add an **admin** feature, backend and frontend:

- **Remove** a user, customer or project. Archiving is the default; a **"Delete permanently"**
  checkbox deletes the row instead, for records created by mistake.
- An **Administration** section in the web client (`/admin/users`, `/admin/customers`,
  `/admin/projects`) where an administrator lists, creates, edits, archives/restores and deletes
  all three entities.

### Decisions confirmed with the user

- **Deletion rule: blocked by business dependencies, soft cascade for plain links.** A permanent
  delete is refused (409, with the reason) while business data references the record: a customer
  that has projects (active or archived), and later anything time entries or invoices reference.
  Plain link rows are removed along with the record: a user's project memberships, a project's
  members.
- **Access:** permanent deletion is admin only. Managers (`admin`, `project_manager`) keep archiving
  customers and projects through the existing `PATCH` endpoints. The new `/admin` API and the web
  section are admin only.
- **Frontend:** a separate `/admin` section, visible and routable only for administrators. The
  existing `/projects` pages stay as they are.

### Design principles

- **Deleting stays inside the module that owns the table.** Owning modules get small primitive
  commands (`DeleteUser`, `DeleteCustomer`, `DeleteProject`, `RemoveUserFromAllProjects`). Only a
  module may touch its own `models`/`repository`, so the module boundary rule stays intact.
- **`modules/admin/` owns no tables.** It orchestrates: it works out what a removal would affect
  (impact queries) and runs archive or delete as one bus transaction, calling other modules only
  through their `contracts.py`.
- **Foreign keys are the safety net.** The existing `ON DELETE RESTRICT` constraints
  (`projects.customer_id`, `project_members.user_id`, and future time entries/invoices) block a
  delete even if an impact check races with a concurrent insert. A repository turns a
  foreign-key violation into a module `...InUseError`, and the admin module maps that to
  `RemovalBlockedError` (409).
- **No schema changes and no migration.** `project_members.project_id` is already
  `ON DELETE CASCADE`. User memberships are deleted explicitly before the user.

## Target layout

```
backend/src/time_reporting/modules/
  users/      contracts.py (+DeleteUser, UserInUseError)  repository.py (+delete)  service.py  handlers.py  module.py
  customers/  contracts.py (+DeleteCustomer, CustomerInUseError, ListCustomers.search)  repository.py  service.py  handlers.py  module.py  router.py
  projects/   contracts.py (+DeleteProject, RemoveUserFromAllProjects, ProjectInUseError)  repository.py  service.py  handlers.py  module.py
  admin/                    # NEW: orchestration only, no models.py
    contracts.py            # RemovalOutcome, RemovalBlockerKind, RemovalEffectKind, DTOs, commands, queries, RemovalBlockedError
    service.py              # AdminRemovalService(bus)
    handlers.py  module.py
    schemas.py  router.py   # prefix /admin, AdminDep on every route
  registry.py               # + admin_module.register(registry)

frontend/src/
  auth/roles.ts             # + isAdmin(role)
  auth/RequireRole.tsx      # NEW: route guard by role
  admin/                    # NEW
    api.ts  hooks.ts        # removal impact + remove calls, RemovalBlockedError
    RemoveEntityModal.tsx   # shared archive / "Delete permanently" dialog
  users/     api.ts hooks.ts (+ admin CRUD)  UserFormModal.tsx  ResetPasswordModal.tsx
  customers/ api.ts hooks.ts (+ CRUD, search)  CustomerFormModal.tsx
  projects/  ProjectFormModal.tsx (+ onCreated)
  pages/admin/              # NEW: AdminUsersPage, AdminCustomersPage, AdminProjectsPage
  router.tsx  components/AppLayout.tsx
```

## Admin API (all `AdminDep`)

| Method | Path | Message | Result |
|---|---|---|---|
| GET | `/admin/users/{user_id}/removal-impact` | `GetUserRemovalImpact` | `RemovalImpactResponse` / 404 |
| DELETE | `/admin/users/{user_id}?permanent=false` | `RemoveUser` | `RemovalResponse` / 404 / 400 self / 409 blocked |
| GET | `/admin/customers/{customer_id}/removal-impact` | `GetCustomerRemovalImpact` | `RemovalImpactResponse` / 404 |
| DELETE | `/admin/customers/{customer_id}?permanent=false` | `RemoveCustomer` | `RemovalResponse` / 404 / 409 blocked |
| GET | `/admin/projects/{project_id}/removal-impact` | `GetProjectRemovalImpact` | `RemovalImpactResponse` / 404 |
| DELETE | `/admin/projects/{project_id}?permanent=false` | `RemoveProject` | `RemovalResponse` / 404 / 409 blocked |

- `RemovalImpactResponse`: `is_active`, `can_delete_permanently`,
  `blockers: [{kind, count}]` (what prevents a permanent delete), and
  `effects: [{kind, count}]` (what a permanent delete also removes).
- `RemovalResponse`: `outcome: "archived" | "deleted"`.
- A 409 carries `detail = {"message": str, "blockers": [{kind, count}]}`.
- Archiving an already archived record is a no-op that returns `outcome="archived"`. A permanent
  delete works whether or not the record is archived.
- Create, edit and restore keep using the existing endpoints (`POST`/`PATCH /users`,
  `/customers`, `/projects`, and `PUT /users/{id}/password`). The admin module does not duplicate
  them.

### Removal rules per entity

| Entity | Archive (`permanent=false`) | Permanent delete: blockers | Permanent delete: also removes |
|---|---|---|---|
| User | `UpdateUser(is_active=False)`, not allowed on yourself | `self` (acting admin), future time entries (FK) | the user's project memberships |
| Customer | `UpdateCustomer(is_active=False)` | `projects` (any, active or archived), future invoices (FK) | nothing |
| Project | `UpdateProject(is_active=False)` | future time entries (FK) | project members (FK cascade) |

Archiving a customer still does not cascade to its projects (current behaviour stays).

---

## Tasks

Suggested branch: `feature/admin-module`. Each task is one reviewable commit and must leave
`ruff`, `mypy`, `pytest` (and for frontend tasks `lint`, `typecheck`, `test`) green.

Dependency order: **B1 → B2 → B3 → B4** (B5 can go in any time before F4) → **F1 → F2 → F3/F4/F5** → **D1**.

### B1. Primitive delete commands in the owning modules

Goal: each module can hard-delete its own rows and reports an FK conflict as a domain error. No HTTP
changes.

- **users**
  - `contracts.py`: `DeleteUser(Command[None])` with `user_id` and `acting_user_id`, plus
    `UserInUseError(user_id)`.
  - `service.py`: `delete_user` raises `UserNotFoundError`, and raises `SelfModificationError`
    when `user_id == acting_user_id` (extend its message to cover deletion, or add
    `SelfDeletionError`).
  - `repository.py`: `delete(user)` runs `session.delete` + `flush`. On `IntegrityError` it checks
    for an FK violation (SQLSTATE `23503`, or the constraint name in `exc.orig`, as the existing
    repositories do) and raises `UserInUseError`.
- **customers**
  - `contracts.py`: `DeleteCustomer(customer_id)` and `CustomerInUseError(customer_id)`.
  - `repository.py`/`service.py`: delete, mapping the FK violation from `projects.customer_id`.
  - Update the `UpdateCustomer` docstring: the rule is no longer "never deleted"; permanent deletion
    of an unreferenced customer goes through the admin module.
- **projects**
  - `contracts.py`: `DeleteProject(project_id)`, `ProjectInUseError(project_id)`, and
    `RemoveUserFromAllProjects(user_id) -> int`, which returns the number of memberships removed.
  - `repository.py`: `ProjectRepository.delete(project)` (members go through the FK cascade; map
    FK violations to `ProjectInUseError`) and `ProjectMemberRepository.delete_all_for_user(user_id)`,
    a bulk `delete(ProjectMember).where(...)` returning `rowcount`.
  - Update the `UpdateProject` docstring and the `models.py` comment "archived rather than deleted".
- Register the new handlers in each `module.py`.
- Tests (extend `test_users_handlers.py`, `test_customers_handlers.py`, `test_projects_handlers.py`):
  - a user with no references is deleted, `GetUserById` returns `None`, and deleting yourself fails;
    a user who is still a project member → `UserInUseError`; the same user after
    `RemoveUserFromAllProjects` → deleted;
  - a customer with a project → `CustomerInUseError`; a customer without projects → deleted;
  - a project with members → deleted and its `project_members` rows are gone;
    `RemoveUserFromAllProjects` returns the correct count;
  - not found → `...NotFoundError` for every command.

### B2. Admin module: contracts and removal-impact queries

Goal: the admin module exists, is registered, and can say what removing a record would do.

- `modules/admin/contracts.py`:
  - `RemovalOutcome(StrEnum)`: `ARCHIVED`, `DELETED`.
  - `RemovalBlockerKind(StrEnum)`: `SELF`, `PROJECTS`. Leave room for `TIME_ENTRIES`/`INVOICES`
    when those modules exist.
  - `RemovalEffectKind(StrEnum)`: `PROJECT_MEMBERSHIPS`, `PROJECT_MEMBERS`.
  - DTOs: `RemovalCountDTO(kind, count)` and
    `RemovalImpactDTO(is_active, can_delete_permanently, blockers, effects)`.
  - Queries: `GetUserRemovalImpact(user_id, acting_user_id)`,
    `GetCustomerRemovalImpact(customer_id)`, `GetProjectRemovalImpact(project_id)`, each
    `-> RemovalImpactDTO | None` (`None` means not found).
  - Exceptions: `AdminError`, `RemovalTargetNotFoundError`,
    `RemovalBlockedError(blockers: tuple[RemovalCountDTO, ...])`, and `SelfRemovalError`.
- `service.py`: `AdminRemovalService(bus)` computes impact only from existing contract queries,
  with no new cross-module queries:
  - user: `GetUserById`; memberships = `ListProjects(member_id=..., include_inactive=True, limit=1).total`;
    `SELF` blocker when the target is the acting admin;
  - customer: `GetCustomerById`; projects = `ListProjects(customer_id=..., include_inactive=True, limit=1).total`;
  - project: `GetProjectById`; members = `len(ListProjectMembers(...))`.
- `handlers.py`/`module.py`: register the handlers, and add `admin_module.register` to
  `modules/registry.py`.
- `test_module_boundaries.py` needs no change, but confirm it passes with the new module, which
  imports only `users/customers/projects.contracts` and `auth.dependencies`.
- Tests `test_admin_handlers.py`: impact for each entity, with and without dependencies, the self
  case, and unknown id → `None`.

### B3. Admin module: removal commands (archive or delete)

Goal: one command per entity that archives by default or deletes permanently, atomically.

- `contracts.py`: `RemoveUser(user_id, acting_user_id, permanent: bool = False)`,
  `RemoveCustomer(customer_id, permanent=False)`, `RemoveProject(project_id, permanent=False)`,
  each `-> RemovalOutcome`.
- `service.py`:
  - `permanent=False` → the owning module's update command with `is_active=False`, skipped if the
    record is already archived. Map `UserNotFoundError`/`CustomerNotFoundError`/
    `ProjectNotFoundError` → `RemovalTargetNotFoundError`, and `SelfModificationError` →
    `SelfRemovalError`.
  - `permanent=True` → compute the impact (B2). Any blocker raises `RemovalBlockedError` without
    changing anything. Otherwise:
    - user: `execute(RemoveUserFromAllProjects)` then `execute(DeleteUser)`;
    - customer: `execute(DeleteCustomer)`;
    - project: `execute(DeleteProject)`.
  - These are nested commands under the outer `RemoveX` command, so the bus commits once, or rolls
    back everything, including removed memberships, if the delete fails.
  - A late `...InUseError` (race with a concurrent insert) → `RemovalBlockedError` with the matching
    blocker kind (`count` may be unknown; use `0` and document it).
  - Log permanent deletions at `INFO` (entity, id, acting admin id). A persistent audit log is out
    of scope.
- Tests (extend `test_admin_handlers.py`):
  - archive sets `is_active=False` and is idempotent;
  - permanently deleting a user who is a member of 2 projects removes the memberships and the user;
  - a customer with an archived project → `RemovalBlockedError` and nothing changes;
  - a project with members → deleted;
  - self removal is rejected in both modes;
  - rollback check: make `DeleteUser` fail after `RemoveUserFromAllProjects` (a user referenced by
    a fake FK row, or a patched handler) and assert the memberships are still there.

### B4. Admin HTTP API

Goal: expose B2/B3 under `/api/v1/admin`.

- `schemas.py`: `RemovalCountResponse`, `RemovalImpactResponse` and `RemovalResponse`, all
  `from_attributes`.
- `router.py` (prefix `/admin`, tag `admin`, `AdminDep` on every route), following the table
  above. Map errors: `RemovalTargetNotFoundError` → 404, `SelfRemovalError` → 400,
  `RemovalBlockedError` → 409 with a structured `detail`. Declare `responses=` for OpenAPI like
  the existing routers do.
- Include the router in `api/router.py`.
- Tests `test_admin_api.py`:
  - worker and project manager → 403 on every route, anonymous → 401;
  - `DELETE` without `permanent` archives the record;
  - `?permanent=true` deletes it (a later `GET` returns 404);
  - 409 body shape for a customer with projects;
  - 400 when an admin removes themselves;
  - cookie-authenticated `DELETE` without `X-Requested-With` → 403 (the CSRF rule covers the new
    routes).

### B5. Search in the customers list

Goal: `/admin/customers` needs search. `CLAUDE.md` already claims customers listing supports it,
but `ListCustomers` has no `search` field.

- `ListCustomers.search: str | None`: a case-insensitive substring match against `name` and
  `legal_name` via `db/queries.py:escape_like`, applied in both `get_page` and `count` (factor out a
  `_filtered` helper like `UserRepository`).
- `GET /customers?search=` (`max_length=255`).
- Tests: handler and API search, including LIKE wildcards (`%`, `_`) matched literally.

### F1. Admin routing, role guard and navigation

Depends on B4/B5 being merged locally: run `npm run gen:api` against the running backend.

- `auth/roles.ts`: `isAdmin(role)`.
- `auth/RequireRole.tsx`: `<RequireRole roles={["admin"]} />` renders `<Outlet />` for allowed
  roles and `NotFoundPage` otherwise, so the section's existence is not revealed.
- `router.tsx`: under `AppLayout`, add
  `{ path: "admin", element: <RequireRole roles={["admin"]} />, children: [...] }` with
  `index → <Navigate to="users" replace />`, `users`, `customers`, `projects`. Use placeholder
  pages until F3–F5.
- `components/AppLayout.tsx`: an "Administration" `NavLink` group (children Users / Customers /
  Projects) shown only when `isAdmin(user.role)`. The active state uses the `/admin` prefix.
- Tests:
  - `AppLayout.test.tsx`: the group is visible for an admin, hidden for a project manager and a
    worker;
  - a new `admin/AdminRoutes.test.tsx`: a non-admin opening `/admin/users` sees the not-found page,
    an admin gets redirected from `/admin` to `/admin/users`.
- Add an `testAdmin` fixture to `test/fixtures.ts`.

### F2. Shared removal dialog

- `admin/api.ts`:
  - `getRemovalImpact(entity, id)` and `removeEntity(entity, id, { permanent })`, where `entity` is
    `"users" | "customers" | "projects"`;
  - `RemovalBlockedError` (409, carries `blockers`), `RemovalRuleError` (400, backend message) and
    `RemovalNotFoundError` (404).
- `admin/hooks.ts`:
  - `adminKeys.impact(entity, id)`;
  - `useRemovalImpact(entity, id, { enabled })`, which fetches only while the dialog is open;
  - `useRemoveEntity(entity)`, which on success invalidates the affected caches: users → user keys
    and `projectKeys.all` (member lists); customers → customer keys and `projectKeys.all`;
    projects → `projectKeys.all`.
- `admin/RemoveEntityModal.tsx`, props `entity`, `id`, `name`, `opened`, `onClose`, `onRemoved?`:
  - loads the impact; if the record is already archived, the archive option is hidden and the
    dialog only offers permanent deletion;
  - a **"Delete permanently"** `Checkbox`, unchecked by default. It is disabled when
    `can_delete_permanently` is false, with the blockers listed as a reason (e.g. "Customer has 3
    projects. Delete or reassign them first." / "You cannot delete your own account.");
  - when checked, a red warning lists the effects ("Also removes 2 project memberships. This cannot
    be undone.") and the confirm button changes from "Archive" to a red "Delete permanently";
  - on success, a notification ("… archived" / "… deleted") and `onClose`; on 409, the blockers are
    shown inline and the impact refetched.
- Tests `admin/RemoveEntityModal.test.tsx` (mock `@/admin/api`):
  - the default action calls `removeEntity(..., { permanent: false })`;
  - checking the box calls `{ permanent: true }`;
  - the checkbox is disabled and the reason shown when there are blockers;
  - the effects warning is visible only when checked;
  - a 409 from the server shows the blockers.

### F3. Users administration page (`/admin/users`)

- `users/api.ts`: `listUsers({search, includeInactive, limit, offset})`, `createUser`, `updateUser`
  and `resetUserPassword`, plus `UserEmailConflictError` (409) and `UserRuleError` (400, e.g. self
  modification).
- `users/hooks.ts`: `userKeys` (`all`, `list`, `directory`) and `useUsers`, `useCreateUser`,
  `useUpdateUser`, `useResetUserPassword`, all invalidating `userKeys.all`. Move
  `useUserDirectory` onto `userKeys.directory`.
- `users/UserFormModal.tsx`:
  - create mode: name, email, role `Select` (`roleLabels`), and password (min length from
    `auth/passwords.ts`);
  - edit mode: name, email, role, sending only changed fields;
  - a 409 shows as an email field error.
- `users/ResetPasswordModal.tsx`: new password + confirmation, with a note that the user's sessions
  end.
- `pages/admin/AdminUsersPage.tsx`:
  - a debounced search, a "Show inactive" switch and pagination (same pattern as `ProjectsPage`);
  - table: name, email, role badge, status (Active/Inactive), last login;
  - row actions `Menu`: Edit, Reset password, Restore (only when inactive, `PATCH is_active=true`)
    and Remove… (`RemoveEntityModal`);
  - Remove and role change are disabled on the current admin's own row.
- Tests `pages/admin/AdminUsersPage.test.tsx`:
  - list rendering and search;
  - create user happy path and 409;
  - edit sends only changed fields;
  - restore;
  - the remove menu opens the dialog;
  - own row actions are disabled.

### F4. Customers administration page (`/admin/customers`)

- `customers/api.ts`: `listCustomers` gains `search`; add `getCustomer`, `createCustomer`,
  `updateCustomer` and `CustomerConflictError` (409).
- `customers/hooks.ts`: `customerKeys` (if missing), `useCreateCustomer` and `useUpdateCustomer`,
  invalidating `customerKeys.all` and `projectKeys.all` (a project shows its customer's name and
  status).
- `customers/CustomerFormModal.tsx` (create/edit), built with `@mantine/form`:
  - main: name, legal name, tax id, billing email, notes;
  - billing address: line1, line2, city, region, postal code, and country as a 2-letter code
    (upper-cased);
  - billing: interval count + unit `Select` + anchor date (`DatePickerInput` from
    `@mantine/dates`), currency as a 3-letter code (upper-cased), payment terms (0–365);
  - in edit mode, a cleared optional text field is sent as `null`, which the backend
    `clear_fields` expects, and unchanged fields are omitted;
  - a 409 shows as a name field error.
- `pages/admin/AdminCustomersPage.tsx`:
  - search, a "Show archived" switch and pagination;
  - table: name, legal name, currency, billing period ("every 1 month"), status;
  - row actions: Edit, Restore, Remove…;
  - a "New customer" button.
- Tests:
  - form validation (required fields, country/currency format);
  - create happy path;
  - edit sends `null` for a cleared field;
  - archived rows show Restore;
  - remove opens the dialog.

### F5. Projects administration page (`/admin/projects`)

- `projects/ProjectFormModal.tsx`: add an optional `onCreated(project)` prop. When given, it is
  called instead of navigating to `/projects/:id`, so the admin page stays in place. Existing
  behaviour is unchanged when the prop is omitted.
- `pages/admin/AdminProjectsPage.tsx`:
  - customer filter, search, a "Show archived" switch and pagination (reuse `useProjects`);
  - table: name (link to `/projects/:id` for members), customer, status;
  - row actions: Edit (`ProjectFormModal mode="edit"`), Restore (`PATCH is_active=true`; show the
    backend 400 when the customer is archived) and Remove….
- Tests:
  - list and filters;
  - create via the modal stays on `/admin/projects`;
  - restore under an archived customer shows the rule error;
  - remove opens the dialog;
  - the existing `ProjectsPage.test.tsx` still passes (navigation after create).

### D1. Docs, seed check and final verification

- `CLAUDE.md`:
  - describe the **admin** module (orchestration only, no tables, `/admin` routes, removal rules,
    `RemovalBlockedError`);
  - replace "never deleted, only archived" for customers/projects/users with the new rule (archive
    by default; permanent delete by an admin only when unreferenced; memberships removed along
    with the record);
  - note the `search` parameter on customers;
  - frontend: `admin/`, `RequireRole`, the `/admin` routes, and the new `users/`/`customers/`
    CRUD files.
- `README.md`: a short "Administration" section, if the README lists features.
- `seed.py`: no data changes. Confirm `test_seed.py` still passes, since demo projects/customers can
  now be deleted in tests.
- Verification (from the repository root, Postgres running and migrated):
  1. `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest`
  2. `cd frontend && npm run gen:api && npm run lint && npm run typecheck && npm test && npm run build`
     (`schema.d.ts` must be committed regenerated)
  3. Manual smoke test (`uv run time-reporting seed-demo`, dev servers):
     - as the demo admin, create a customer and archive it via Remove;
     - create a customer by mistake and delete it permanently;
     - try to delete a customer with projects (checkbox disabled, reason shown);
     - add a user to a project, then delete the user permanently (the membership disappears from
       the project page);
     - confirm you cannot remove yourself;
     - sign in as the project manager and a worker: no Administration menu, `/admin/users` → not
       found, `DELETE /api/v1/admin/...` → 403.

## Out of scope

- A persistent audit log of deletions (INFO logs only).
- Reassigning projects to another customer before deleting (`customer_id` stays immutable).
- Bulk actions.
- Removal blockers for time entries and invoices: those modules don't exist yet. When they are
  added, their FKs must be `ON DELETE RESTRICT` and their counts added to the admin impact queries.
