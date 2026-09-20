# frontend customers/

Backend: `modules/customers`.

- `api.ts` — typed calls for the customer endpoints, plus `CustomerConflictError` (409) and
  `CustomerNotFoundError` (404).
- `hooks.ts` — `customerKeys` + list/detail queries and create/update mutations (`useCustomers`,
  `useCreateCustomer`, `useUpdateCustomer`).
- `CustomerFormModal.tsx` — the create/edit form used by `pages/admin/AdminCustomersPage.tsx`.
  Elsewhere (e.g. the projects customer picker) only the read-only `useCustomers` is needed. An
  "Invoicing" section holds `vat_rate` (blank prints no VAT line — e.g. reverse charge, explained
  by the free-text `vat_note` instead), an "Invoice language" select (`INVOICE_LOCALE_OPTIONS` from
  `company/api.ts` plus a "Company default" option mapping to `null`) and the free-text
  `customer_number`/`your_reference`. Nothing reads these yet; the future `invoices` module will.
