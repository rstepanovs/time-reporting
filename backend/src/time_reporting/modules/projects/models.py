"""Project ORM entities, internal to the module — other modules use ``projects.contracts``."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from time_reporting.db.base import Base
from time_reporting.db.mixins import TimestampMixin, utc_now
from time_reporting.modules.projects.contracts import BillingItemPreset, BillingUnit


class Project(TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("customer_id", "name", name="uq_projects_customer_id_name"),
        CheckConstraint(
            "normal_working_hours > 0 AND normal_working_hours <= 24",
            name="normal_working_hours_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Immutable after creation; referenced by table name, never by importing customers.models.
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    # Archived by default (billing data will reference projects); the admin module can permanently
    # delete one that nothing references yet.
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())
    # The one manager responsible for this project (an active admin/project_manager); referenced
    # by table name, never by importing users.models. Nullable: not every project has one yet.
    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    # Hours booked per working day when a timesheet week is prefilled for this project.
    normal_working_hours: Mapped[Decimal] = mapped_column(
        Numeric(4, 2), default=Decimal("8.00"), server_default="8"
    )


class ProjectMember(Base):
    """A user added to a project. A plain link with no per-project role."""

    __tablename__ = "project_members"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )


class ProjectBillingItem(TimestampMixin, Base):
    """A position invoices for the project are made of, e.g. overtime hours or per diems.

    ``unit`` and ``preset`` are immutable. ``unit_rate`` prices ``hour``/``day`` items;
    ``markup_percent`` applies only to ``amount`` items, whose money amount is entered per expense.
    Rates are in the customer's currency.
    """

    __tablename__ = "project_billing_items"
    __table_args__ = (
        # Also serves lookups by project_id, so no separate index on it.
        UniqueConstraint("project_id", "name", name="uq_project_billing_items_project_id_name"),
        UniqueConstraint("project_id", "preset", name="uq_project_billing_items_project_id_preset"),
        CheckConstraint("unit_rate >= 0", name="unit_rate_non_negative"),
        CheckConstraint("markup_percent >= 0", name="markup_percent_non_negative"),
        CheckConstraint("unit_rate IS NULL OR unit <> 'amount'", name="unit_rate_not_for_amount"),
        CheckConstraint(
            "markup_percent IS NULL OR unit = 'amount'", name="markup_percent_only_for_amount"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    preset: Mapped[BillingItemPreset | None] = mapped_column(
        Enum(
            BillingItemPreset,
            name="billing_item_preset",
            values_callable=lambda presets: [p.value for p in presets],
        )
    )
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[BillingUnit] = mapped_column(
        Enum(
            BillingUnit, name="billing_unit", values_callable=lambda units: [u.value for u in units]
        )
    )
    unit_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    markup_percent: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    # Display (and later invoice) order within the project.
    position: Mapped[int]
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())
