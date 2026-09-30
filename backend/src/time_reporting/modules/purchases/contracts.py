"""Public contract of the purchases module.

Other modules may import only this file: DTOs, commands, queries and domain exceptions. Handlers
for these messages are registered in ``purchases.module``; ORM entities never leave the module.
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from uuid import UUID

from time_reporting.core.cqrs import Command, Query

# Scans and photos of receipts and invoices, and PDFs. A separate constant from the expenses
# module's on purpose: the two may diverge (e.g. TIFF from a scanner).
ALLOWED_PURCHASE_CONTENT_TYPES: frozenset[str] = frozenset(
    {"application/pdf", "image/jpeg", "image/png", "image/webp", "image/heic"}
)

DEFAULT_LIST_LIMIT = 200

# How far ahead "due soon" looks, in days, counting today.
DUE_SOON_DAYS = 7


class PurchaseStage(StrEnum):
    INBOX = "inbox"
    REGISTERED = "registered"
    DISCARDED = "discarded"


class PurchaseKind(StrEnum):
    RECEIPT = "receipt"
    INVOICE = "invoice"
    CARD_INVOICE = "card_invoice"
    OTHER = "other"


class PaymentStatus(StrEnum):
    UNPAID = "unpaid"
    PAID = "paid"


class PaymentMethod(StrEnum):
    CARD = "card"
    BANK_TRANSFER = "bank_transfer"
    DIRECT_DEBIT = "direct_debit"
    CASH = "cash"
    PRIVATE = "private"


class PurchaseSort(StrEnum):
    NEWEST = "newest"  # most recently added first
    DOCUMENT_DATE = "document_date"  # newest document date first
    DUE_DATE = "due_date"  # earliest due date first, undated last — the "to pay" order


class PurchaseSource(StrEnum):
    UPLOAD = "upload"
    EMAIL = "email"


class RateSource(StrEnum):
    NONE = "none"  # the document is already in the base currency
    RIKSBANK = "riksbank"
    CARD_INVOICE = "card_invoice"
    MANUAL = "manual"


# --- Errors ---


class PurchaseError(Exception):
    """Base class for every domain error of the purchases module."""


class PurchaseDocumentNotFoundError(PurchaseError):
    def __init__(self, document_id: UUID) -> None:
        super().__init__(f"Purchase document {document_id} not found")
        self.document_id = document_id


class PurchaseFileTooLargeError(PurchaseError):
    def __init__(self, size_bytes: int, max_bytes: int) -> None:
        super().__init__(f"File is {size_bytes} bytes, more than the {max_bytes} byte limit")
        self.size_bytes = size_bytes
        self.max_bytes = max_bytes


class PurchaseFileTypeNotAllowedError(PurchaseError):
    def __init__(self, content_type: str) -> None:
        super().__init__(f"File type {content_type!r} is not allowed")
        self.content_type = content_type


class PurchaseDocumentStateError(PurchaseError):
    """The document's stage or payment state doesn't allow the requested change."""


class PurchaseValidationError(PurchaseError):
    """The submitted fields break the rules of the document's kind."""


# --- DTOs ---


@dataclass(frozen=True, slots=True, kw_only=True)
class PurchaseDocumentDTO:
    id: UUID
    stage: PurchaseStage
    kind: PurchaseKind | None
    vendor: str | None
    document_no: str | None
    description: str | None
    document_date: date | None
    due_date: date | None
    payment_status: PaymentStatus | None
    paid_on: date | None
    payment_method: PaymentMethod | None
    card_invoice_id: UUID | None
    amount: Decimal | None
    currency: str | None
    vat_amount: Decimal | None
    amount_base: Decimal | None
    exchange_rate: Decimal | None
    rate_date: date | None
    rate_source: RateSource | None
    amount_base_final: bool
    file_name: str
    content_type: str
    size_bytes: int
    source: PurchaseSource
    email_from: str | None
    email_subject: str | None
    received_at: datetime | None
    rebilled_expense_line_id: UUID | None
    rebilled_expense_report_id: UUID | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class CardInvoiceDTO:
    """A card invoice with the receipts settled by it.

    ``receipts_total_base`` sums the receipts' base-currency amounts; ``difference_base`` is the
    card invoice's own total minus that sum — fees, interest and purchases with no receipt (yet).
    Both are ``None``-safe: a receipt without an amount counts as zero, and the difference is
    ``None`` while the card invoice itself has no base-currency amount.
    """

    invoice: PurchaseDocumentDTO
    receipts: tuple[PurchaseDocumentDTO, ...]
    receipts_total_base: Decimal
    difference_base: Decimal | None


