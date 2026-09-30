"""Currency ORM entities, internal to the module — other modules use ``currency.contracts``."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CHAR, Date, DateTime, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from time_reporting.db.base import Base


class ExchangeRate(Base):
    """One published rate — SEK per one unit of ``currency`` — cached forever once fetched."""

    __tablename__ = "exchange_rates"
    __table_args__ = (
        UniqueConstraint("currency", "rate_date", "source", name="uq_exchange_rates_rate"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    currency: Mapped[str] = mapped_column(CHAR(3))
    rate_date: Mapped[date] = mapped_column(Date)
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    source: Mapped[str] = mapped_column(String(20))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
