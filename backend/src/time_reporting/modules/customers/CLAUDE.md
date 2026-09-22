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
- Invoicing fields, all nullable and clearable the same way as `legal_name`/`tax_id`/`notes`:
  `vat_rate` (0–100, checked both in the DB and by the Pydantic schema; null means the invoice
  prints no VAT line — e.g. reverse charge, explained instead by `vat_note`), `vat_note`,
  `invoice_locale` (`"sv"`/`"en"`; null falls back to the company's own default) and the free-text
  `customer_number`/`your_reference` printed on an invoice. `INVOICE_LOCALES` is a local constant in
  `customers.contracts`, deliberately duplicating `company.contracts.INVOICE_LOCALES` rather than
  importing it — a module may only import another module's `contracts.py`, and neither of these two
  needs the other; both independently mirror `faktura_printer.available_locales()`. Read by
  `invoices` (`CreateInvoiceDraft`, `IssueInvoice`) — see `invoices/CLAUDE.md`.
