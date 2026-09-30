# Plan: email integration and a purchase-document register

## Context

Three things still leave the app by hand today:

1. An issued invoice's PDF is downloaded and mailed manually to the customer — usually to an
   automated invoice receiver (an AP scanning address) rather than a person.
2. Receipts and supplier invoices arrive on paper (scanned) or by email. The only place for them is
   an employee's expense report, which is built for claims and rebilling, not for the company's own
   purchases: there is no notion of "an invoice still to pay", of a card payment settled later by
   the credit-card invoice, or of a foreign currency.
3. The accountant's monthly package (`accounting.BuildAccountantPackage`) is downloaded and mailed
   manually, and holds nothing about the company's own purchases beyond internal-project expense
   reports.

The company runs Google Workspace (Business Plus) on its own domain, books in SEK and pays many
purchases with a company credit card. This plan:

- connects the app to **one Gmail mailbox through the Gmail API with OAuth**;
- creates **Gmail drafts** (never sends) for invoices and the accountant package — the user reviews
  and sends or schedules them in Gmail;
- polls a Gmail label fed by a scanner and forwarded emails into an **inbox of incoming
  documents**, which the user classifies into a new **purchase register**: paid receipts, invoices
  to pay (with due date and a "Paid" action) and credit-card invoices that group the card receipts
  they settle, with amounts converted to SEK;
- lets a purchase be **rebilled** by filing it into a project's expense report, from where it can
  travel with the customer's invoice email.

### Decisions confirmed with the user

1. **Gmail API + OAuth** for one connected mailbox; access tokens refreshed on demand, a reconnect
   prompt when the refresh token stops working.
2. **Drafts only** — no sending, no scheduling and no auto-draft on issue in the app; scheduled
   sending is done by hand in Gmail.
3. **Incoming supplier invoices are mostly company costs**; occasionally one is rebilled and must
   go in the same email as the customer's invoice.
4. **One pile, sorted later**: scanned receipts and emailed invoices land in one inbox and are
   classified and distributed afterwards, with descriptions.
5. **Each document is sorted into "paid receipt" or "invoice to pay"**: a receipt records the date
   it was paid, an invoice records its due date and gets a "Paid" button.
6. **Card purchases are grouped under the credit-card invoice** that settled them; the real SEK
   amount of a card purchase comes from that invoice, not from an exchange rate — the receipt is
   only attached.
7. **Other foreign-currency amounts are converted with the Riksbank's rate of the payment date.**
8. **One company card for now** — an implicit single card, no card entity (several cards are in
   the TODO list).
9. **Every other option goes to a TODO list** (`email-integration-todo.md`) so the integration can
   later become configurable and provider-neutral.

### Design decisions (flag on review if wrong)

- **New `mail` module = transport only.** It owns the Google connection (OAuth tokens), the draft
  log and access to the inbound label, behind a `MailProvider` protocol with one `GmailProvider`
  implementation. It knows nothing about invoices or purchases; `invoices`, `accounting` and
  `purchases` depend on `mail.contracts`, never the reverse. The protocol is the seam the TODO
  list's other providers plug into.
- **New `purchases` module owns incoming documents.** A `PurchaseDocument` is one file plus what it
  is: an inbox item until classified, then a receipt, an invoice, a card invoice or "other". This
  replaces the earlier idea of storing inbox documents as report-less expense attachments: the
  register needs its own lifecycle (payment status, due date, card grouping, currency) that has
  nothing to do with an employee's claim, and company costs no longer need to be forced into
  internal-project expense reports.
- **Rebilling copies, it doesn't move.** Filing a purchase to a project executes a new
  `expenses.AddExpenseLineWithAttachment` (creating the report when needed), which stores its own
  copy of the file as an ordinary `ExpenseAttachment`; the purchase keeps the resulting ids. Each
  module keeps owning its own files; the cost is a duplicate of a few hundred KB.
- **The register is the company's books, so it is `AccountantDep`-only** (admin via the usual
  combination). Employees keep uploading their own claim receipts to their own expense reports.
