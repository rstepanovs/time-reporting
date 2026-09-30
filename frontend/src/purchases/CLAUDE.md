# frontend purchases/

Backend: `modules/purchases` (stages, register rules, conversion to the base currency) and
`modules/currency` (Riksbank rates). Accountant-only throughout (`RequireRole roles={["accountant"]}`
on `/purchases`).

## API layer

- `api.ts` — `listPurchaseDocuments(params)` (a *page*: `stage`, `kind`, `paymentStatus`, `search`,
  `dateFrom`/`dateTo`, `sort`, `limit`, `offset`), `getPurchaseDocument`, `updatePurchaseDocument`,
  `markPurchasePaid`, `markPurchaseUnpaid`, `returnPurchaseToInbox`, `getPurchasesSummary` (inbox count, unpaid
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

- `/purchases?tab=inbox|register|to-pay` (`Tabs` with `keepMounted={false}`, so only the open tab
  queries). **Inbox**: a list of inbox documents (file, source — the email
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

## Register, To pay and the document page

- **Register tab** (`PurchaseRegisterTab`): every registered document, newest document date first,
  20 per page (`Pagination`), filterable by kind, payment state, a date range and a debounced text
  search (vendor, number, description); any filter change returns to page 1. Amounts come from
  `format.ts`: a `~` before a base-currency amount marks an estimate (unpaid), "—" a missing one
  (a card receipt awaiting its card invoice, or no published rate).
- **To pay tab** (`PurchaseToPayTab`): unpaid invoices/card invoices by due date (`sort=due_date`),
  overdue ones in red with a badge (compared with `todayIso()`), each with **Paid…**
  (`MarkPaidModal`: payment date — default today — method, and for a foreign-currency document an
  optional base-currency amount actually debited; omitted, the backend converts at the payment
  date's rate and makes it final).
- **`/purchases/:documentId`** (`PurchaseDocumentPage`): header with kind/status badges, the amounts
  and how the base amount arose (rate of a date, set by hand, from the card invoice), the file
  preview, and for a registered document the same form as registration in `mode="edit"`
  (`updatePurchaseDocument`; a "recompute" checkbox appears for a hand-set base amount), Paid…/
  Mark unpaid (invoices and card invoices) and "Back to inbox…" (confirmed). A rebilled document
  shows a notice and no form or return action, matching the backend freeze. The form is keyed by
  `id + updated_at`, so a save or payment change resets it from the server's copy.

## Card invoices and rebilling

- **`CardInvoiceSection`** (on the document page of a registered card invoice): the linked
  receipts, each with its own amount and an editable base-currency amount — the figure from the
  card invoice's line — saved per row (`updateCardReceiptAmount`, enabled only once changed) and
  **Unlink**; beneath, *Receipts total*, *Card invoice total* and the **difference** (green at
  zero, orange otherwise: fees, interest, purchases with no receipt yet). **Add receipts…**
  (`LinkCardReceiptsModal`) lists unlinked card-paid receipts over a date range (default: the 62
  days up to the invoice date), each selectable with the amount from the invoice typed beside it;
  the Link button stays disabled until every selected receipt has an amount > 0, and the backend
  links all or none. A linked receipt's own page links back to its card invoice; an unlinked
  card-paid receipt carries a notice that its base amount is open until linked.
- **`RebillModal`** ("Rebill to project…", registered receipts/invoices that aren't rebilled yet):
  project (active ones, from `useProjects`), billing item (only the project's active `amount`
  items), expense date (its month picks the expense report), amount and description. The amount
  and description start as the server's suggestion (`getRebillSuggestion`: the printed amount if
  the currencies match, else converted through the base currency) until the user types over them;
  when it can't be derived a hint asks for it. On success the line is on the accountant's *own*
  expense report for the project-month, which still has to be submitted and approved there; the
  rebilled document then links to it (`rebilled_expense_report_id` → `/expenses/:id`) and loses
  its edit and return actions.
