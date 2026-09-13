"""Customer ORM entity, internal to the module — other modules use ``customers.contracts``."""

import uuid
from datetime import date

from sqlalchemy import CheckConstraint, Date, Enum, String, Text, true
from sqlalchemy.orm import Mapped, mapped_column

from time_reporting.db.base import Base
from time_reporting.db.mixins import TimestampMixin
from time_reporting.modules.customers.contracts import BillingIntervalUnit


class Customer(TimestampMixin, Base):
    __tablename__ = "customers"
    __table_args__ = (
        CheckConstraint("billing_interval_count > 0", name="billing_interval_count_positive"),
        CheckConstraint("payment_terms_days >= 0", name="payment_terms_days_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    legal_name: Mapped[str | None] = mapped_column(String(255))
    tax_id: Mapped[str | None] = mapped_column(String(64))
    billing_email: Mapped[str | None] = mapped_column(String(320))

    # Billing address; the country is stored as an upper-case ISO 3166-1 alpha-2 code.
    billing_address_line1: Mapped[str] = mapped_column(String(255))
    billing_address_line2: Mapped[str | None] = mapped_column(String(255))
    billing_city: Mapped[str] = mapped_column(String(255))
    billing_region: Mapped[str | None] = mapped_column(String(255))
    billing_postal_code: Mapped[str | None] = mapped_column(String(32))
    billing_country: Mapped[str] = mapped_column(String(2))

    # Billing period: consecutive intervals of `count` units, counted from the anchor date.
    billing_interval_count: Mapped[int]
    billing_interval_unit: Mapped[BillingIntervalUnit] = mapped_column(
        Enum(
            BillingIntervalUnit,
            name="billing_interval_unit",
            values_callable=lambda units: [u.value for u in units],
        )
    )
    billing_anchor_date: Mapped[date] = mapped_column(Date)

    # Upper-case ISO 4217 code.
    currency: Mapped[str] = mapped_column(String(3))
    payment_terms_days: Mapped[int] = mapped_column(default=30, server_default="30")
    notes: Mapped[str | None] = mapped_column(Text)
    # Customers are archived rather than deleted: billing data will reference them.
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())
