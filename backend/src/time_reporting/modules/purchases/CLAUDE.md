# purchases module

Owns `PurchaseDocument` (`purchase_documents`): the company's register of incoming receipts,
supplier invoices, card invoices and other documents worth keeping. Accountant-only
(`AccountantDep`, admin via the usual level combination) — employees keep claiming their own
spending through `expenses`. Design and lifecycle: `.claude/plans/email-integration.md`.

Depends on `currency.contracts` (`GetExchangeRate`), `company.contracts` (`GetCompanySettings` for
`base_currency`) and `audit.contracts`; rebilling will add `expenses.contracts`.

## Stages

`inbox` (just stored: file + import metadata) → `registered` (classified: kind, amounts, payment) or
`discarded` (duplicate/junk; the row and file are kept). The table already carries every column
later tasks fill (kind/payment/currency/card link/rebill ids, `extracted` for a future classifier);
its CHECK constraints (`registered` needs a `kind`, `card_invoice_id` only on a card payment,
`due_date` only on invoices) hold from the start.

## Files

`storage.py: PurchaseFileStorage` wraps `core/file_storage.FileStorage` rooted at
`<attachment_dir>/purchases/`, so the backup's attachment archive already covers them while
`expenses`' pruning (it only matches `<hex>/<file>`) never touches them. The size limit is the
shared `attachment_max_bytes`. As everywhere, the file is written before the row; a rolled-back
command can orphan a file, which `time-reporting prune-attachments` sweeps (it now also passes over
the purchases directory, reporting those keys with a `purchases/` prefix).

## Commands and queries

- `AddPurchaseDocument` stores a file as an inbox document. With an `external_ref` it is
  idempotent: an existing document with that reference is returned and nothing is written; a
  concurrent insert that loses the unique-constraint race deletes its file and returns the winner
  (the flush runs in a savepoint so the session stays usable). `actor_id` is `None` for the mail
  importer.
- `DiscardPurchaseDocument` → `discarded`; refused when already discarded or rebilled.
- `ListPurchaseDocuments(stage, kind, limit)` newest first, `GetPurchaseDocument`,
  `GetPurchaseFilePath` (a missing row *or* missing file is `PurchaseDocumentNotFoundError`),
  `ListPurchaseStorageKeys`.

## Registering, editing, paying

`PurchaseDetails` (contracts) is the one payload for `RegisterPurchaseDocument` (inbox →
`registered`) and `UpdatePurchaseDocument` (full replace of a registered document, refused once
rebilled); `rules.py: normalize` validates it per kind (`PurchaseValidationError` → 400) — see its
docstring: a receipt is always paid (on the purchase date by default) and needs a payment method;
an invoice/card invoice is unpaid (due date required, no payment fields) or paid (`paid_on` +
method required), a card invoice never by card; `other` takes descriptive fields only.
`ReturnPurchaseToInbox` clears the classification (refused when rebilled or when a card invoice
still has linked receipts). `MarkPurchasePaid`/`MarkPurchaseUnpaid` only work on a registered
invoice or card invoice in the opposite state (`PurchaseDocumentStateError` → 409).

## Conversion to the base currency (`conversion.py`)

Every registered document with an amount gets `amount_base`, `exchange_rate`, `rate_date`,
`rate_source` and `amount_base_final` from `Converter.apply`:

- Already in `company.base_currency` → as is, `rate_source = none`.
- Otherwise the Riksbank rate (`currency.GetExchangeRate`, executed nested so the cached rates
  commit with the document): **paid** → the rate of `paid_on`, `amount_base_final = true`;
  **unpaid** → the rate of `document_date`, provisional (`final = false`) until "Paid".
- A **card** payment of a receipt/invoice is never converted (`amount_base` stays empty) — A5 types
  it in from the card invoice's line (`rate_source = card_invoice`, never recomputed).
- A **manual** amount (`amount_base`, rate derived) or rate (`exchange_rate`) is never recomputed by
  later edits, by Paid or by Unpaid; an update that changes `amount`/`currency`, or sets
  `recompute_conversion`, discards it. `MarkPurchasePaid.amount_base` (what the bank really debited)
  is the same manual amount.
- No published rate (`ExchangeRateUnavailableError`) → the document is still registered with the
  amount left empty, for the user to type in.

## Card invoices (`service.py`, "card invoices" section)

A card receipt is a registered `receipt`/`invoice` with `payment_method = card`; its base-currency
amount is open until a `card_invoice` (registered) settles it.

- `LinkCardReceipts(card_invoice_id, links=[(receipt_id, amount_base)])` is all-or-nothing: every
  receipt must be a registered, card-paid, unlinked document, amounts positive, receipts distinct.
  Each gets `card_invoice_id`, the typed `amount_base` (rate derived), `rate_source = card_invoice`
  and `amount_base_final` — never recomputed by edits, Paid or Unpaid. `UpdateCardReceiptAmount`
  retypes it; `UnlinkCardReceipt` clears it back to open.
- `GetCardInvoice` → `CardInvoiceDTO`: the card invoice, its receipts, `receipts_total_base` and
  `difference_base` (card invoice total minus the sum: fees, interest, purchases without a
  receipt; `None` while the card invoice has no base-currency amount).
  `ListUnlinkedCardReceipts(date_from, date_to)` feeds the picker.
- Guards: a card invoice with linked receipts can't be returned to the inbox, discarded, or turned
  into another kind; a linked receipt stays a card-paid receipt (edits to its other fields keep the
  card amount) and discarding one unlinks it first.

## HTTP API

Under `/purchases`, all `AccountantDep`: `POST /documents` (multipart, `files` — several at once;
every file's type and size is checked before any is stored, so one bad file rejects the batch:
415/413), `GET /documents?stage=&kind=&limit=`, `GET /documents/{id}`, `GET /documents/{id}/file`,
`POST /documents/{id}/discard` (409 on a state error), `POST /documents/{id}/register` and `PUT
/documents/{id}` (`PurchaseDetailsRequest`; 400 on a rule error, 409 on state), `POST
/documents/{id}/return-to-inbox`, `POST /documents/{id}/paid` (`paid_on`, `payment_method`,
optional `amount_base`) `POST /documents/{id}/unpaid`; for card invoices `GET /card-receipts/unlinked?date_from=&date_to=`,
`GET /documents/{id}/card-invoice`, `POST /documents/{id}/card-receipts` (`{links: [{receipt_id,
amount_base}]}`), `PUT /documents/{id}/card-amount` and `POST /documents/{id}/unlink-card` (the last
two take the *receipt's* id). `frontend/nginx.conf`'s 12 MB body limit
covers one file at a time; a batch of files larger than that in total would need it raised.
