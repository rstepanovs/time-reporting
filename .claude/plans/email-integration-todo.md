# TODO: email integration — options deferred from the first version

The first version (`email-integration.md`) connects one Gmail mailbox through the Gmail API with
OAuth, creates drafts only, and polls one label for incoming documents. Everything below was
considered and deliberately left out; the `mail` module's `MailProvider` protocol is the seam most
of it plugs into. Goal: make the integration configurable and provider-neutral.

## Connection and authentication

- [ ] **SMTP + IMAP with an app password** (`smtp.gmail.com:587`, `imap.gmail.com:993`) — the
  provider-neutral baseline; works with any mail host, not only Google. Google is phasing app
  passwords out and an admin can disable them, so it should not be the only Google option.
- [ ] **IMAP/SMTP with OAuth (XOAUTH2)** — the same protocols with Google or Microsoft tokens
  instead of a password.
- [ ] **Gmail API with a service account and domain-wide delegation** — no interactive consent and
  no expiring refresh token, but the key can impersonate every mailbox in the domain for the
  granted scopes; only with a tightly scoped delegation and the key kept out of backups.
- [ ] **Google Workspace SMTP relay** (`smtp-relay.gmail.com`, IP allowlist or SMTP AUTH) — for
  sending from a server with a static IP; sent mail doesn't appear in anyone's Sent folder.
- [ ] **Microsoft 365 / Outlook via Microsoft Graph** — drafts, send, and reading a folder, for
  customers of the app not on Google.
- [ ] **Generic hosted email APIs** (Postmark, SES, Mailgun...) for sending only.
- [ ] **A dedicated mailbox** (e.g. `billing@<domain>`) instead of the owner's own, so the
  `gmail.modify` scope covers only billing mail — a Workspace licence, a configuration change only.
- [ ] **Several connections** (e.g. one for invoices, another for the inbox) instead of the
  singleton `mail_connection`.
- [ ] **Narrower scopes where possible** (`gmail.compose` for drafts, `gmail.readonly` + label
  moves) once it's clear which calls each feature really needs.

## Sending

- [ ] **Send directly from the app** (`drafts.send` / SMTP) with an outbox table, retries and
  delivery status, instead of the user sending the draft from Gmail.
- [ ] **Scheduled sending in the app** — a `send_after` column on the outbox, delivered by a
  worker; needs the machine running at that time (Gmail's own scheduling doesn't).
- [ ] **Automatic draft/send on invoice issue** — a per-customer flag.
- [ ] **Reminders for overdue invoices** — a draft with the invoice attached again.
- [ ] **One PDF per email for automated receivers** — merge the invoice and its supporting
  documents into a single PDF (receivers often ignore every attachment but the first), a
  per-customer setting.
- [ ] **Per-customer / per-locale templates** instead of one company-wide template.
- [ ] **A signature and HTML body** instead of plain text.

## Large attachments and the accountant

- [ ] **Upload the accountant package to a shared Google Drive folder** (`drive.file` scope, one
  folder per month) and email a notification only — no 25 MB limit.
- [ ] **Split the package across several emails** when it doesn't fit one.
- [ ] **Automatic monthly package** on a fixed day, with the "month not closed" warnings in the
  mail.
- [ ] **Direct export to the accountant's bookkeeping system** (e.g. SIE file, Fortnox / Visma API)
  instead of or next to the ZIP.

## Receiving

- [ ] **Push instead of polling** — Gmail `users.watch` + Cloud Pub/Sub; needs a public HTTPS
  endpoint (or a pull subscription the worker reads).
- [ ] **Emails without attachments** (a supplier invoice in the body or behind a link) — render the
  body to PDF with WeasyPrint and import that.
- [ ] **Plus addressing** (`scans+<project code>@<domain>`) filing a document straight into a
  project's report for that month; needs short project codes.
- [ ] **A sender allowlist / per-sender default owner and project** (e.g. the scanner's own address
  → the owner, a supplier's address → the internal project).
- [ ] **Scanner to Google Drive / a network folder** instead of email.
- [ ] **Handing an inbox document over to another user** (today only an ownerless document can be
  taken, and only for yourself).

## Documents and accounting

- [ ] **Foreign currency on employee expense lines** — the purchase register converts to SEK, but
  an expense report line is still in the project's customer's currency only.
- [ ] **VAT bookkeeping on purchases** (net/VAT split per rate, reclaimable VAT, reverse charge on
  foreign services) beyond the single `vat_amount` field.
- [ ] **Several payment cards / accounts** as their own entities (card invoices and receipts per
  card, matched by the card's last digits) instead of one implicit company card.
- [ ] **Import the card invoice's transactions** (CSV/PDF from the card issuer) and match them to
  receipts automatically by date and amount.
- [ ] **Bank statement import and reconciliation** — mark invoices paid from the bank's
  transactions instead of the "Paid" button.
- [ ] **Payment files** (ISO 20022 `pain.001` / Bankgiro) generated from unpaid invoices.
- [ ] **Credit notes** from suppliers, offset against an invoice.
- [ ] **Several files per document** (an invoice plus its appendix) and merging/splitting inbox
  items.
- [ ] **Employee receipts sent by email** routed to that employee's own expense report instead of
  the company inbox.
- [ ] **Automatic sorting suggestions** (stage C of the plan): PDF text layer, Tesseract OCR for
  scans, keyword/regex rules, per-vendor defaults learned from registered documents, and only then
  a trained classifier. An LLM API (e.g. Claude) stays an opt-in option for hard documents.
- [ ] **Duplicate detection** by SHA-256 across the inbox, the register and expense attachments.
- [ ] **SIE export** of purchases and invoices for the accountant's bookkeeping system.

## Invoices

- [ ] **E-invoicing via Peppol** (EHF / Svefaktura / XRechnung) instead of a PDF by email, for
  customers requiring it.
