"""Public contract of the currency module.

Other modules may import only this file: DTOs, commands, queries and domain exceptions. Handlers
for these messages are registered in ``currency.module``; ORM entities never leave the module.
"""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from time_reporting.core.cqrs import Command

# The currency every rate is quoted against: a rate is "SEK per one unit of the currency".
QUOTE_CURRENCY = "SEK"

# How many days before the requested date a published rate is still accepted — enough to bridge
# a weekend plus a holiday stretch such as Christmas/New Year.
MAX_RATE_LOOKBACK_DAYS = 10

RATE_SOURCE_RIKSBANK = "riksbank"

CURRENCY_CODE_PATTERN = re.compile(r"^[A-Z]{3}$")


# --- Errors ---


class CurrencyError(Exception):
    """Base class for every domain error of the currency module."""


class ExchangeRateUnavailableError(CurrencyError):
    def __init__(self, currency: str, on_date: date, reason: str) -> None:
        super().__init__(f"No {currency} exchange rate for {on_date}: {reason}")
        self.currency = currency
        self.on_date = on_date
        self.reason = reason


# --- DTOs ---


@dataclass(frozen=True, slots=True, kw_only=True)
class ExchangeRateDTO:
    currency: str
    requested_date: date
    # The banking day the rate was actually published for: ``requested_date`` or an earlier one.
    rate_date: date
    rate: Decimal
    source: str


# --- Commands ---


@dataclass(frozen=True, slots=True, kw_only=True)
class GetExchangeRate(Command[ExchangeRateDTO]):
    """SEK per one unit of ``currency`` on ``on_date``, or the latest rate published before it.

    ``SEK`` itself is always 1 without any lookup. Raises ``ExchangeRateUnavailableError`` when no
    rate within ``MAX_RATE_LOOKBACK_DAYS`` can be found or the source can't be reached.

    A command, not a query, because a lookup that misses the cache stores what it fetched — and
    only a command's outermost ``execute()`` commits. Nested in another command (registering a
    purchase) the rates commit together with it.
    """

    currency: str
    on_date: date
