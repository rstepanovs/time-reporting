# frontend customers/

Backend: `modules/customers`.

- `api.ts` — typed calls for the customer endpoints, plus `CustomerConflictError` (409) and
  `CustomerNotFoundError` (404).
- `hooks.ts` — `customerKeys` + list/detail queries and create/update mutations (`useCustomers`,
  `useCreateCustomer`, `useUpdateCustomer`).
- `CustomerFormModal.tsx` — the create/edit form used by `pages/admin/AdminCustomersPage.tsx`.
  Elsewhere (e.g. the projects customer picker) only the read-only `useCustomers` is needed.
