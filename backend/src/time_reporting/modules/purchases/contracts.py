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
    """The document's stage doesn't allow the requested change."""


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
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class PurchaseFileDTO:
    """Where a document's file lives on disk, plus what to call it when serving it."""

    path: Path
    file_name: str
    content_type: str


# --- Queries ---


@dataclass(frozen=True, slots=True, kw_only=True)
class ListPurchaseDocuments(Query[tuple[PurchaseDocumentDTO, ...]]):
    """Newest first, restricted to a stage and/or kind when given."""

    stage: PurchaseStage | None = None
    kind: PurchaseKind | None = None
    limit: int = DEFAULT_LIST_LIMIT


@dataclass(frozen=True, slots=True, kw_only=True)
class GetPurchaseDocument(Query[PurchaseDocumentDTO]):
    document_id: UUID


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
