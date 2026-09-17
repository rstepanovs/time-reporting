"""Expenses ORM entities, internal to the module — other modules use ``expenses.contracts``."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from time_reporting.db.base import Base
from time_reporting.db.mixins import TimestampMixin, utc_now
from time_reporting.modules.expenses.contracts import ExpenseReportStatus


class ExpenseReport(TimestampMixin, Base):
    """One employee's expense claim for one project and one calendar month.

    Unlike ``timesheets.TimesheetWeek``, a ``draft`` row is persisted — the document has to exist
    before lines and attachments can hang off it. ``locked_at`` is set (in the same transaction as
    the billing handoff, via a nested ``LockProjectMonthExpenseReports`` executed from
    ``timesheets``) once the project's month is sent to billing, and cleared if it's reopened;
    ``expenses`` never reads ``timesheets``' tables to know this itself.
    """

    __tablename__ = "expense_reports"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "project_id",
            "period_start",
            name="uq_expense_reports_user_id_project_id_period_start",
        ),
        CheckConstraint("period_start <= period_end", name="period_start_before_period_end"),
        Index("ix_expense_reports_project_id_period_start", "project_id", "period_start"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="RESTRICT"))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    status: Mapped[ExpenseReportStatus] = mapped_column(
        Enum(
            ExpenseReportStatus,
            name="expense_report_status",
            values_callable=lambda statuses: [s.value for s in statuses],
        )
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    return_comment: Mapped[str | None] = mapped_column(String(10_000))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExpenseReportLine(TimestampMixin, Base):
    """One dated, priced item of an ``ExpenseReport``, e.g. one receipt's worth of a purchase."""

    __tablename__ = "expense_report_lines"
    __table_args__ = (CheckConstraint("amount > 0", name="amount_positive"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    report_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("expense_reports.id", ondelete="CASCADE"), index=True
    )
    billing_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project_billing_items.id", ondelete="RESTRICT")
    )
    expense_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    description: Mapped[str] = mapped_column(String(255))
    vendor: Mapped[str | None] = mapped_column(String(255))
    document_no: Mapped[str | None] = mapped_column(String(100))
    # Display order within the report; new lines get max(position) + 1.
    position: Mapped[int] = mapped_column(default=1, server_default="1")


class ExpenseAttachment(Base):
    """Metadata for one uploaded receipt/invoice scan, hanging off the report as a whole (not a
    specific line). The file itself lives on disk under ``storage_key``
    (``ExpenseAttachmentStorage``, in ``storage.py``); this row is the source of truth for which
    files are still referenced — ``time-reporting prune-attachments`` deletes orphaned files whose
    row a rolled-back write never committed. No ``updated_at``: a row is written once and only ever
    deleted, never modified.
    """

    __tablename__ = "expense_attachments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    report_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("expense_reports.id", ondelete="CASCADE"), index=True
    )
    file_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column()
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(255), unique=True)
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