@dataclass(frozen=True, slots=True, kw_only=True)
class PurchasesSummaryDTO:
    """What needs attention, for the dashboard.

    The unpaid figures cover registered invoices and card invoices not yet paid. Their total is in
    ``base_currency`` and is *provisional* when ``unpaid_provisional`` — at least one amount is
    still the document-date estimate, not a final one; ``unpaid_unconverted_count`` counts unpaid
    documents with no base-currency amount at all (left out of the total).
    """

    base_currency: str
    inbox_count: int
    unpaid_count: int
    unpaid_total_base: Decimal
    unpaid_provisional: bool
    unpaid_unconverted_count: int
    overdue_count: int
    due_soon_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class MonthPurchaseDTO:
    """One registered document of a month. A card invoice carries the receipts it settled
    (whatever their own dates); those receipts are not listed on their own."""

    document: PurchaseDocumentDTO
    card_receipts: tuple[PurchaseDocumentDTO, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class CardReceiptLink:
    """One receipt to link, with its amount in the base currency as printed on the card invoice."""

    receipt_id: UUID
    amount_base: Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class RebillSuggestionDTO:
    """Defaults for the rebill form. ``amount`` is in the project's customer's currency
    (``currency``); ``None`` when it can't be derived (the document has no amount in a usable
    currency yet) and must be typed in."""

    amount: Decimal | None
    currency: str
    expense_date: date | None
    description: str


@dataclass(frozen=True, slots=True, kw_only=True)
class PurchaseFileDTO:
    """Where a document's file lives on disk, plus what to call it when serving it."""

    path: Path
    file_name: str
    content_type: str


@dataclass(frozen=True, slots=True, kw_only=True)
class PurchaseDetails:
    """What a user fills in when classifying a document; the same payload registers and edits.

    Per kind (``PurchaseValidationError`` otherwise):

    - ``receipt`` — ``document_date`` (the purchase date), ``amount``, ``currency`` and
      ``payment_method`` are required; it is always paid, on ``paid_on`` (default: the purchase
      date); no ``due_date``.
    - ``invoice`` / ``card_invoice`` — ``document_date``, ``amount``, ``currency`` and
      ``payment_status`` are required. Unpaid needs a ``due_date`` and has no ``paid_on``/
      ``payment_method``; paid needs both. A card invoice is never paid by card.
    - ``other`` — descriptive fields only (vendor, number, description, date).

    ``amount_base`` / ``exchange_rate`` are optional manual overrides of the automatic conversion
    (mutually exclusive); a manual value is never recomputed by later edits or by "Paid".
    """

    kind: PurchaseKind
    vendor: str | None = None
    document_no: str | None = None
    description: str | None = None
    document_date: date | None = None
    due_date: date | None = None
    payment_status: PaymentStatus | None = None
    paid_on: date | None = None
    payment_method: PaymentMethod | None = None
    amount: Decimal | None = None
    currency: str | None = None
    vat_amount: Decimal | None = None
    amount_base: Decimal | None = None
    exchange_rate: Decimal | None = None


# --- Queries ---


@dataclass(frozen=True, slots=True, kw_only=True)
class PurchaseDocumentPageDTO:
    items: tuple[PurchaseDocumentDTO, ...]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True, slots=True, kw_only=True)
class ListPurchaseDocuments(Query[PurchaseDocumentPageDTO]):
    """One page of documents. Every filter is optional: ``search`` matches vendor, document number
    and description (case-insensitive, literal); ``date_from``/``date_to`` bound ``document_date``
    (inclusive). ``total`` counts every match, not just the page."""

    stage: PurchaseStage | None = None
    kind: PurchaseKind | None = None
    payment_status: PaymentStatus | None = None
    search: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    sort: PurchaseSort = PurchaseSort.NEWEST
    limit: int = DEFAULT_LIST_LIMIT
    offset: int = 0


@dataclass(frozen=True, slots=True, kw_only=True)
class GetPurchaseDocument(Query[PurchaseDocumentDTO]):
    document_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class GetPurchasesSummary(Query[PurchasesSummaryDTO]):
    today: date


@dataclass(frozen=True, slots=True, kw_only=True)
class ListMonthPurchases(Query[tuple[MonthPurchaseDTO, ...]]):
    """Registered documents whose ``document_date`` is in the month, oldest first, with card
    receipts grouped under their card invoice. A card receipt not linked to any card invoice is
    listed on its own (with no base-currency amount)."""

    year: int
    month: int


@dataclass(frozen=True, slots=True, kw_only=True)
class GetCardInvoice(Query[CardInvoiceDTO]):
    """Raises ``PurchaseDocumentStateError`` when the document isn't a registered card invoice."""

    card_invoice_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class ListUnlinkedCardReceipts(Query[tuple[PurchaseDocumentDTO, ...]]):
    """Registered card-paid receipts/invoices not yet linked to a card invoice, dated within the
    range (either bound optional), oldest first — the picker when building a card invoice."""

    date_from: date | None = None
    date_to: date | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class GetPurchaseFilePath(Query[PurchaseFileDTO]):
    """Raises ``PurchaseDocumentNotFoundError`` for an unknown id or a missing file on disk."""

    document_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class ListPurchaseStorageKeys(Query[frozenset[str]]):
    """Every document's ``storage_key``, for ``time-reporting prune-attachments``."""


