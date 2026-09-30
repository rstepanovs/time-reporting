# frontend purchases/

Backend: `modules/purchases` (stages, register rules, conversion to the base currency) and
`modules/currency` (Riksbank rates). Accountant-only throughout (`RequireRole roles={["accountant"]}`
on `/purchases`).

## API layer

- `api.ts` — `listPurchaseDocuments({ stage?, kind? })`, `getPurchasesSummary` (inbox count, unpaid
  figures and the **base currency**), `uploadPurchaseDocuments(files)` (one multipart request, several
  `files`; a bad file rejects the whole batch), `discardPurchaseDocument`,
  `registerPurchaseDocument({ documentId, details })`, `getExchangeRate({ currency, on })` and
  `purchaseFileUrl(id)` (a plain relative URL for an `<iframe>`/`<img>`/`<a href>`, never fetched
  through `api`).
- Errors: `PurchaseRuleError` (400/404 — a per-kind rule, an unknown document, or no exchange rate),
  `PurchaseConflictError` (409 — the document's state), `PurchaseFileTooLargeError` (413),
  `PurchaseFileTypeError` (415); each carries the backend's `detail`.
- `hooks.ts`: `purchaseKeys` with `documents()` (every list) and `summary()` prefixes, which all
  mutations invalidate together. Mutation functions are wrapped, not passed bare — TanStack calls
  them with a context argument that would otherwise reach the API function.

## Inbox (`pages/PurchasesPage.tsx`, `PurchaseRegisterForm.tsx`)

- `/purchases?tab=inbox` (only tab so far): a list of inbox documents (file, source — the email
  subject for mail — size, date), the selected one (first by default) with a preview (PDF in an
  `<iframe>`, images in an `<img>`, a plain link for HEIC which browsers can't render) and a
  download link, **Discard**, and the register form beside it. The tab title and the "Purchases" nav
  item (`AppLayout`, accountants only) show the inbox count from `getPurchasesSummary`.
- `PurchaseRegisterForm` (keyed by document id, so switching starts a fresh form): a kind switch
  (receipt/invoice/card invoice/other) drives which fields show — receipt: purchase date, amount,
  currency, VAT, payment method; invoice/card invoice: "Not paid yet" (due date) or "Already paid"
  (paid-on date, method; a card invoice can't be paid by card); other: descriptive fields only. The
  per-kind rules are enforced by the backend (400 shown in an alert), not duplicated here.
- **Base-currency preview** mirrors what the backend will apply: the amount as is in the base
  currency, else the Riksbank rate of the payment date (a receipt's purchase date, a paid invoice's
  "Paid on") or, for an unpaid invoice, of the document date, marked "provisional until paid". A card
  receipt shows a note instead (its amount comes from the card invoice). When no rate is published,
  a hint asks for the manual "<base> amount (optional)" — which, when filled, also switches the
  preview off (the backend stores it as a manual amount, never recomputed).
