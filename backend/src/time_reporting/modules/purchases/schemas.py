"""HTTP response models of the purchases API."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from time_reporting.modules.purchases.contracts import (
    PaymentMethod,
    PaymentStatus,
    PurchaseDetails,
    PurchaseKind,
    PurchaseSource,
    PurchaseStage,
    RateSource,
)

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
DocumentNo = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
CurrencyCode = Annotated[str, StringConstraints(pattern=r"^[A-Za-z]{3}$")]
Money = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
Rate = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=8)]


class PurchaseDetailsRequest(BaseModel):
    """The classification form; per-kind rules are enforced by the service (400)."""

    model_config = ConfigDict(extra="forbid")

    kind: PurchaseKind
    vendor: Text | None = None
    document_no: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
        | None
    ) = None
    description: LongText | None = None
    document_date: date | None = None
    due_date: date | None = None
    payment_status: PaymentStatus | None = None
    paid_on: date | None = None
    payment_method: PaymentMethod | None = None
    amount: Money | None = None
    currency: CurrencyCode | None = None
    vat_amount: Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)] | None = None
    amount_base: Money | None = None
    exchange_rate: Rate | None = None

    def to_details(self) -> PurchaseDetails:
        return PurchaseDetails(**self.model_dump())


class UpdatePurchaseRequest(PurchaseDetailsRequest):
    recompute_conversion: bool = False

    def to_details(self) -> PurchaseDetails:
        return PurchaseDetails(**self.model_dump(exclude={"recompute_conversion"}))


class MarkPaidRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paid_on: date
    payment_method: PaymentMethod
    # What the bank actually debited, in the base currency; omit to convert at the paid_on rate.
    amount_base: Money | None = None


class CardReceiptLinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    receipt_id: UUID
    amount_base: Money


class LinkCardReceiptsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    links: Annotated[list[CardReceiptLinkRequest], Field(min_length=1)]


class CardReceiptAmountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount_base: Money


class PurchaseDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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


class CardInvoiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    invoice: PurchaseDocumentResponse
    receipts: list[PurchaseDocumentResponse]
    receipts_total_base: Decimal
    difference_base: Decimal | None


class PurchasesSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    base_currency: str
    inbox_count: int
    unpaid_count: int
    unpaid_total_base: Decimal
    unpaid_provisional: bool
    unpaid_unconverted_count: int
    overdue_count: int
    due_soon_count: int


class MonthPurchaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document: PurchaseDocumentResponse
    card_receipts: list[PurchaseDocumentResponse]


class RebillRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    year: Annotated[int, Field(ge=2000, le=2100)]
    month: Annotated[int, Field(ge=1, le=12)]
    billing_item_id: UUID
    description: Text
    # In the project's customer's currency; omit to use the suggestion.
    amount: Money | None = None
    expense_date: date | None = None


class RebillSuggestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    amount: Decimal | None
    currency: str
    expense_date: date | None
    description: str
