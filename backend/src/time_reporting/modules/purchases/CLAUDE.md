# purchases module

Owns `PurchaseDocument` (`purchase_documents`): the company's register of incoming receipts,
supplier invoices, card invoices and other documents worth keeping. Accountant-only
(`AccountantDep`, admin via the usual level combination) — employees keep claiming their own
spending through `expenses`. Design and lifecycle: `.claude/plans/email-integration.md`.

Depends on nothing yet besides `core/file_storage.py`; later tasks add `currency.contracts`
(SEK conversion), `audit.contracts`, `company.contracts` (`base_currency`) and `expenses.contracts`
(rebilling).

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

## HTTP API

Under `/purchases`, all `AccountantDep`: `POST /documents` (multipart, `files` — several at once;
every file's type and size is checked before any is stored, so one bad file rejects the batch:
415/413), `GET /documents?stage=&kind=&limit=`, `GET /documents/{id}`, `GET /documents/{id}/file`,
`POST /documents/{id}/discard` (409 on a state error). `frontend/nginx.conf`'s 12 MB body limit
covers one file at a time; a batch of files larger than that in total would need it raised.
