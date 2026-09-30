"""Purchases ORM entities, internal to the module — other modules use ``purchases.contracts``."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    false,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from time_reporting.db.base import Base
from time_reporting.db.mixins import TimestampMixin
from time_reporting.modules.purchases.contracts import (
    PaymentMethod,
    PaymentStatus,
    PurchaseKind,
    PurchaseSource,
    PurchaseStage,
    RateSource,
)


def _enum(enum_class: type[StrEnum], name: str) -> Enum:
    return Enum(enum_class, name=name, values_callable=lambda members: [m.value for m in members])


class PurchaseDocument(TimestampMixin, Base):
    """A scan or file of something the company bought: a receipt, a supplier invoice, a card
    invoice or any other document worth keeping. Lives in the ``inbox`` until someone classifies
    it (``registered``), or is ``discarded``. The file is on disk under ``storage_key``
    (``PurchaseFileStorage``); this row is the source of truth for which files are referenced.
    """

    __tablename__ = "purchase_documents"
    __table_args__ = (
        CheckConstraint("stage <> 'registered' OR kind IS NOT NULL", name="registered_has_kind"),
        CheckConstraint(
            "card_invoice_id IS NULL OR payment_method = 'card'", name="card_invoice_needs_card"
        ),
        CheckConstraint(
            "due_date IS NULL OR kind IN ('invoice', 'card_invoice')", name="due_date_kind"
        ),
        CheckConstraint("size_bytes > 0", name="size_positive"),
        Index("ix_purchase_documents_stage_kind", "stage", "kind"),
        Index("ix_purchase_documents_document_date", "document_date"),
        Index("ix_purchase_documents_payment_status_due_date", "payment_status", "due_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    stage: Mapped[PurchaseStage] = mapped_column(
        _enum(PurchaseStage, "purchase_stage"), default=PurchaseStage.INBOX
    )
    kind: Mapped[PurchaseKind | None] = mapped_column(_enum(PurchaseKind, "purchase_kind"))

    vendor: Mapped[str | None] = mapped_column(String(255))
    document_no: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(500))
    # Receipt: the purchase date; invoice: the invoice date.
    document_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)

    payment_status: Mapped[PaymentStatus | None] = mapped_column(
        _enum(PaymentStatus, "purchase_payment_status")
    )
    paid_on: Mapped[date | None] = mapped_column(Date)
    payment_method: Mapped[PaymentMethod | None] = mapped_column(
        _enum(PaymentMethod, "purchase_payment_method")
    )
    # A card receipt → the card invoice that settled it.
    card_invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("purchase_documents.id", ondelete="SET NULL"), index=True
    )

    # As printed on the document (total including VAT).
    amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str | None] = mapped_column(CHAR(3))
    vat_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    # The same amount in the company's base currency, and how it was arrived at.
    amount_base: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    exchange_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    rate_date: Mapped[date | None] = mapped_column(Date)
    rate_source: Mapped[RateSource | None] = mapped_column(
        _enum(RateSource, "purchase_rate_source")
    )
    amount_base_final: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    file_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column()
    sha256: Mapped[str] = mapped_column(CHAR(64))
    storage_key: Mapped[str] = mapped_column(String(255), unique=True)

    source: Mapped[PurchaseSource] = mapped_column(_enum(PurchaseSource, "purchase_source"))
    email_from: Mapped[str | None] = mapped_column(String(320))
    email_subject: Mapped[str | None] = mapped_column(String(998))
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The mail importer's idempotency key, e.g. "<gmail message id>/<attachment id>".
    external_ref: Mapped[str | None] = mapped_column(String(255), unique=True)
    # An automatic classifier's suggestion, kept for comparison with what the user registered.
    extracted: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    # Set when the document is filed to a project's expense report (table-name FKs: the rows
    # belong to `expenses`).
    rebilled_expense_line_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("expense_report_lines.id", ondelete="SET NULL")
    )
    rebilled_expense_attachment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("expense_attachments.id", ondelete="SET NULL")
    )
    # The report the line sits on, so the document can link to it.
    rebilled_expense_report_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("expense_reports.id", ondelete="SET NULL")
    )

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    registered_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
