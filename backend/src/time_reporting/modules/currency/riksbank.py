"""Client of the Riksbank SWEA API (https://api.riksbank.se/swea/v1), anonymous access.

Daily exchange rates are the ``SEK<CCY>PMI`` series ("SEK per one unit", published each banking
day; weekends and holidays have no observation). The API answers ``204 No Content`` for a range
without observations or an unknown series and ``429`` once the anonymous rate limit (a few requests
per minute) is exceeded.
"""

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Protocol

import httpx

from time_reporting.modules.currency.contracts import QUOTE_CURRENCY

_TIMEOUT_SECONDS = 10.0


class RatesSourceError(Exception):
    """The rates source couldn't be reached or answered something unusable."""


class RatesSource(Protocol):
    async def fetch_rates(
        self, currency: str, date_from: date, date_to: date
    ) -> dict[date, Decimal]:
        """Every published rate for ``currency`` between the two dates (inclusive); empty if
        there's none. Raises ``RatesSourceError`` on any failure."""
        ...


class RiksbankClient:
    def __init__(self, base_url: str, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._transport = transport

    async def fetch_rates(
        self, currency: str, date_from: date, date_to: date
    ) -> dict[date, Decimal]:
        series_id = f"{QUOTE_CURRENCY}{currency}PMI"
        span = f"{date_from.isoformat()}/{date_to.isoformat()}"
        url = f"{self._base_url}/Observations/{series_id}/{span}"
        try:
            async with httpx.AsyncClient(
                transport=self._transport, timeout=_TIMEOUT_SECONDS
            ) as client:
                response = await client.get(url)
        except httpx.HTTPError as exc:
            raise RatesSourceError(f"Riksbank request failed: {exc}") from exc

        if response.status_code == httpx.codes.NO_CONTENT:
            return {}
        if response.status_code == httpx.codes.TOO_MANY_REQUESTS:
            raise RatesSourceError("Riksbank rate limit exceeded, try again in a minute")
        if response.status_code != httpx.codes.OK:
            raise RatesSourceError(f"Riksbank answered HTTP {response.status_code}")

        try:
            return {
                date.fromisoformat(item["date"]): Decimal(str(item["value"]))
                for item in response.json()
                if item.get("value") is not None
            }
        except (ValueError, KeyError, TypeError, InvalidOperation) as exc:
            raise RatesSourceError("Riksbank answered an unexpected payload") from exc
