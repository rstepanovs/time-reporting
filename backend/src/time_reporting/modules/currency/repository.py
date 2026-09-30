"""Persistence of cached ``ExchangeRate`` rows. Flushes but never commits — the bus owns
transactions."""

from collections.abc import Mapping
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from time_reporting.modules.currency.models import ExchangeRate


class ExchangeRateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_exact(self, currency: str, rate_date: date, source: str) -> ExchangeRate | None:
        result = await self._session.scalars(
            select(ExchangeRate).where(
                ExchangeRate.currency == currency,
                ExchangeRate.rate_date == rate_date,
                ExchangeRate.source == source,
            )
        )
        return result.one_or_none()

    async def get_latest_on_or_before(
        self, currency: str, on_date: date, earliest: date, source: str
    ) -> ExchangeRate | None:
        result = await self._session.scalars(
            select(ExchangeRate)
            .where(
                ExchangeRate.currency == currency,
                ExchangeRate.source == source,
                ExchangeRate.rate_date <= on_date,
                ExchangeRate.rate_date >= earliest,
            )
            .order_by(ExchangeRate.rate_date.desc())
            .limit(1)
        )
        return result.one_or_none()

    async def store_many(self, currency: str, rates: Mapping[date, Decimal], source: str) -> None:
        """Insert rates not cached yet; an already cached date is left as it is (rates are
        immutable once published, and a concurrent request may have stored the same one)."""
        if not rates:
            return
        statement = (
            insert(ExchangeRate)
            .values(
                [
                    {"currency": currency, "rate_date": day, "rate": rate, "source": source}
                    for day, rate in rates.items()
                ]
            )
            .on_conflict_do_nothing(constraint="uq_exchange_rates_rate")
        )
        await self._session.execute(statement)
