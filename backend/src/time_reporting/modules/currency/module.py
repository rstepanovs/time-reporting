"""Registers the currency module's handlers on the bus."""

from time_reporting.core.cqrs import HandlerRegistry
from time_reporting.modules.currency.contracts import GetExchangeRate
from time_reporting.modules.currency.handlers import GetExchangeRateHandler


def register(registry: HandlerRegistry) -> None:
    registry.command(GetExchangeRate, GetExchangeRateHandler)
