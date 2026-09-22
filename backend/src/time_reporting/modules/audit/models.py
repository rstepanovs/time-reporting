"""Audit event ORM entity, internal to the module — other modules use ``audit.contracts``."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from time_reporting.db.base import Base
from time_reporting.db.mixins import utc_now


class AuditEvent(Base):
    """One immutable record of an administrative action, written by the owning module's command
    handler in the same transaction as the change itself (see ``RecordAuditEvent``). Never
    updated or deleted by the app.

    ``action`` and ``entity_type`` are plain strings rather than Postgres enums (contrast
    ``NonWorkingDay.kind``/``TimesheetWeek.status`` elsewhere), since the set of audited actions is
    expected to keep growing as more of the app gains audit coverage, and altering a Postgres enum
    type is disproportionately ceremonious (see migration ``635a2361699d`` for what that looks
    like) for a column that exists purely for a human-readable log.
    """

    __tablename__ = "audit_events"
    __table_args__ = (
        # Serves "newest first" listings; a plain ascending btree index still supports an ORDER BY
        # ... DESC scan backwards just as well as a descending one would.
        Index("ix_audit_events_occurred_at", "occurred_at"),
        Index("ix_audit_events_entity", "entity_type", "entity_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    # `SET NULL` (not `RESTRICT`): a deleted user's history stays readable via `actor_name`, and
    # deleting them must never be blocked by their own audit trail.
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    actor_name: Mapped[str | None] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str] = mapped_column(Text)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