- **Files live under `<attachment_dir>/purchases/`**, so the backup's existing attachment archive
  already covers them. The storage class moves from `expenses/storage.py` into the shared kernel
  (`core/file_storage.py`, parametrized by directory); `expenses.prune_orphans` only matches its
  own two-level key pattern, so it never touches `purchases/` (covered by a test), and
  `prune-attachments` grows a purchases pass.
- **The base currency is a company setting** (`company.base_currency`, default `SEK`). Each
  document keeps its original `amount`/`currency` plus `amount_base`, `exchange_rate`, `rate_date`,
  `rate_source` (`none` when already SEK, `riksbank`, `card_invoice`, `manual`) and
  `amount_base_final` (bool).
- **Riksbank rates of the payment date, cached.** A new small `currency` module fetches the SWEA
  API's daily rates (the `SEK<CCY>PMI` series), takes the latest published rate on or before the
  requested date (weekends and holidays fall back to the previous banking day) and caches it in
  `exchange_rates`; a rate is fetched once, ever. The rate date is **the payment date**:
  - a paid receipt / invoice registered as paid → the rate of `paid_on`, final at once;
  - an unpaid invoice → a **provisional** SEK amount at the rate of the document date (so "To pay"
    and the dashboard can still show SEK totals), marked provisional in the UI;
  - "Paid" → recomputed at the rate of `paid_on` and final; the Paid dialog also accepts the
    actual SEK amount the bank debited instead (`rate_source = manual`, rate derived from it).
  - A manual rate or SEK amount is always allowed and is never overwritten by a later recompute.
  - A card receipt is **never** converted: its `amount_base` is typed from the card invoice's line,
    final once linked.
- **External side effects stay outside the transaction's failure path.** Creating a draft calls
  Gmail first, then writes the log row: a failed commit can only leave a harmless orphan draft in
  Gmail. Importing mail commits the documents first and labels the Gmail messages as processed
  only afterwards; a crash in between re-imports on the next poll, which a unique `external_ref`
  turns into a no-op.
- **No Google client library.** The Gmail REST API, the OAuth token endpoint and the Riksbank API
  are a handful of JSON calls; `httpx` (async, already a dev dependency, promoted to a runtime one)
  keeps them non-blocking and testable with `httpx.MockTransport`.
- **OAuth "Web application" client, callback on the app itself.** Google accepts
  `http://localhost:<port>` redirect URIs, so "Connect Google account" redirects to Google and back
  to `GET /api/v1/mail/oauth/callback`. The consent screen must be **Internal** — an External app
  in "Testing" gets refresh tokens that expire after 7 days. Scope `gmail.modify` only (read, label,
  draft; no permanent delete), knowingly covering the whole connected mailbox.
- **The refresh token is encrypted at rest** (Fernet, `cryptography`) with
  `MAIL_TOKEN_ENCRYPTION_KEY`, so a database dump alone doesn't grant mailbox access.
- **Draft size is checked before upload**: Gmail won't send more than 25 MB of attachments, so the
  app refuses above `MAIL_MAX_DRAFT_BYTES` (default 24 MB) with a clear message. Drafts go through
  the `/upload/` endpoint (`message/rfc822`, up to 35 MB).
- **Sorting is manual for now.** Automatic suggestions (stage C, deferred) will be local — PDF text,
  OCR, rules and the register's own history — never a paid API, and only ever prefill the form.
  The `extracted` JSONB column is created in A3 anyway, so stage C needs no migration of its own.

### Open questions for the spikes (B1, A2)

Checked against the real mailbox and the real Riksbank API before the tasks depending on them are built (B1, and A2 for the Riksbank), with the
answers written back here:

- Can a user label be put on a draft so it shows under that label in Gmail? (Drafts always keep the
  system `DRAFT` label.) Fallback: a recognizable subject, the app's own draft list with
  "Open in Gmail" links.
