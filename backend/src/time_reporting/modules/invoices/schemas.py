"""HTTP request/response models of the invoices API.

Response models mirror the shape of DTOs rather than importing another module's own
``schemas.py`` — a module may only reach another module's ``contracts.py``, and the HTTP response
shape is this module's own to own regardless. Mirrors ``expenses/schemas.py``'s conventions
throughout.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from time_reporting.modules.invoices.contracts import (
    CLEARABLE_INVOICE_FIELDS,
    ClearableInvoiceField,
    InvoiceLineKind,
    InvoiceStatus,
)

Description = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Unit = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)]
Quantity = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
UnitPrice = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
VatRate = Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)]
VatNote = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]
YourReference = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)
]
Notes = Annotated[str, StringConstraints(strip_whitespace=True, max_length=10_000)]


class InvoiceCustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    currency: str


class InvoiceLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    position: int
    kind: InvoiceLineKind
    description: str
    quantity: Decimal
    unit: str
    unit_price: Decimal
    amount: Decimal
    project_id: UUID | None
    billing_item_id: UUID | None


class InvoicePeriodResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project_id: UUID
    project_name: str
    period_start: date


class InvoiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer: InvoiceCustomerResponse
    status: InvoiceStatus
    number: str | None
    invoice_date: date
    due_date: date
    currency: str
    locale: str
    vat_rate: Decimal | None
    vat_note: str | None
    your_reference: str | None
    notes: str | None
    subtotal: Decimal
    vat_amount: Decimal
    total: Decimal
    issued_at: datetime | None
    paid_on: date | None
    voided_at: datetime | None
    void_reason: str | None
    lines: list[InvoiceLineResponse]
    periods: list[InvoicePeriodResponse]
    created_at: datetime
    updated_at: datetime


class InvoiceSummaryResponse(BaseModel):
    """One row of a list view (``GET /invoices``)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer_id: UUID
    customer_name: str
    status: InvoiceStatus
    number: str | None
    invoice_date: date
    due_date: date
    currency: str
    total: Decimal


class InvoicePageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    items: list[InvoiceSummaryResponse]
    total: int
    limit: int
    offset: int


class InvoiceablePeriodResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project_id: UUID
    project_name: str
    period_start: date
    period_end: date
    sent_at: datetime


class InvoiceableCustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    customer_id: UUID
    customer_name: str
    currency: str
    periods: list[InvoiceablePeriodResponse]


class CurrencyTotalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    currency: str
    amount: Decimal


class InvoicingSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    periods_to_invoice: int
    unpaid_totals: list[CurrencyTotalResponse]
    overdue_count: int


class BillingPeriodRefRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    period_start: date


class CreateInvoiceDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: UUID
    periods: list[BillingPeriodRefRequest] = Field(min_length=1)


class InvoiceLineChangeRequest(BaseModel):
    """One line's new value. ``line_id`` given updates that line (whatever its ``kind``); omitted
    (or ``null``), it creates a new manual line."""

    model_config = ConfigDict(extra="forbid")

    line_id: UUID | None = None
    description: Description
    quantity: Quantity
    unit: Unit
    unit_price: UnitPrice


class UpdateInvoiceDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice_date: date | None = None
    due_date: date | None = None
    vat_rate: VatRate | None = None
    vat_note: VatNote | None = None
    your_reference: YourReference | None = None
    notes: Notes | None = None
    lines: list[InvoiceLineChangeRequest] = []
    delete_line_ids: list[UUID] = []
    clear_fields: list[ClearableInvoiceField] = Field(
        default=[], description=f"Any of: {', '.join(CLEARABLE_INVOICE_FIELDS)}"
    )


class MarkInvoicePaidRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paid_on: date


class VoidInvoiceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
