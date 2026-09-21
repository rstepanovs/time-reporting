"""HTTP request/response models of the expenses API.

Response models mirror the shape of DTOs from ``projects.contracts`` (via ``from_attributes``)
rather than importing that module's own ``schemas.py`` — a module may only reach another module's
``contracts.py``, and the HTTP response shape is this module's own to own regardless. Mirrors
``timesheets/schemas.py``'s conventions throughout.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from time_reporting.modules.expenses.contracts import ExpenseReportStatus
from time_reporting.modules.projects.contracts import BillingItemPreset, BillingUnit

Amount = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
Vendor = Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)]
DocumentNo = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]
# A non-blank explanation, required when returning a report to its owner for corrections.
ReturnComment = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10_000)
]


class ExpenseCustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    is_active: bool
    currency: str


class ExpenseProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    customer: ExpenseCustomerResponse
    name: str
    is_active: bool


class ExpenseBillingItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    preset: BillingItemPreset | None
    name: str
    unit: BillingUnit
    unit_rate: Decimal | None
    markup_percent: Decimal | None
    position: int
    is_active: bool


class ExpenseOptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project: ExpenseProjectResponse
    billing_items: list[ExpenseBillingItemResponse]


class ExpenseUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: str


class ExpenseLineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    expense_date: date
    billing_item: ExpenseBillingItemResponse
    amount: Decimal
    description: str
    vendor: str | None
    document_no: str | None


class ExpenseAttachmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    line_id: UUID | None
    file_name: str
    content_type: str
    size_bytes: int
    uploaded_by_name: str | None
    created_at: datetime


class ExpenseReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project: ExpenseProjectResponse
    user: ExpenseUserResponse
    period_start: date
    period_end: date
    status: ExpenseReportStatus
    submitted_at: datetime | None
    reviewed_at: datetime | None
    reviewed_by_name: str | None
    return_comment: str | None
    locked_at: datetime | None
    can_edit: bool
    can_submit: bool
    can_review: bool
    is_locked: bool
    total: Decimal
    lines: list[ExpenseLineResponse]
    attachments: list[ExpenseAttachmentResponse]


class ExpenseReportSummaryResponse(BaseModel):
    """One row of a list view (``GET /expenses/reports``, ``GET /expenses/submissions``)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project: ExpenseProjectResponse
    user: ExpenseUserResponse
    period_start: date
    period_end: date
    status: ExpenseReportStatus
    submitted_at: datetime | None
    total: Decimal
    line_count: int


class CreateExpenseReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    year: Annotated[int, Field(ge=2000, le=2100)]
    month: Annotated[int, Field(ge=1, le=12)]


class ExpenseLineChangeRequest(BaseModel):
    """One line's new value. ``line_id`` given updates that line; omitted (or ``null``), it
    creates a new one."""

    model_config = ConfigDict(extra="forbid")

    line_id: UUID | None = None
    billing_item_id: UUID
    expense_date: date
    amount: Amount
    description: Description
    vendor: Vendor | None = None
    document_no: DocumentNo | None = None


class SaveExpenseReportLinesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lines: list[ExpenseLineChangeRequest] = []
    delete_line_ids: list[UUID] = []


class ReturnExpenseReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comment: ReturnComment


class SetAttachmentLineRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line_id: UUID | None
