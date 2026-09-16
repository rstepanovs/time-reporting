# projects module

Owns `Project` (belongs to one `Customer`, `customer_id` immutable after creation), `ProjectMember` (a
plain user↔project link with no per-project role) and `ProjectBillingItem`.

Depends on: `customers.contracts` (`GetCustomersByIds`, active check), `users.contracts`
(`GetUsersByIds`, manager eligibility). `Project`/`ProjectMember` reference `customers.id` /
`users.id` by table name only, never by importing those modules' `models`.

## Projects and members

- `Project.normal_working_hours` (default 8, `0 < x ≤ 24`) is how many hours the timesheets module's
  weekly grid prefills per working day when it seeds a fresh draft week.
- `Project.manager_id` is the one responsible manager (nullable; an active user holding the
  `manager` access level, checked on set — `ProjectManagerNotFoundError` /
  `ProjectManagerNotEligibleError` otherwise), settable on `CreateProject`/`UpdateProject`
  (`null`/naming it in `clear_fields` clears it) and responsible for that project's timesheets team
  overview and billing handoff. `RemoveUserFromAllProjects` also clears it wherever the removed user
  was the manager.
- Project names are unique per customer, not globally.
- Creating a project, or reactivating one, requires its customer to currently be active, but
  archiving a customer does not cascade to its projects.
- Only active users can be added as members, and only to an active project; a member later
  deactivated stays listed (with `is_active=false`) rather than disappearing.
- Access follows customers: any authenticated user can read projects and members, `ManagerDep` is
  required to create/update projects and to add/remove members.
- `ListProjects` filters by `customer_id`, `member_id`, `manager_id` and a `search` substring
  against the name.
- `DeleteProject` (permanent) cascades to its members and billing items (FK `ON DELETE CASCADE`);
  it's blocked by time entries (FK violation mapped to `ProjectInUseError`).

## Billing items

`ProjectBillingItem`: the positions a project's invoices will be made of (normal/overtime/travel
hours, per diems, purchasing/other expenses), each with an immutable `unit` (`hour`, `day` or
`amount`) and, depending on that unit, a `unit_rate` or a `markup_percent` in the customer's
currency.

- Creating a project creates its six defaults (`DEFAULT_BILLING_ITEMS`, unpriced); further items
  are added directly to one project (there is no catalog shared across projects).
- Access mirrors projects: any authenticated user reads them, `ManagerDep` adds/edits/archives/
  restores, and permanently deleting one — blocked by a foreign key once time entries reference it,
  reported as `BillingItemInUseError` — is admin only, like every other permanent delete.

## Queries for the timesheets module

Exist so `timesheets` never joins into these tables directly:
- `GetProjectsByIds` / `GetProjectBillingItemsByIds` — batch lookups.
- `ListMemberProjectsWithBillingItems` — a user's active projects with their active billing items,
  one round trip.
- `ListManagedProjectsWithMembers` — active projects (one manager's, or every one when
  `manager_id=None`), each with its members, one round trip.
