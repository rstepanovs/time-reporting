"""HTTP response models of the purchases API."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from time_reporting.modules.purchases.contracts import (
    PaymentMethod,
    PaymentStatus,
    PurchaseKind,
    PurchaseSource,
    PurchaseStage,
    RateSource,
)


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
