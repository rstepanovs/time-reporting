"""Invoices ORM entities, internal to the module — other modules use ``invoices.contracts``."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from time_reporting.db.base import Base
from time_reporting.db.mixins import TimestampMixin
from time_reporting.modules.invoices.contracts import InvoiceLineKind, InvoiceStatus


class Invoice(TimestampMixin, Base):
    """One customer invoice, built from one or more of that customer's sent, uninvoiced billing
    periods (``InvoiceBillingPeriod``). ``DRAFT`` is mutable; ``IssueInvoice`` moves it to
    ``ISSUED``, at which point it becomes immutable except for
    ``paid_on``/``voided_at``/``void_reason`` (``MarkInvoicePaid``/``VoidInvoice``).
    """

    __tablename__ = "invoices"
    __table_args__ = (
        CheckConstraint("subtotal >= 0", name="subtotal_non_negative"),
        CheckConstraint("vat_amount >= 0", name="vat_amount_non_negative"),
        CheckConstraint("total >= 0", name="total_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id", ondelete="RESTRICT"))
    # Allocated only when issued, via `company.AllocateInvoiceNumber` — `None` for a draft.
    number: Mapped[str | None] = mapped_column(String(50), unique=True)
    status: Mapped[InvoiceStatus] = mapped_column(
        Enum(InvoiceStatus, name="invoice_status", values_callable=lambda s: [x.value for x in s])
    )
    invoice_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date)
    # Upper-case ISO 4217 code, taken from the customer at creation.
    currency: Mapped[str] = mapped_column(String(3))
    # "sv" or "en" — see customers.contracts.INVOICE_LOCALES.
    locale: Mapped[str] = mapped_column(String(2))
    vat_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    vat_note: Mapped[str | None] = mapped_column(Text)
    your_reference: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    vat_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    # Seller/buyer identity frozen at issue time, so a later edit to the company profile or
    # customer never changes what an already-issued invoice printed.
    seller_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    buyer_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # Rendered PDF, stored as bytea like company.CompanySettings.logo — small enough that pg_dump
    # already backs it up, no new Docker volume.
    pdf: Mapped[bytes | None] = mapped_column(LargeBinary)
    pdf_sha256: Mapped[str | None] = mapped_column(String(64))
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    issued_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    paid_on: Mapped[date | None] = mapped_column(Date)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    void_reason: Mapped[str | None] = mapped_column(Text)


class InvoiceLine(TimestampMixin, Base):
    """One line of an ``Invoice``. ``project_id``/``billing_item_id`` are set only for a generated
    (``TIME``/``EXPENSE``) line, ``SET NULL`` so deleting that project/item later never blocks or
    loses the invoice's own history."""

    __tablename__ = "invoice_lines"
    __table_args__ = (CheckConstraint("amount >= 0", name="amount_non_negative"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), index=True
    )
    # Display order; a new line gets max(position) + 1.
    position: Mapped[int] = mapped_column(default=1, server_default="1")
    kind: Mapped[InvoiceLineKind] = mapped_column(
        Enum(
            InvoiceLineKind,
            name="invoice_line_kind",
            values_callable=lambda k: [x.value for x in k],
        )
    )
    description: Mapped[str] = mapped_column(String(500))
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    unit: Mapped[str] = mapped_column(String(20))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL")
    )
    billing_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_billing_items.id", ondelete="SET NULL")
    )


class InvoiceBillingPeriod(Base):
    """Which billing period(s) an invoice was built from — the join
    `timesheets.ProjectBillingPeriod` itself has no FK to (only a bare `invoice_id` column, per
    that module's own migration); this is the invoices-side record of the same link, keyed the
    same way (`timesheets.contracts.BillingPeriodRef`). No ``TimestampMixin``: written once at
    creation, never updated, deleted only by cascade when the invoice itself is deleted."""

    __tablename__ = "invoice_billing_periods"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "period_start", name="uq_invoice_billing_periods_project_id_period_start"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT"))
    period_start: Mapped[date] = mapped_column(Date)
