# frontend projects/

Backend: `modules/projects`.

- `api.ts` — typed calls for all `/projects` endpoints plus `ProjectConflictError` (409) /
  `ProjectRuleError` (400, backend `detail` as the message) / `ProjectNotFoundError` (404), and for
  billing items `BillingItemConflictError` (409 name) / `BillingItemInUseError` (409 on delete, a
  different meaning than a project's own 409, mapped separately).
- `hooks.ts` — `projectKeys` + `useProjects`/`useProject`/`useProjectMembers`/
  `useProjectBillingItems` queries and `useCreateProject`/`useUpdateProject`/`useAddProjectMember`/
  `useRemoveProjectMember`/`useAddProjectBillingItem`/`useUpdateProjectBillingItem`/
  `useDeleteProjectBillingItem` mutations, all invalidating `projectKeys.all` on success.
- `ProjectFormModal.tsx` — shared create/edit form used by `pages/ProjectsPage.tsx`,
  `pages/ProjectDetailsPage.tsx` and `pages/admin/AdminProjectsPage.tsx`; an optional `onCreated`
  callback lets the admin page stay put instead of navigating to the new project. A searchable,
  clearable "Manager" picker (`useUserDirectory` with `roles: ["admin","project_manager"]`)
  sets/clears `manager_id`, keeping the current manager selectable even when a search narrows the
  directory past them.
- `BillingItemFormModal.tsx` — create/edit a billing item; the unit is locked once editing, and its
  rate/markup field swaps by unit.

## Pages

- `pages/ProjectsPage.tsx` has a Manager column and, for admins/project managers, a "Managed by me"
  filter (`manager_id` = the signed-in user).
- `pages/ProjectDetailsPage.tsx` shows the project's manager; its "Billing items" section is readable
  by anyone, editable by managers, and offers "Delete permanently" to admins only — the one write in
  this router that isn't `ManagerDep`.