# --- Commands ---


@dataclass(frozen=True, slots=True, kw_only=True)
class AddPurchaseDocument(Command[PurchaseDocumentDTO]):
    """Store a file as a new inbox document.

    ``external_ref`` (the mail importer's Gmail message/attachment id) makes the call idempotent:
    when a document with that reference already exists it is returned and nothing is written.
    ``actor_id`` is ``None`` for the mail importer.
    """

    actor_id: UUID | None
    file_name: str
    content_type: str
    content: bytes
    source: PurchaseSource = PurchaseSource.UPLOAD
    email_from: str | None = None
    email_subject: str | None = None
    received_at: datetime | None = None
    external_ref: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class DiscardPurchaseDocument(Command[PurchaseDocumentDTO]):
    """Mark a duplicate or junk document ``discarded`` (its file is kept). Refused for one that is
    already discarded or already rebilled to a project."""

    document_id: UUID
    actor_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class RegisterPurchaseDocument(Command[PurchaseDocumentDTO]):
    """Classify an inbox document (``inbox`` → ``registered``) and convert its amount into the
    company's base currency. A currency without a published rate leaves ``amount_base`` empty for
    the user to type in (an update with ``amount_base``)."""

    document_id: UUID
    actor_id: UUID
    details: PurchaseDetails


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdatePurchaseDocument(Command[PurchaseDocumentDTO]):
    """Replace a registered document's fields. Refused once it is rebilled. A manual conversion
    survives unless ``amount``/``currency`` change or ``recompute_conversion`` is set."""

    document_id: UUID
    actor_id: UUID
    details: PurchaseDetails
    recompute_conversion: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class ReturnPurchaseToInbox(Command[PurchaseDocumentDTO]):
    """Undo a registration: every classification field is cleared. Refused when rebilled, or
    for a card invoice that still has receipts linked to it."""

    document_id: UUID
    actor_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class MarkPurchasePaid(Command[PurchaseDocumentDTO]):
    """Pay an unpaid invoice or card invoice. The base-currency amount is recomputed at the rate
    of ``paid_on`` and becomes final — or ``amount_base`` (what the bank actually debited) is taken
    as given, and the rate derived from it."""

    document_id: UUID
    actor_id: UUID
    paid_on: date
    payment_method: PaymentMethod
    amount_base: Decimal | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class MarkPurchaseUnpaid(Command[PurchaseDocumentDTO]):
    """Undo a payment made by mistake: back to unpaid, with an automatic amount provisional
    again (a manual one stays)."""

    document_id: UUID
    actor_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class LinkCardReceipts(Command[CardInvoiceDTO]):
    """Settle card receipts under a card invoice, all or nothing. Each becomes final in the base
    currency at the given amount (``rate_source = card_invoice``, never recomputed). Only a
    registered, card-paid, not yet linked receipt/invoice qualifies
    (``PurchaseDocumentStateError`` otherwise); amounts must be positive and receipts distinct
    (``PurchaseValidationError``)."""

    card_invoice_id: UUID
    actor_id: UUID
    links: tuple[CardReceiptLink, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class UnlinkCardReceipt(Command[PurchaseDocumentDTO]):
    """Detach a receipt from its card invoice; its base-currency amount goes back to open."""

    receipt_id: UUID
    actor_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class UpdateCardReceiptAmount(Command[PurchaseDocumentDTO]):
    receipt_id: UUID
    actor_id: UUID
    amount_base: Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class SuggestRebillAmount(Command[RebillSuggestionDTO]):
    """Prefill for rebilling ``document_id`` to ``project_id``: the document's amount in the
    customer's currency — as printed when the currencies match, otherwise its base-currency amount
    converted at the Riksbank rate of the payment (or document) date. A command only because that
    lookup may store a rate in the cache."""

    document_id: UUID
    project_id: UUID


@dataclass(frozen=True, slots=True, kw_only=True)
class RebillPurchase(Command[PurchaseDocumentDTO]):
    """File a registered receipt or invoice to a project's expense report for ``year``/``month``.

    A copy of the file is stored as an ordinary expense attachment linked to the new line, on the
    actor's own report (created when missing), so it then goes through that report's submit/approve
    flow and reaches the customer's invoice. ``amount`` defaults to ``SuggestRebillAmount``'s and
    ``expense_date`` to the document date; ``description`` is what the line says. Refused when
    already rebilled or not a registered receipt/invoice (``PurchaseDocumentStateError``) and when
    the expense module rejects the line (``PurchaseValidationError``: closed project, wrong
    billing item, date outside the month, no amount; ``PurchaseDocumentStateError``: the report
    isn't editable or is locked).
    """

    document_id: UUID
    actor_id: UUID
    project_id: UUID
    year: int
    month: int
    billing_item_id: UUID
    description: str
    amount: Decimal | None = None
    expense_date: date | None = None
