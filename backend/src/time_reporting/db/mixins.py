"""Reusable column sets for ORM models."""

from datetime import UTC, datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    """``created_at`` / ``updated_at`` columns.

    Values are generated on the Python side, so they are readable right after a flush without an
    extra round trip (lazy loading is not available on async sessions); the server defaults cover
    rows inserted outside the ORM.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, server_default=func.now()
    )
