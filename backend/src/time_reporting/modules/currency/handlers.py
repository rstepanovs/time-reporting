"""Command handlers of the currency module (registered in ``currency.module``)."""

from time_reporting.core.config import get_settings
from time_reporting.core.cqrs import Bus
from time_reporting.modules.currency.contracts import ExchangeRateDTO, GetExchangeRate
from time_reporting.modules.currency.repository import ExchangeRateRepository
from time_reporting.modules.currency.riksbank import RatesSource, RiksbankClient
from time_reporting.modules.currency.service import CurrencyService


def create_rates_source() -> RatesSource:
    """The production rates source; tests monkeypatch this to inject a mock transport."""
    return RiksbankClient(get_settings().riksbank_api_url)


class GetExchangeRateHandler:
    def __init__(self, bus: Bus) -> None:
        self._service = CurrencyService(ExchangeRateRepository(bus.session), create_rates_source())

    async def handle(self, query: GetExchangeRate) -> ExchangeRateDTO:
        return await self._service.get_rate(query.currency, query.on_date)
