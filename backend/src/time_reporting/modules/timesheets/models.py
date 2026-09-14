"""Timesheets ORM entities, internal to the module — other modules use
``timesheets.contracts``."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from time_reporting.db.base import Base
from time_reporting.db.mixins import TimestampMixin
from time_reporting.modules.projects.contracts import BillingUnit


class TimeEntry(TimestampMixin, Base):
    """One day's quantity a user booked against one project billing item.

    ``project_id`` and ``unit`` are denormalized from the billing item (set once, by the service,
    from data it already fetched to validate the write, and never changed afterwards) so this
    module's own queries — filtering by project, or summing a user's hours for a day — never need
    to join into the projects module's tables. ``unit`` reuses the ``billing_unit`` Postgres enum
    already created by the projects module's migration (``create_type=False``): it is the same
    logical enum, not a new one.
    """

    __tablename__ = "time_entries"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "billing_item_id",
            "entry_date",
            name="uq_time_entries_user_id_billing_item_id_entry_date",
        ),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        # Serves both a single user's week (user_id + a date range) and, as a prefix, a plain
        # user_id filter; no separate index on user_id alone.
        Index("ix_time_entries_user_id_entry_date", "user_id", "entry_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), index=True
    )
    billing_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project_billing_items.id", ondelete="RESTRICT")
    )
    entry_date: Mapped[date] = mapped_column(Date)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    unit: Mapped[BillingUnit] = mapped_column(
        Enum(
            BillingUnit,
            name="billing_unit",
            values_callable=lambda units: [u.value for u in units],
            create_type=False,
        )
    )
    note: Mapped[str | None] = mapped_column(Text)
