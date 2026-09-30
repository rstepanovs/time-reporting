"""Exchange-rate lookup: the local cache first, the rates source only on a miss."""

from datetime import date, timedelta
from decimal import Decimal

from time_reporting.modules.currency.contracts import (
    CURRENCY_CODE_PATTERN,
    MAX_RATE_LOOKBACK_DAYS,
    QUOTE_CURRENCY,
    RATE_SOURCE_RIKSBANK,
    ExchangeRateDTO,
    ExchangeRateUnavailableError,
)
from time_reporting.modules.currency.repository import ExchangeRateRepository
from time_reporting.modules.currency.riksbank import RatesSource, RatesSourceError


class CurrencyService:
    def __init__(self, rates: ExchangeRateRepository, source: RatesSource) -> None:
        self._rates = rates
        self._source = source

    async def get_rate(self, currency: str, on_date: date) -> ExchangeRateDTO:
        currency = currency.upper()
        if currency == QUOTE_CURRENCY:
            return ExchangeRateDTO(
                currency=currency,
                requested_date=on_date,
                rate_date=on_date,
                rate=Decimal(1),
                source="none",
            )
        if CURRENCY_CODE_PATTERN.fullmatch(currency) is None:
            raise ExchangeRateUnavailableError(currency, on_date, "not a currency code")

        # Only an exact hit proves the cache is complete for this date: a cached rate from an
        # earlier day might be stale if a later banking day (still <= on_date) was never fetched.
        cached = await self._rates.get_exact(currency, on_date, RATE_SOURCE_RIKSBANK)
        if cached is not None:
            return self._dto(currency, on_date, cached.rate_date, cached.rate)

        earliest = on_date - timedelta(days=MAX_RATE_LOOKBACK_DAYS)
        try:
            fetched = await self._source.fetch_rates(currency, earliest, on_date)
        except RatesSourceError as exc:
            raise ExchangeRateUnavailableError(currency, on_date, str(exc)) from exc
        if not fetched:
            raise ExchangeRateUnavailableError(
                currency, on_date, f"no rate published in the {MAX_RATE_LOOKBACK_DAYS} days before"
            )

        await self._rates.store_many(currency, fetched, RATE_SOURCE_RIKSBANK)
        rate_date = max(day for day in fetched if day <= on_date)
        return self._dto(currency, on_date, rate_date, fetched[rate_date])

    @staticmethod
    def _dto(currency: str, requested: date, rate_date: date, rate: Decimal) -> ExchangeRateDTO:
        return ExchangeRateDTO(
            currency=currency,
            requested_date=requested,
            rate_date=rate_date,
            rate=rate,
            source=RATE_SOURCE_RIKSBANK,
        )