- Does `https://mail.google.com/mail/u/<email>/#drafts?compose=<message id>` open a given draft?
- After the user schedules a draft, and after it is sent, what does the API show (`SCHEDULED`/`SENT`
  labels, draft gone from `drafts.list`, found via `rfc822msgid:`)?
- Does a `From:` header set to a verified send-as alias survive in the draft and the sent mail?
- Riksbank SWEA: exact series ids and the observation endpoint, anonymous rate limits, how a
  non-banking day is answered.

## Data model

`mail` (new):

- `mail_connection` — singleton (`id = 1`, the `CompanySettings` pattern): `provider` (`gmail`),
  `account_email`, `refresh_token_encrypted` (bytea), `scopes`, `connected_at`, `connected_by_id`
  (FK `users.id` `SET NULL`), `last_error`, `last_error_at`; admin-edited configuration:
  `from_address` (nullable send-as alias), `inbox_label` (default `Time Reporting/Inbox`),
  `processed_label` (`Time Reporting/Imported`), `rejected_label` (`Time Reporting/Rejected`);
  poll status: `last_poll_at`, `last_poll_imported`, `last_poll_error`.
- `mail_drafts` — every draft created: `id`, `purpose` (enum `invoice`/`accountant_package`),
  `subject_ref` (the invoice id, or `YYYY-MM`), `to_addresses`, `subject`, `attachment_names`
  (JSONB), `size_bytes`, `provider_draft_id`, `provider_message_id`, `rfc822_message_id`, `status`
  (enum `draft`/`scheduled`/`sent`/`deleted`/`unknown`), `status_checked_at`, `created_by_id`,
  `created_at`. Index `(purpose, subject_ref)`.

`currency` (new): `exchange_rates` — `currency` char(3), `rate_date` date, `rate` numeric(18, 8)
(SEK per 1 unit), `source` (`riksbank`), `fetched_at`; unique `(currency, rate_date, source)`.

`purchases` (new) — `purchase_documents`:

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `stage` | enum `inbox`/`registered`/`discarded` | `inbox` until classified |
| `kind` | enum `receipt`/`invoice`/`card_invoice`/`other`, nullable | null while in the inbox |
| `vendor`, `document_no`, `description` | varchar, nullable | |
| `document_date` | date, nullable | receipt: purchase date; invoice: invoice date |
| `due_date` | date, nullable | `invoice`/`card_invoice` only |
| `payment_status` | enum `unpaid`/`paid`, nullable | receipt: always `paid` |
| `paid_on` | date, nullable | set by "Paid" or, for a receipt, the purchase date |
| `payment_method` | enum `card`/`bank_transfer`/`direct_debit`/`cash`/`private`, nullable | |
| `card_invoice_id` | uuid FK `purchase_documents.id` `SET NULL`, nullable | a card receipt → the card invoice that settled it |
| `amount`, `currency` | numeric(12, 2), char(3), nullable | as printed on the document (total incl. VAT) |
| `vat_amount` | numeric(12, 2), nullable | |
| `amount_base`, `exchange_rate`, `rate_date`, `rate_source`, `amount_base_final` | | see "Design decisions" |
| `file_name`, `content_type`, `size_bytes`, `sha256`, `storage_key` (unique) | | the file |
| `source` | enum `upload`/`email` | |
| `email_from`, `email_subject`, `received_at`, `external_ref` (unique) | nullable | import metadata and idempotency key |
| `extracted` | JSONB, nullable | stage C's suggestion, kept for comparison; unused until then |
| `rebilled_expense_line_id`, `rebilled_expense_attachment_id` | uuid, nullable | set when filed to a project (table-name FKs `SET NULL`) |
| `created_by_id`, `registered_by_id`, timestamps | | |

Checks: a registered document has a `kind`; `card_invoice_id` only on `payment_method = 'card'`;
`due_date` only on `invoice`/`card_invoice`. Indexes on `(stage, kind)`, `document_date`,
`(payment_status, due_date)`, `card_invoice_id`.

`expenses` (changed): no schema change; new command `AddExpenseLineWithAttachment`.

