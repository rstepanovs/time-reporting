# customers module

Owns the `Customer` entity: name, legal details, a structured billing address (ISO 3166-1 alpha-2
country), a billing period (`interval_count` × `BillingIntervalUnit`, counted from `anchor_date`),
currency (ISO 4217) and payment terms.

- Any authenticated user can read customers; writes require `ManagerDep` (the `manager` access
  level).
- `UpdateCustomer` treats `None` as "unchanged"; optional text fields are cleared by naming them in
  `clear_fields`, which the router fills from fields sent as JSON `null`.
- `ListCustomers` filters by a `search` substring against name or legal name (via the shared
  `db/queries.py:escape_like`).
- `GetCustomersByIds` is the batch query other modules (e.g. `projects`) use for display data.
- Deleting is archive-by-default, permanent-on-request — orchestrated by the `admin` module.
  `DeleteCustomer` (permanent) fails with `CustomerInUseError` while the customer still has any
  project.
- Archiving a customer does not cascade to its projects, but creating or reactivating a project
  requires its customer to be active (enforced in `projects`).
