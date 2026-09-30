"""Exchange-rate lookup with a mocked Riksbank (`httpx.MockTransport`) and the real database."""

from datetime import date
from decimal import Decimal

import httpx
import pytest
from httpx import AsyncClient

from support import ACCOUNTANT, EMPLOYEE, AuthHeaders, UserFactory
from time_reporting.core.cqrs import Bus
from time_reporting.modules.currency.contracts import (
    ExchangeRateUnavailableError,
    GetExchangeRate,
)
from time_reporting.modules.currency.riksbank import RiksbankClient

# A currency no real test or dev data uses, so cached rows never collide with anything.
CCY = "ZZZ"
OBSERVATIONS = [
    {"date": "2026-09-24", "value": 11.2645},
    {"date": "2026-09-25", "value": 11.29},
]


class FakeRiksbank:
    """Records the requests it answers and serves ``OBSERVATIONS`` (or a fixed status)."""

    def __init__(self, *, status: int = 200) -> None:
        self.requests: list[httpx.Request] = []
        self._status = status

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self._status != 200:
            return httpx.Response(self._status)
        return httpx.Response(200, json=OBSERVATIONS)


@pytest.fixture
def fake_riksbank(monkeypatch: pytest.MonkeyPatch) -> FakeRiksbank:
    return install(monkeypatch, FakeRiksbank())


def install(monkeypatch: pytest.MonkeyPatch, fake: FakeRiksbank) -> FakeRiksbank:
    client = RiksbankClient("https://riksbank.test/swea/v1", transport=httpx.MockTransport(fake))
    monkeypatch.setattr(
        "time_reporting.modules.currency.handlers.create_rates_source", lambda: client
    )
    return fake


async def test_weekend_falls_back_to_the_previous_banking_day(
    bus: Bus, fake_riksbank: FakeRiksbank
) -> None:
    rate = await bus.execute(GetExchangeRate(currency=CCY.lower(), on_date=date(2026, 9, 27)))

    assert rate.currency == CCY
    assert rate.rate_date == date(2026, 9, 25)
    assert rate.requested_date == date(2026, 9, 27)
    assert rate.rate == Decimal("11.29")
    assert str(fake_riksbank.requests[0].url).endswith(
        f"/Observations/SEK{CCY}PMI/2026-09-17/2026-09-27"
    )


async def test_an_exact_cached_date_makes_no_second_call(
    bus: Bus, fake_riksbank: FakeRiksbank
) -> None:
    query = GetExchangeRate(currency=CCY, on_date=date(2026, 9, 25))

    first = await bus.execute(query)
    second = await bus.execute(query)

    assert first == second
    assert len(fake_riksbank.requests) == 1
    # The whole fetched window was cached, not just the requested day.
    earlier = await bus.execute(GetExchangeRate(currency=CCY, on_date=date(2026, 9, 24)))
    assert earlier.rate == Decimal("11.2645")
    assert len(fake_riksbank.requests) == 1


async def test_sek_needs_no_lookup(bus: Bus, fake_riksbank: FakeRiksbank) -> None:
    rate = await bus.execute(GetExchangeRate(currency="SEK", on_date=date(2026, 9, 25)))

    assert rate.rate == Decimal(1)
    assert rate.source == "none"
    assert fake_riksbank.requests == []


@pytest.mark.parametrize("status", [204, 429, 500])
async def test_unavailable_when_nothing_is_published_or_the_source_fails(
    bus: Bus, monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    install(monkeypatch, FakeRiksbank(status=status))

    with pytest.raises(ExchangeRateUnavailableError):
        await bus.execute(GetExchangeRate(currency=CCY, on_date=date(2026, 9, 25)))


async def test_rates_route_is_for_accountants(
    client: AsyncClient,
    make_user: UserFactory,
    auth_headers: AuthHeaders,
    fake_riksbank: FakeRiksbank,
) -> None:
    accountant = auth_headers(await make_user(roles=ACCOUNTANT))
    employee = auth_headers(await make_user(roles=EMPLOYEE))
    url = f"/api/v1/currency/rates/{CCY}"

    assert (await client.get(url, headers=employee, params={"on": "2026-09-25"})).status_code == 403
    ok = await client.get(url, headers=accountant, params={"on": "2026-09-27"})
    assert ok.status_code == 200
    assert Decimal(ok.json()["rate"]) == Decimal("11.29")
    assert ok.json()["rate_date"] == "2026-09-25"


async def test_route_answers_502_when_unavailable(
    client: AsyncClient,
    make_user: UserFactory,
    auth_headers: AuthHeaders,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install(monkeypatch, FakeRiksbank(status=204))
    headers = auth_headers(await make_user(roles=ACCOUNTANT))

    response = await client.get(
        f"/api/v1/currency/rates/{CCY}", headers=headers, params={"on": "2026-09-25"}
    )

    assert response.status_code == 502