`customers` (changed): `invoice_delivery_email` (nullable) — the automated invoice receiver; falls
back to `billing_email`.

`company` (changed): `base_currency` (default `SEK`), `accountant_email`, and text templates
`invoice_email_subject`/`_body`, `accountant_email_subject`/`_body` with `{invoice_number}`,
`{customer_name}`, `{total}`, `{currency}`, `{due_date}`, `{month}`, `{company_name}`
placeholders (`str.format_map` over a fixed dict; unknown placeholders left as they are).

## Purchase lifecycle

- **Inbox** (`stage = inbox`): imported from mail or uploaded; only the file and its metadata.
- **Register** (`RegisterPurchaseDocument`): the user picks the kind and fills the fields.
  - `receipt` → `payment_status = paid`, `paid_on = document_date`, a payment method. When the
    method is `card`, the SEK amount is left open until it is linked to a card invoice.
  - `invoice` → `unpaid` with a `due_date`, or already `paid` with `paid_on` (e.g. direct debit).
  - `card_invoice` → like an invoice (unpaid, due date, SEK total); its own page lists linked card
    receipts, each with its SEK amount typed from the card invoice line, the sum vs. the card
    invoice total and the difference (fees, interest, purchases with no receipt yet), and a picker
    of unlinked card receipts dated in its period.
  - `other` → a document to keep (contract, statement); no amounts required.
- **Paid** (`MarkPurchasePaid(paid_on, payment_method, amount_base | None)`) on an unpaid invoice /
  card invoice: the SEK amount is recomputed at the rate of `paid_on` (or taken as given) and
  becomes final. `MarkPurchaseUnpaid` undoes a mistake and makes an automatic SEK amount
  provisional again (a manual one stays).
- **Rebill** (`RebillPurchase(project_id, year, month, billing_item_id, amount, description)`) —
  any registered receipt/invoice; the amount is prefilled in the project's customer currency
  (converted through SEK when it differs) and editable. Refused when already rebilled.
- **Discard** (duplicates, spam) and **back to inbox** while not rebilled.
- Audited: registered, paid, unpaid, rebilled, discarded.

---

## Preparation (by the user, before B1)

1. Google Cloud console, in the Workspace organization: a project, the **Gmail API** enabled, OAuth
   consent screen **Internal**, an OAuth client of type **Web application** with redirect URIs
   `http://localhost:18080/api/v1/mail/oauth/callback` (prod) and
   `http://localhost:5173/api/v1/mail/oauth/callback` (dev).
2. An alias for incoming documents on the connected mailbox (e.g. `scans@<domain>`) and a Gmail
   filter `to:(scans@<domain>)` → label `Time Reporting/Inbox`, skip the inbox. Forwarded supplier
   emails go to the same alias.
3. If invoices should come from another address (e.g. `invoices@<domain>`): a verified "Send mail
   as" alias of the same mailbox.
4. DKIM enabled for the domain in the Admin console.
5. The scanner's "scan to email" configured to send to `scans@<domain>` (options in B13).

## Tasks

Branch `feature/email-integration` from `main`. One reviewable commit per task (`A3: ...`), each
leaving `ruff`, `ruff format --check`, `mypy`, `pytest` (frontend: `lint`, `typecheck`, `test`)
green and updating the `CLAUDE.md` files it touches. Tasks are listed in execution order; tick the
sub-task boxes as they land.

Three independently shippable stages: **A** — the purchase register with manual upload (needs no
Google setup at all, deployable on its own); **B** — mail: drafts and import; **C** — automatic
sorting suggestions (deferred).

### Stage A — purchase register

#### A1 — backend: shared file storage

