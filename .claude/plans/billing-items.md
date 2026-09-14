# Plan: project billing items — the positions an invoice is made of (backend + frontend)

## Context

Projects exist, but nothing describes *what* is billed on them. An invoice will consist of
positions such as normal working hours, overtime, travel time, per diems and reimbursed expenses,
each priced differently per project. Time entries and invoices (not built yet) need a stable thing
to reference.

We add **billing items**: per-project positions with a unit and a price. Every new project gets a
set of default items; managers can add further items, set rates, rename and archive them.

### Decisions confirmed with the user

- **Name:** "billing items" (`ProjectBillingItem`, `/projects/{id}/billing-items`, UI "Billing
  items"). Invoice rows will later be called *invoice lines*.
- **Ownership: items live only inside a project.** There is no global catalog. A fixed list of
  defaults (in code) is copied into every project when it is created; custom items are added to one
  project directly. The same default in two projects is two independent rows, linked only by their
  `preset` value.
- **Pricing: unit + rate per project.** Each item has a unit:
  - `hour` — normal / overtime / travel time; priced by `unit_rate` per hour;
  - `day` — per diems; priced by `unit_rate` per day;
  - `amount` — purchasing / other expenses; the actual amount is entered with each expense later,
    optionally increased by `markup_percent`.
  Rates are in the customer's currency (not stored on the item).
- **Access:** any authenticated user reads items; `ManagerDep` (admin, project manager) adds,
  edits, archives and restores them. Permanent deletion is admin only, like every other permanent
  delete. (The "admin manages the catalog" option does not apply, since there is no catalog.)

### Default items

| `preset` | Name | Unit |
|---|---|---|
| `normal_hours` | Normal working hours | `hour` |
| `overtime_hours` | Overtime working hours | `hour` |
| `travel_time` | Travel time | `hour` |
| `per_diem` | Per diems | `day` |
| `purchasing_expenses` | Purchasing expenses | `amount` |
| `other_expenses` | Other expenses | `amount` |

Defaults are created without rates (`unit_rate = NULL`, "not set" in the UI); invoicing will later
require a rate for `hour`/`day` items that have billed quantities.

### Design principles

- **Billing items belong to the projects module**, next to `ProjectMember`: they have no life
  outside a project, creating a project must create them in the same transaction, and a separate
  module would need a projects ⇄ billing-items contract cycle. Future modules (time entries,
  invoices) reach them via `projects.contracts`.
- **`unit` is immutable** after creation (time entries will store quantities in that unit). Name,
  description, pricing and `is_active` are editable, also for defaults.
- **Archive by default.** Archived items stay listed for existing data but can't be chosen for new
  entries (later). Permanent delete is blocked by a foreign key once time entries reference an
  item (`ON DELETE RESTRICT` from their table), reported as `BillingItemInUseError` (409).
- **Pricing is validated in three layers:** Pydantic (shape), service (rule errors with a clear
  message), DB check constraints (safety net).

## Data model

New table `project_billing_items` (`projects/models.py: ProjectBillingItem`, `TimestampMixin`):

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `project_id` | uuid FK `projects.id` `ON DELETE CASCADE` | immutable; lookups use the unique `(project_id, name)` index |
| `preset` | enum `billing_item_preset`, nullable | set only for defaults; immutable |
| `name` | varchar(255) | `uq_project_billing_items_project_id_name` |
| `description` | text, nullable | printed on the invoice line later |
| `unit` | enum `billing_unit` (`hour`, `day`, `amount`) | immutable |
| `unit_rate` | numeric(12, 2), nullable | only for `hour`/`day` |
| `markup_percent` | numeric(6, 2), nullable | only for `amount` |
| `position` | int | display/invoice order; defaults 1..6, new items `max + 1`; not editable yet |
| `is_active` | bool, default true | |

Check constraints: `unit_rate >= 0`, `markup_percent >= 0`,
`unit_rate IS NULL OR unit <> 'amount'`, `markup_percent IS NULL OR unit = 'amount'`.
Unique `(project_id, preset)` (NULLs are distinct in Postgres, so custom items are unaffected).

## HTTP API (projects router)

| Method | Path | Guard | Message | Result |
|---|---|---|---|---|
| GET | `/projects/{project_id}/billing-items?include_inactive=false` | `CurrentUserDep` | `ListProjectBillingItems` | `list[ProjectBillingItemResponse]` / 404 |
| POST | `/projects/{project_id}/billing-items` | `ManagerDep` | `AddProjectBillingItem` | 201 / 404 / 400 archived project or invalid pricing / 409 name |
| PATCH | `/projects/{project_id}/billing-items/{item_id}` | `ManagerDep` | `UpdateProjectBillingItem` | 200 / 404 / 400 invalid pricing / 409 name |
| DELETE | `/projects/{project_id}/billing-items/{item_id}` | `AdminDep` | `DeleteProjectBillingItem` | 204 / 404 / 409 in use |

- `ProjectBillingItemResponse`: `id`, `project_id`, `preset | null`, `name`, `description`, `unit`,
  `unit_rate | null`, `markup_percent | null`, `position`, `is_active`, `created_at`, `updated_at`.
  Decimals are serialized as JSON strings (Pydantic default) to avoid float rounding.
- Create body: `name`, `unit`, optional `description`, `unit_rate`, `markup_percent`
  (`extra="forbid"`).
- Update body: `name`, `description`, `unit_rate`, `markup_percent`, `is_active`, all optional;
  `null` clears `description`/`unit_rate`/`markup_percent` (via `clear_fields`, like
  `UpdateProject`), and is rejected for `name`/`is_active`. `unit`, `preset` are not accepted.
- Restoring (`is_active: true`) an item of an archived project is rejected (400), mirroring members.
- `ProjectCustomerResponse` gains `currency`, so the UI can show rates without fetching the customer.

---

## Tasks

Suggested branch: `feature/billing-items` (from `feature/admin-module`, which B4/F2 build on). Each
task is one reviewable commit and must leave `ruff`, `mypy`, `pytest` (and for frontend tasks
`lint`, `typecheck`, `test`) green.

Dependency order: **B1 → B2 → B3 → B4** → **F1 → F2** → **D1**.

### B1. Model, migration and default items on project creation

- `projects/contracts.py`: `BillingUnit(StrEnum)`, `BillingItemPreset(StrEnum)`, and
  `DEFAULT_BILLING_ITEMS: tuple[DefaultBillingItem, ...]` (preset, name, unit — the table above).
- `projects/models.py`: `ProjectBillingItem` with the constraints above.
- `projects/repository.py`: `ProjectBillingItemRepository.add_all`. The query and write methods
  (`list_for_project`, `get`, `next_position`, `save`, `delete`) arrive with B2, which uses them.
- `ProjectService.create_project` adds the defaults (positions 1..6) in the same flush.
- Alembic revision (autogenerate + hand edit): creates both enums and the table, then a data step
  inserting the six defaults for every existing project (`gen_random_uuid()`, Postgres 17). The
  downgrade drops the table and enums.
- Tests (`test_projects_handlers.py`): `CreateProject` yields the six defaults in order with no
  rates; a DB check constraint rejects a rate on an `amount` item; deleting a project removes its
  items. The migration keeps its own literal copy of the defaults (migrations must not import app
  code) and is verified by hand: upgrade on existing projects, downgrade drops table and enums.

### B2. Contracts, service and handlers

- `ProjectBillingItemDTO`, `ListProjectBillingItems(project_id, include_inactive=False)`,
  `AddProjectBillingItem`, `UpdateProjectBillingItem` (`None` = unchanged,
  `clear_fields: frozenset[Literal["description", "unit_rate", "markup_percent"]]`),
  `DeleteProjectBillingItem`.
- Exceptions: `BillingItemNotFoundError(project_id, item_id)`,
  `BillingItemNameAlreadyExistsError(project_id, name)`,
  `BillingItemPricingError(unit, field)` ("`unit_rate` is not allowed for `amount` items" etc.),
  `BillingItemInUseError(item_id)`; reuse `ProjectNotFoundError` / `ProjectArchivedError`.
- `ProjectBillingItemRepository`: `list_for_project(project_id, include_inactive)` ordered by
  `position, name`, `get(project_id, item_id)`, `next_position`, `save` (name unique constraint →
  `BillingItemNameAlreadyExistsError`), `delete` (FK violation → `BillingItemInUseError`).
- `ProjectService`: `add_billing_item` (project must exist and be active; pricing checked against
  the unit), `update_billing_item` (name uniqueness, pricing, re-activation requires an active
  project), `delete_billing_item` (FK violation → `BillingItemInUseError`). A shared
  `_ensure_project_active` helper backs both `add_billing_item` and the existing `add_member`
  (which had the same inline check). A wrong-but-existing `project_id` for a real item raises
  `BillingItemNotFoundError` (looked up as `(project_id, item_id)`, so it isn't found); an
  altogether unknown `project_id` raises `ProjectNotFoundError` first — both are 404 at the API.
- `ProjectCustomerDTO.currency` (filled from `CustomerDTO.currency`).
- Register handlers in `projects/module.py`.
- Tests: add/list/update/archive/restore/delete; include_inactive filter; name conflict within a
  project but the same name allowed in another project; pricing errors for each unit; adding to an
  archived project; restoring under an archived project; both not-found cases above; clearing
  `unit_rate`; default items can be renamed and archived.

### B3. HTTP API

- `projects/schemas.py`: `BillingItemCreateRequest`, `BillingItemUpdateRequest`,
  `ProjectBillingItemResponse`; `Rate = Annotated[Decimal, Field(ge=0, max_digits=12,
  decimal_places=2)]`, `Markup = Annotated[Decimal, Field(ge=0, le=1000, max_digits=6,
  decimal_places=2)]` (matching the `numeric(6, 2)` column); `ProjectCustomerResponse.currency`.
  Confirmed: Pydantic's default JSON encoding renders `Decimal` as a string, so rates round-trip
  without float rounding with no extra serializer needed.
- `projects/router.py`: the four routes and the error mapping from the table above.
  `BillingItemNotFoundError` (item missing or belongs to a different project) gets its own 404
  helper carrying the exception's own message, distinct from the generic "Project not found" used
  when `project_id` itself doesn't exist.
- Tests (`test_projects_api.py`): status codes and guards per route (worker reads but gets 403 on
  writes, project manager gets 403 on DELETE), `null` clearing, `unit`/`preset` rejected in PATCH,
  decimals round-trip as strings.

### B4. Admin impact and demo data

- `admin/contracts.py`: `RemovalEffectKind.PROJECT_BILLING_ITEMS`;
  `get_project_removal_impact` counts items via `ListProjectBillingItems(include_inactive=True)`.
  (Deleting a project already cascades to items.) Every project has at least the six defaults, so
  this effect is now never empty — existing tests already index `effects[0]` rather than assert
  equality, so this didn't need any fixing elsewhere.
- `seed.py`: all four demo projects get rates on their defaults via a new `DemoProject.billing_rates`
  flag and a `_apply_demo_billing_rates` helper (normal 90.00, overtime 135.00, travel 45.00, per
  diem 60.00, purchasing markup 10%; other expenses left unset, like a real project would start
  out) — including the archived "Legacy Support" project, priced before it's archived. Rates are
  the same numbers regardless of the customer's currency (EUR/GBP/USD); good enough for demo data,
  not meant to look like real market rates. "Website Revamp" also gets one custom item ("On-call
  standby", `hour`, 50.00) via `DemoProject.custom_billing_items` and a new `DemoBillingItem`
  dataclass. Both only run right after a project is newly created, so re-running stays idempotent.
- Tests: admin impact includes billing items; `test_seed.py` checks rates and the custom item.
  Verified by hand against the real dev database too: `seed-demo` prices all defaults and adds the
  custom item, and a second run changes nothing (still 25 rows: 4 × 6 defaults + 1 custom item).

### F1. Frontend API layer

- `npm run gen:api` after B3.
- `projects/api.ts`: `BillingItem`, `BillingUnit` types; `listProjectBillingItems`,
  `addProjectBillingItem`, `updateProjectBillingItem`, `deleteProjectBillingItem`;
  `BillingItemConflictError` (409 name) and `BillingItemInUseError` (409 on delete); 400 →
  `ProjectRuleError`, 404 → `ProjectNotFoundError`.
- `projects/hooks.ts`: `projectKeys.billingItems(id, includeInactive)`,
  `useProjectBillingItems`, `useAddProjectBillingItem`, `useUpdateProjectBillingItem`,
  `useDeleteProjectBillingItem` (invalidate `projectKeys.all`).
- `admin/RemoveEntityModal.tsx`: label for the `project_billing_items` effect.
- `test/fixtures.ts`: `testProject.customer` needed a `currency` once the schema was regenerated
  (`ProjectCustomerResponse` gained it in B3) — `tsc -b` caught the now-missing field.
- A billing item's 409 means two different things depending on the route (name conflict on
  create/update, "still in use" on delete), unlike a project's single 409 meaning; `api.ts` gets
  two small error mappers (`billingItemWriteError`, `billingItemDeleteError`) instead of reusing
  the generic `ruleAwareError` for writes.

### F2. Billing items on the project page

- `projects/BillingItemFormModal.tsx` (create/edit): name, unit (`Select`, disabled when editing),
  rate (`NumberInput`, 2 decimals, customer currency as suffix) for `hour`/`day` or markup % for
  `amount`, description. Units shown as "per hour", "per day", "expense at cost".
- `pages/ProjectDetailsPage.tsx`: a "Billing items" section above Members — table with Name
  (+ "Default"/"Archived" badges), Unit, Price ("90.00 EUR / hour", "at cost + 10%", "not set"),
  a per-row menu for managers (Edit, Archive/Restore, and for admins "Delete permanently" with a
  confirmation that shows the in-use reason on 409), a "Show archived" switch and an
  "Add billing item" button (disabled with a hint when the project is archived).
- Tests (`ProjectDetailsPage.test.tsx`): items rendered with formatted prices; worker sees no
  actions; manager adds/edits (rate field swaps with the unit); archived toggle; admin-only delete;
  conflict error shown in the form.

### D1. Docs and final verification

- `CLAUDE.md`: billing items in the projects module description, the new effect kind in the admin
  module, frontend `projects/` additions; "remaining domain models" now lists time entries and
  invoices only.
- Run the full backend and frontend checks, `docker compose up --build`, and click through: create
  a project → defaults appear → set rates → add a custom item → archive/restore → delete as admin.

## Out of scope

- Time entries and invoices (billing items only prepare for them).
- A global, admin-editable catalog / templates of default items; copying items between projects.
- Rate history or effective dates (a rate change applies to everything not yet invoiced — to be
  decided with invoices).
- Reordering items in the UI (`position` exists but is not editable yet).
- A per-item "billable / non-billable" flag and hiding rates from workers.