- [x] Move `ExpenseAttachmentStorage`'s logic into `core/file_storage.py` (`FileStorage(root: Path,
      max_bytes, allowed_types)`); `expenses/storage.py` becomes a thin wrapper over
      `attachment_dir`, no behavior change.
- [x] Existing attachment tests stay green unchanged.
- [x] New test: `expenses` pruning ignores files under `<attachment_dir>/purchases/`.

#### A2 — backend `currency`: Riksbank rates

- [x] `modules/currency/{contracts,models,repository,service,handlers,module,riksbank}.py` +
      `CLAUDE.md`; register in `modules/registry.py`, models in `models/__init__.py`.
- [x] Migration: `exchange_rates`.
- [x] `riksbank.py`: SWEA client over `httpx.AsyncClient` (injectable transport); `httpx` moves to
      runtime dependencies.
- [x] `GetExchangeRate(currency, on_date)` (a command, since a miss writes the cache) — cache first, else fetch the latest observation on or
      before `on_date` (look back at most 10 days), store it; SEK → 1 without a call;
      `ExchangeRateUnavailableError` otherwise.
- [x] `GET /currency/rates/{currency}?on=` (`AccountantDep`).
- [x] Tests (`httpx.MockTransport`): cache hit makes no call, weekend falls back, unavailable, SEK.
- [x] Before merging: one manual call against the live SWEA API to confirm series ids and response
      shape (the Riksbank half of B1's spike, pulled forward since A doesn't wait for Google).
      Result: anonymous access works; `GET /Observations/SEK<CCY>PMI/<from>/<to>` returns
      `[{date, value}]` (SEK per 1 unit, JPY included), banking days only; `204` for an empty range or
      unknown series; `429` past a few requests per minute.

#### A3 — backend `purchases`: module, inbox, upload

- [x] `modules/purchases/*` + `CLAUDE.md`, registered after `expenses`/`currency`, before
      `invoices`.
- [x] Migration: `purchase_documents` with its enums, checks and indexes (the full table, including
      the columns later tasks fill); `company.base_currency` (default `SEK`) through company's
      contracts/schemas.
- [x] Storage under `<attachment_dir>/purchases/` via `FileStorage`.
- [x] `AddPurchaseDocument` (duplicate `external_ref` returns the existing one),
      `DiscardPurchaseDocument`, `GetPurchaseFilePath`, `ListPurchaseDocuments(stage, ...)`.
- [x] Router `/purchases` (`AccountantDep`): multipart upload of several files, list, get, file
      download, discard.
- [x] `prune-attachments` gains the purchases pass.
- [x] Tests: upload/download round trip, type/size limits, idempotent `external_ref`, discard,
      access (non-accountant 403), prune keeps referenced files.

#### A4 — backend `purchases`: register, currency, paid

- [ ] `RegisterPurchaseDocument`, `UpdatePurchaseDocument`, `ReturnPurchaseToInbox` with per-kind
      validation (receipt / invoice / card invoice / other).
- [ ] SEK conversion per "Riksbank rates of the payment date": paid → rate of `paid_on`, final;
      unpaid → document date's rate, provisional; manual rate/amount never recomputed; card receipt
      left open.
- [ ] `MarkPurchasePaid(paid_on, payment_method, amount_base | None)`, `MarkPurchaseUnpaid`.
- [ ] Audit actions `purchase.registered`/`paid`/`unpaid`/`discarded` (+ `audit/CLAUDE.md`).
- [ ] Router routes for all of the above.
- [ ] Tests: each kind's rules, provisional → final on Paid, actual SEK amount at Paid, manual rate
      survives edits, Unpaid, return to inbox, `currency` mocked.

#### A5 — backend `purchases`: card invoices

- [ ] `LinkCardReceipts(card_invoice_id, [(receipt_id, amount_base)])`, `UnlinkCardReceipt`,
      `UpdateCardReceiptAmount`.
- [ ] `GetPurchaseDocument` for a card invoice: linked receipts, their SEK sum, the card invoice
      total and the difference; `ListUnlinkedCardReceipts(date_from, date_to)` for the picker.
- [ ] Tests: only card receipts, one card invoice per receipt, final SEK on link, back to open on
      unlink, sums and difference.

#### A6 — backend `purchases`: summary and month list

- [ ] `GetPurchasesSummary(today)` — inbox count, unpaid count and SEK total (provisional marked),
      overdue, due within 7 days.
- [ ] `ListMonthPurchases(year, month)` for `accounting` (registered documents with
      `document_date` in the month, card receipts grouped under their card invoice).
- [ ] Tests for both.

#### A7 — backend: rebilling a purchase

- [ ] `expenses.AddExpenseLineWithAttachment(project_id, year, month, actor_id, line, file)` — the
      report created when missing, line + linked attachment in one transaction, locked/non-editable
      refused.
- [ ] `purchases.RebillPurchase` executes it with the file's bytes and stores the ids; prefill
      helper converting to the project's customer currency; audit `purchase.rebilled`.
- [ ] Tests: new and existing report, locked report refused, already rebilled refused, the copy
      downloads from the expense report, return-to-inbox refused once rebilled.

#### A8 — backend `accounting`: purchases in the package

- [ ] `accounting` → `purchases.contracts`; `PackageContent` gains purchase rows and files.
- [ ] `summary.pdf`: a Purchases section (card receipts under their card invoice, provisional
      amounts marked); `summary.xlsx`: a `Purchases` sheet.
- [ ] ZIP: `purchases/<NNN>_<date>_<vendor>_<amount><ext>`, `purchases/card-<date>/...`.
- [ ] `GetAccountantPackageStatus`: warnings for documents still in the inbox and unlinked card
      receipts; the provisional SEK total.
- [ ] Tests: contents, grouping, warnings.

#### A9 — frontend: purchases API and the inbox

- [ ] `npm run gen:api`; `frontend/src/purchases/{api,hooks}.ts` + `CLAUDE.md`; test fixtures.
- [ ] `/purchases?tab=inbox` page, route under `RequireRole roles={["accountant"]}`, nav item in
      the "Billing" group with an inbox count badge.
- [ ] Inbox: list, multi-file upload, preview panel (PDF/image), Discard.
- [ ] Register form beside the preview: kind switch, vendor, number, dates, amount + currency with
      the live SEK preview (`/currency/rates`), payment method.
- [ ] Tests: upload, register each kind, SEK preview, discard.

#### A10 — frontend: register, to pay, document page

- [ ] Register tab: filterable, paginated table.
- [ ] To pay tab: by due date, overdue highlighted, "Paid…" dialog (date, method, optional actual
      SEK amount).
- [ ] `/purchases/:id`: preview, edit, Paid/Unpaid, Back to inbox.
- [ ] Tests: filters, Paid flow incl. the actual SEK amount, Unpaid.

#### A11 — frontend: card invoices and rebilling

- [ ] Card invoice page section: linked receipts with editable SEK amounts, sum/total/difference,
      "Add receipts…" picker, unlink.
- [ ] "Rebill to project…" dialog (project, month, billing item, prefilled amount, description) and
      a link to the resulting expense report.
- [ ] Tests: linking and the difference, rebill.

#### A12 — frontend: dashboard and settings

- [ ] "Bills to pay" card in the dashboard's Billing section (`GetPurchasesSummary`).
- [ ] Company page: base currency.
- [ ] Accounting page shows the new warnings.
- [ ] Tests.

#### A13 — documentation for stage A

- [ ] Root `CLAUDE.md` (`currency`, `purchases` modules, `purchases/` frontend area, routes, nav),
      `expenses`, `accounting`, `company`, `audit`, `pages/CLAUDE.md`, `README.md`,
      `docs/operations.md` (purchase files in the backup, prune pass).
- [ ] The stage A manual verification (see "Verification"), then deploy.

### Stage B — mail

#### B1 — spike: Gmail behavior

- [ ] A throwaway script in the scratchpad (not committed) answering the Gmail "Open questions"
      against the prepared mailbox; answers written back into this plan, B3/B4 adjusted.

#### B2 — backend `mail`: connection and OAuth

- [ ] `modules/mail/{contracts,models,repository,service,handlers,module,router,schemas,provider,
      gmail}.py` + `CLAUDE.md`; migration `mail_connection`.
- [ ] Settings `google_oauth_client_id`, `google_oauth_client_secret`, `public_base_url`,
      `mail_token_encryption_key`, `mail_max_draft_bytes`, `mail_poll_interval_minutes` (all
      optional, `MailNotConfiguredError`); non-secret ones in `SystemConfigDTO`; `.env.example`;
      `cryptography` dependency.
- [ ] `MailProvider` protocol; `GmailProvider` token handling (cached access token, refresh ~60 s
      early, `invalid_grant` → `MailReconnectRequiredError` + `last_error`).
- [ ] `GET /mail/oauth/start` (signed `state`), `GET /mail/oauth/callback`, `GET/PATCH/DELETE
      /mail/connection` (`AdminDep`); audit `mail.connected`/`mail.disconnected`.
- [ ] Tests: encryption round trip, refresh on expiry, `invalid_grant`, bad/expired `state`, not
      configured.

#### B3 — backend `mail`: drafts

- [ ] Migration `mail_drafts`.
- [ ] `CreateMailDraft` — MIME (`EmailMessage`), `From` alias, size check, upload endpoint, log row
      after the provider call, "Open in Gmail" URL.
- [ ] `ListMailDrafts`, `RefreshMailDraftStatuses` (classification per B1).
- [ ] Tests with a fake provider: MIME structure (non-ASCII subject/file names), too large, no row
      on provider failure, status refresh.

#### B4 — backend `mail`: reading the label

- [ ] `FetchLabelledMessages(limit)` with allowed attachments' bytes (skipped ones reported),
      `ensure_labels`.
- [ ] `MarkMessagesProcessed`, `MarkMessagesRejected`, `RecordPollResult`.
- [ ] Tests: type/size filtering, label moves, poll status.

#### B5 — backend: mail import and the poller

- [ ] `purchases.ImportPurchasesFromMail` (`source = email`, `external_ref = gmail:<msg>:<part>`,
      email metadata stored).
- [ ] CLI `time-reporting mail-poll` and `POST /purchases/inbox/poll`: import → commit → label →
      record result.
- [ ] `compose.yaml`: `mail-poller` service (the `backup` loop pattern, `attachments` volume),
      idle when not configured/connected.
- [ ] Tests: import, idempotent re-import, rejection, labels only after commit.

#### B6 — backend: customer and company email settings

- [ ] `customers.invoice_delivery_email` (migration, contracts, schemas, `clear_fields`).
- [ ] `company`: `accountant_email` and the four templates with English defaults; placeholder
      rendering helper (unknown placeholders left as they are).
- [ ] Tests: set/clear, rendering.

#### B7 — backend `invoices`: invoice email draft

- [ ] `expenses.ListInvoiceSupportingAttachments(periods)`.
- [ ] `GetInvoiceEmailDraftPreview` (recipient fallback to `billing_email`, rendered templates,
      candidates).
- [ ] `CreateInvoiceEmailDraft` (issued/paid only, PDF first, attachment ids scoped to the
      invoice's periods), audit `invoice.email_drafted`.
- [ ] Routes: preview, create, list (with `refresh`).
- [ ] Tests: status rules, fallback, scoping, too large.

#### B8 — backend `accounting`: accountant package draft

- [ ] `GetAccountantPackageDraftPreview`, `CreateAccountantPackageDraft` (the ZIP attached, too
      large → `MailDraftTooLargeError`), routes, audit.
- [ ] Tests: draft carries the ZIP, too large, list per month.

#### B9 — frontend: integration settings

- [ ] `frontend/src/mail/{api,hooks}.ts` + `CLAUDE.md`.
- [ ] `/admin/integrations` (Administration nav): the four connection states, Connect link,
      Disconnect, from address and labels, last poll result.
- [ ] Company page "Email" section; customer form "Invoice delivery email".
- [ ] Tests: each state, disconnect, settings save.

#### B10 — frontend: mail in the purchases inbox

- [ ] "Check mail now" with the poll result; sender/subject shown on emailed documents.
- [ ] Tests.

#### B11 — frontend: invoice email draft

- [ ] Invoice page (issued/paid) "Email draft…" modal: prefilled recipient/subject/body, fixed PDF
      + supporting attachment checkboxes, one-PDF warning; "Open in Gmail"; draft list with
      "Refresh status".
- [ ] Tests: prefill, selection, too large, reconnect required, draft list.

#### B12 — frontend: accountant email draft

- [ ] Accounting page "Email draft to accountant…" with the package warnings; draft list.
- [ ] Tests.

#### B13 — documentation for stage B

- [ ] `docs/operations.md`: Google Cloud setup, env variables and Fernet key generation,
      `mail-poller`, reconnecting; **scanner setup** — "scan to email" to an address on the own
      domain via Google's restricted server `aspmx.l.google.com:25` (no authentication, delivers
      only to Workspace/Gmail recipients; port 25 may be blocked by the ISP), `smtp.gmail.com:587`
      with an app password, or the Workspace SMTP relay `smtp-relay.gmail.com` with an IP
      allowlist.
- [ ] Root `CLAUDE.md` (`mail` module and frontend area, `/admin/integrations`, `mail-poller`),
      `invoices`, `accounting`, `customers`, `company`, `system`, `audit`, `pages/CLAUDE.md`,
      `README.md`.
- [ ] The stage B manual verification, then deploy.

### Stage C — automatic sorting (deferred, not planned in detail yet)

Classification is manual in stages A and B. Stage C adds suggestions **locally, without a paid
API**, and is planned in detail only once A and B are in use and there are real documents to tune
against:

1. **Text extraction**: the PDF's own text layer first (`pypdf`/`pdfplumber` — most emailed
   invoices are digital PDFs and need no OCR at all), OCR only for scans and photos (Tesseract with
   the `swe`+`eng` language packs, e.g. via `ocrmypdf`, run by the poller, never inside a request);
   the text is stored on the document and becomes searchable.
2. **Rules and patterns**: keywords (`Kvitto`/`Receipt`, `Faktura`/`Invoice`, `Förfallodatum`/
   `Due date`, `Betald`/`Paid`, `Kontokortsfaktura`), regexes for amounts, dates, currencies, org
   numbers, Bankgiro/OCR numbers and masked card numbers (`**** 1234`).
3. **Learning from the register itself**: once a vendor's documents have been registered by hand,
   the next one from the same vendor (sender address or org number) is prefilled with the same
   kind, payment method and currency.
4. **A trained classifier** (e.g. scikit-learn over the extracted text) only if 1–3 aren't good
   enough and there are a few hundred registered documents to learn from.

Whatever the method, the result only prefills the Register form (the `extracted` column), each
suggested field marked; nothing is registered automatically.

## Verification

- Per task: the usual backend/frontend checks against a migrated Postgres.
- Stage A by hand: upload a SEK receipt, an unpaid EUR invoice (a provisional SEK amount at its
  invoice date's rate), two USD card receipts and a card invoice; link the receipts with the SEK
  amounts from the card invoice and see the difference; mark the EUR invoice paid on a later date
  and see the SEK amount recomputed at that date's rate and marked final; mark the card invoice
  paid; rebill one receipt to a customer project and find it on that project's expense report; the month's
  accountant package lists all of it, card receipts under their card invoice.
- Stage B with the real mailbox: connect; scan a receipt to `scans@<domain>`, "Check mail now",
  it appears once (re-polling doesn't duplicate); issue an invoice for a period with the rebilled
  receipt and create its draft with it attached, open it via the link, schedule it in Gmail,
  "Refresh status" shows scheduled, then sent; create the accountant package draft; revoke the
  app's access in the Google account and confirm the UI asks to reconnect.
- Backups: a purchase document survives backup + restore.

## Out of scope (see `email-integration-todo.md`)

Sending or scheduling from the app, other mail providers and auth methods, Drive upload, push
notifications, e-invoicing, email bodies without attachments, several cards as separate accounts,
bank statement import and payment files, VAT bookkeeping, SIE export.
